# services/api/main.py
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any
import uuid

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from libs.config import settings
from libs.schema.email_summary_v1 import EmailSummaryV1
from libs.gmail_client.client import GmailConfig, get_thread_messages, search_threads
from libs.llm_client.groq import GroqSummarizer
from libs.rag.store import upsert_emails, semantic_search
from agents.graph import build_agent
from libs.db.repo import init_db, save_summary
from libs.db.session import engine  # DB engine for connectivity check

# ----------------------------------------------------------------------
# Optional Auth Dependencies (for multi-user UI flow)
# ----------------------------------------------------------------------
try:
    from services.api.deps import current_user  # Bearer -> user
    from libs.gmail_client.user_service import gmail_service_from_token_json
    AUTH_AVAILABLE = True
except Exception as e:
    print("⚠️ AUTH IMPORT ERROR:", e)
    current_user = None  # type: ignore
    gmail_service_from_token_json = None  # type: ignore
    AUTH_AVAILABLE = False


# ----------------------------------------------------------------------
# FastAPI App
# ----------------------------------------------------------------------
app = FastAPI(title="Email Summarizer API (RAG + Agentic)", version="0.5.0")


from fastapi.middleware.cors import CORSMiddleware

# Accept requests from your Next.js dev server
cors_origins = {
    getattr(settings, "UI_URL", "http://localhost:3000").rstrip("/"),
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cors_origins),
    allow_credentials=True,
    allow_methods=["*"],          # <-- critical for OPTIONS
    allow_headers=["*"],          # <-- allows Authorization header
)

print("✅ CORS middleware enabled for:", cors_origins)


# ----------------------------------------------------------------------
# Request Models
# ----------------------------------------------------------------------
class ThreadReq(BaseModel):
    thread_id: str


class SearchReq(BaseModel):
    query: str = "newer_than:7d"
    limit: int = 5


class RAGIndexReq(BaseModel):
    thread_id: str


class RAGSearchReq(BaseModel):
    query: str
    k: int = 5


class AgentSummarizeReq(BaseModel):
    thread_id: str | None = None
    query: str | None = None


# ----------------------------------------------------------------------
# Startup
# ----------------------------------------------------------------------
@app.on_event("startup")
def _startup():
    """Create tables and include OAuth router if available."""
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print("⚠️ DB init skipped:", e)

    # Include Google OAuth routes if enabled
    if settings.AUTH_ENABLED and AUTH_AVAILABLE:
        try:
            from services.api.auth import router as google_auth_router  # type: ignore
            app.include_router(google_auth_router)
            print("✅ Auth router mounted")
        except Exception as e:
            print("⚠️ Auth router not mounted:", e)


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# ----------------------------------------------------------------------
# Dev Utilities (no PII)
# ----------------------------------------------------------------------
@app.get("/v1/dev/config")
def show_config():
    """Return runtime info (safe for local use)."""
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "groq_api_key_loaded": bool(settings.GROQ_API_KEY),
        "groq_model": settings.GROQ_MODEL,
        "gmail_credentials_path": settings.GMAIL_CREDENTIALS,
        "gmail_credentials_exists": Path(settings.GMAIL_CREDENTIALS).exists(),
        "gmail_token_path": settings.GMAIL_TOKEN,
        "gmail_token_exists": Path(settings.GMAIL_TOKEN).exists(),
        "auth_enabled": bool(settings.AUTH_ENABLED and AUTH_AVAILABLE),
        "ui_url": getattr(settings, "UI_URL", None),
        "database_url": settings.DATABASE_URL,
        "db_connectable": db_ok,
    }


@app.get("/v1/dev/groq/ping")
def groq_ping():
    """Quick ping to validate Groq API connectivity."""
    if not settings.GROQ_API_KEY:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"ok": False, "error": "GROQ_API_KEY missing in .env"},
        )
    try:
        s = GroqSummarizer(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
        res = s.client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": 'Return JSON: {"ok": true}'}],
            temperature=0.0,
            max_tokens=10,
        )
        return {"ok": True, "raw": res.choices[0].message.content}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"ok": False, "error": f"{type(e).__name__}: {e}"},
        )


@app.get("/v1/dev/gmail/thread/{thread_id}")
def gmail_thread_preview(thread_id: str):
    """Preview Gmail thread metadata for debugging."""
    cfg = GmailConfig(credentials_path=settings.GMAIL_CREDENTIALS, token_path=settings.GMAIL_TOKEN)
    data = get_thread_messages(thread_id=thread_id, cfg=cfg)
    return {
        "thread_id": thread_id,
        "message_count": len(data.get("messages", [])),
        "subjects": [m.get("subject") for m in data.get("messages", [])][:5],
        "has_any_body": any(bool(m.get("body")) for m in data.get("messages", [])),
        "body_lengths": [len(m.get("body", "")) for m in data.get("messages", [])][:5],
    }


# ----------------------------------------------------------------------
# Helpers (flatten + chunking/map-reduce)
# ----------------------------------------------------------------------
def _flatten_thread_text(thread: dict) -> str:
    parts = []
    for m in thread.get("messages", []):
        body = (m.get("body") or "")[:4000]
        parts.append(
            f"Subject: {m.get('subject','')}\n"
            f"From: {m.get('from','')}\n"
            f"Date: {m.get('date','')}\n"
            f"Body:\n{body}\n---\n"
        )
    return "\n".join(parts)[:12000]


def _chunk_text(s: str, size: int = 3500, overlap: int = 200) -> list[str]:
    out = []
    i = 0
    while i < len(s):
        out.append(s[i : i + size])
        i += size - overlap
    return out


def _reduce_bullets(bullets: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge key points and actions from chunks."""
    kp, seen_kp, actions, seen_act = [], set(), [], set()
    for b in bullets:
        for k in (b.get("key_points") or []):
            k = k.strip()
            if k and k.lower() not in seen_kp:
                kp.append(k)
                seen_kp.add(k.lower())
        for a in (b.get("actions") or []):
            key = (
                (a.get("who") or "").lower(),
                (a.get("what") or "").lower(),
                (a.get("due") or ""),
                (a.get("priority") or ""),
            )
            if key not in seen_act and a.get("what"):
                actions.append(
                    {
                        "who": a.get("who") or "Unassigned",
                        "what": a.get("what"),
                        "due": a.get("due"),
                        "priority": a.get("priority") or "medium",
                    }
                )
                seen_act.add(key)
    return {"key_points": kp[:20], "actions": actions[:10]}


def _bullets_to_prompt_text(b: dict[str, Any]) -> str:
    lines = []
    if b.get("key_points"):
        lines.append("Key Points:")
        for k in b["key_points"]:
            lines.append(f"- {k}")
    if b.get("actions"):
        lines.append("\nActions:")
        for a in b["actions"]:
            lines.append(f"- {a['who']}: {a['what']} (due: {a['due']}, priority: {a['priority']})")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Legacy Summarize/Search Endpoints
# ----------------------------------------------------------------------
@app.post("/v1/summarize/search")
def summarize_search(req: SearchReq):
    cfg = GmailConfig(credentials_path=settings.GMAIL_CREDENTIALS, token_path=settings.GMAIL_TOKEN)
    if not Path(cfg.credentials_path).exists():
        raise HTTPException(status_code=500, detail=f"Missing Gmail credentials file: {cfg.credentials_path}")
    try:
        ids = search_threads(query=req.query, max_results=req.limit, cfg=cfg)
        return {"query": req.query, "threads": ids}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gmail error: {type(e).__name__}: {e}")


@app.post("/v1/summarize/thread")
def summarize_thread(req: ThreadReq):
    """Summarize a Gmail thread using Groq model."""
    if not req.thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required")
    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    cfg = GmailConfig(credentials_path=settings.GMAIL_CREDENTIALS, token_path=settings.GMAIL_TOKEN)
    thread = get_thread_messages(thread_id=req.thread_id, cfg=cfg)
    content = _flatten_thread_text(thread)
    if not content.strip():
        raise HTTPException(status_code=422, detail="Thread has no readable text content")

    summarizer = GroqSummarizer(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
    if len(content) > 12000:
        chunks = _chunk_text(content)
        maps = [summarizer.summarize_chunk_to_bullets(c) for c in chunks]
        merged = _reduce_bullets(maps)
        stitched = _bullets_to_prompt_text(merged)
        final = summarizer.summarize_thread(stitched)
        final = final.model_copy(update={"thread_id": req.thread_id})
        return {
            "summary": final.model_dump(),
            "meta": {"mode": "map-reduce", "chunks": len(chunks)},
        }

    summary = summarizer.summarize_thread(content)
    summary = summary.model_copy(update={"thread_id": req.thread_id})
    return {"summary": summary.model_dump(), "meta": {"mode": "single"}}


# ----------------------------------------------------------------------
# RAG Endpoints
# ----------------------------------------------------------------------
@app.post("/v1/rag/index/thread")
def rag_index_thread(req: RAGIndexReq):
    cfg = GmailConfig(credentials_path=settings.GMAIL_CREDENTIALS, token_path=settings.GMAIL_TOKEN)
    data = get_thread_messages(thread_id=req.thread_id, cfg=cfg)
    items = []
    for m in data.get("messages", []):
        text = m.get("body") or ""
        if text.strip():
            items.append(
                {
                    "id": f"{req.thread_id}:{m.get('id')}",
                    "text": text,
                    "meta": {
                        "thread_id": req.thread_id,
                        "message_id": m.get("id"),
                        "subject": m.get("subject"),
                        "from": m.get("from"),
                        "date": m.get("date"),
                    },
                }
            )
    count = upsert_emails(items)
    return {"indexed": count, "thread_id": req.thread_id}


@app.post("/v1/rag/search")
def rag_search(req: RAGSearchReq):
    res = semantic_search(req.query, k=req.k)
    return {"query": req.query, "results": res}


# ----------------------------------------------------------------------
# Agentic Pipeline
# ----------------------------------------------------------------------
@app.post("/v1/agent/summarize")
def agent_summarize(req: AgentSummarizeReq):
    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    summarizer = GroqSummarizer(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
    app_graph = build_agent(summarizer)
    state: Dict[str, Any] = {}

    # Option A: thread mode
    if req.thread_id:
        cfg = GmailConfig(credentials_path=settings.GMAIL_CREDENTIALS, token_path=settings.GMAIL_TOKEN)
        data = get_thread_messages(thread_id=req.thread_id, cfg=cfg)
        raw = _flatten_thread_text(data)
        state["raw_text"] = raw
        items = []
        for m in data.get("messages", []):
            text = m.get("body") or ""
            if text.strip():
                items.append(
                    {
                        "id": f"{req.thread_id}:{m.get('id')}",
                        "text": text,
                        "meta": {
                            "thread_id": req.thread_id,
                            "message_id": m.get("id"),
                            "subject": m.get("subject"),
                            "from": m.get("from"),
                            "date": m.get("date"),
                        },
                    }
                )
        if items:
            upsert_emails(items)

    # Option B: query mode
    if req.query:
        state["query"] = req.query

    final_state = app_graph.invoke(state)
    summary = final_state.get("summary")
    if not summary:
        raise HTTPException(status_code=422, detail="Agent could not produce a summary")

    v = EmailSummaryV1(**summary)
    return {
        "summary": v.model_dump(),
        "agent": {"pipeline": ["retrieve", "summarize", "plan"], "model": settings.GROQ_MODEL},
    }


# ----------------------------------------------------------------------
# User-scoped (OAuth) Endpoints — enabled only if AUTH_ENABLED + AUTH_AVAILABLE
# ----------------------------------------------------------------------
if settings.AUTH_ENABLED and AUTH_AVAILABLE:

    @app.get("/v1/me/threads")
    def me_threads(limit: int = 8, user=Depends(current_user)):  # type: ignore
        svc = gmail_service_from_token_json(user.token_json)  # type: ignore
        res = svc.users().threads().list(userId="me", maxResults=limit, labelIds=["INBOX"]).execute()
        out = []
        for t in res.get("threads", []):
            tid = t["id"]
            meta = svc.users().threads().get(userId="me", id=tid, format="metadata").execute()
            msgs = meta.get("messages", [])
            headers = {h["name"].lower(): h["value"] for h in (msgs[0].get("payload", {}).get("headers", []) if msgs else [])}
            out.append(
                {
                    "thread_id": tid,
                    "subject": headers.get("subject", "(no subject)"),
                    "from": headers.get("from"),
                    "date": headers.get("date"),
                }
            )
        return {"threads": out}

    @app.post("/v1/me/summarize")
    def me_summarize(body: ThreadReq, user=Depends(current_user)):  # type: ignore
        cfg = GmailConfig(credentials_path=settings.GMAIL_CREDENTIALS, token_path=settings.GMAIL_TOKEN)
        thread = get_thread_messages(body.thread_id, cfg)
        content = _flatten_thread_text(thread)
        if not content.strip():
            raise HTTPException(status_code=422, detail="Thread has no readable text content")

        summarizer = GroqSummarizer(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
        if len(content) > 12000:
            chunks = _chunk_text(content)
            maps = [summarizer.summarize_chunk_to_bullets(c) for c in chunks]
            merged = _reduce_bullets(maps)
            stitched = _bullets_to_prompt_text(merged)
            final = summarizer.summarize_thread(stitched)
            final = final.model_copy(update={"thread_id": body.thread_id})
            sid = uuid.uuid4().hex
            save_summary(user.google_user_id, body.thread_id, final.subject, final.model_dump_json(), sid)
            return {"summary": final.model_dump(), "meta": {"mode": "map-reduce"}}

        final = summarizer.summarize_thread(content)
        final = final.model_copy(update={"thread_id": body.thread_id})
        sid = uuid.uuid4().hex
        save_summary(user.google_user_id, body.thread_id, final.subject, final.model_dump_json(), sid)
        return {"summary": final.model_dump(), "meta": {"mode": "single"}}


# ----------------------------------------------------------------------
# Root
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {"ok": True, "service": "Email Summarizer API"}

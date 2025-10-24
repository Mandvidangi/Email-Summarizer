from __future__ import annotations
import base64
from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

@dataclass
class GmailConfig:
    credentials_path: str
    token_path: str

def _get_service(cfg: GmailConfig):
    creds = None
    tp = Path(cfg.token_path)
    if tp.exists():
        creds = Credentials.from_authorized_user_file(cfg.token_path, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(cfg.credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        tp.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def search_threads(query: str, max_results: int, cfg: GmailConfig) -> List[str]:
    service = _get_service(cfg)
    resp = service.users().threads().list(userId="me", q=query, maxResults=max_results).execute()
    return [t["id"] for t in resp.get("threads", [])]

def _b64(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.extract()
    return soup.get_text(separator="\n", strip=True)

def get_thread_messages(thread_id: str, cfg: GmailConfig) -> Dict[str, Any]:
    service = _get_service(cfg)
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    out = []
    for msg in thread.get("messages", []):
        payload = msg.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date = headers.get("date", "")
        snippet = msg.get("snippet", "")

        body = ""
        # body in root?
        if payload.get("body", {}).get("data"):
            body = _b64(payload["body"]["data"])
        else:
            parts = payload.get("parts", []) or []
            # Try text/plain
            for p in parts:
                if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
                    body = _b64(p["body"]["data"])
                    break
            # Fallback: text/html → strip tags
            if not body:
                for p in parts:
                    if p.get("mimeType") == "text/html" and p.get("body", {}).get("data"):
                        body = _html_to_text(_b64(p["body"]["data"]))
                        break

        out.append({
            "id": msg.get("id", ""),
            "subject": subject,
            "from": sender,
            "date": date,
            "snippet": snippet,
            "body": body
        })
    return {"thread_id": thread_id, "messages": out}

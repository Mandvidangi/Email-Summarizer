from __future__ import annotations
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

from libs.rag.store import semantic_search
from libs.llm_client.groq import GroqSummarizer
from libs.schema.email_summary_v1 import EmailSummaryV1

# -------- State --------
class EmailState(TypedDict, total=False):
    query: str                # user query (semantic)
    thread_id: str            # optional direct thread id
    retrieved: List[Dict[str, Any]]  # retrieved docs (from RAG)
    raw_text: str             # compiled text (from retrieved or Gmail)
    summary: Dict[str, Any]   # EmailSummaryV1 dict

# -------- Nodes --------
def node_retrieve(state: EmailState) -> EmailState:
    """RAG retriever from ChromaDB."""
    q = state.get("query", "")
    if not q:
        return state
    res = semantic_search(q, k=5)
    items = []
    for doc, meta in zip(res["documents"], res["metadatas"]):
        items.append({"text": doc, "meta": meta})
    return {**state, "retrieved": items}

def node_summarize(state: EmailState, summarizer: GroqSummarizer) -> EmailState:
    """
    Summarize either:
     - raw_text if provided, else
     - join retrieved docs
    """
    text = state.get("raw_text") or "\n\n".join([f"Subject: {i['meta'].get('subject','')}\nFrom: {i['meta'].get('from','')}\nDate: {i['meta'].get('date','')}\nBody:\n{i['text']}\n---" for i in state.get("retrieved", [])])
    if not text.strip():
        return state

    m: EmailSummaryV1 = summarizer.summarize_thread(text)
    return {**state, "summary": m.model_dump()}

def node_plan_actions(state: EmailState) -> EmailState:
    """
    Simple 'agentic' planner (rule-based):
      - If subject or key_points contain 'alert', priority=low and who='System'
      - Else leave as is; summmarizer already produced actions
    """
    s = state.get("summary")
    if not s:
        return state
    subject = (s.get("subject") or "").lower()
    key_points = " ".join(s.get("key_points", [])).lower()
    if "alert" in subject or "alert" in key_points:
        actions = s.get("actions") or []
        if not actions:
            actions = [{"who": "System", "what": "Review alert", "due": None, "priority": "low"}]
            s["actions"] = actions
    return {**state, "summary": s}

# -------- Graph Builder --------
def build_agent(summarizer: GroqSummarizer):
    g = StateGraph(EmailState)
    # register nodes
    g.add_node("retrieve", node_retrieve)
    g.add_node("summarize", lambda st: node_summarize(st, summarizer))
    g.add_node("plan", node_plan_actions)

    # edges: START -> retrieve -> summarize -> plan -> END
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "summarize")
    g.add_edge("summarize", "plan")
    g.add_edge("plan", END)
    return g.compile()

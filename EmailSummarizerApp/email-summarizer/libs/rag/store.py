from __future__ import annotations
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

# One collection for email messages/snippets
_COLLECTION = "emails"

def get_client(persist_dir: str = ".chroma") -> chromadb.Client:
    # Persistent local store, telemetry off
    return chromadb.Client(Settings(is_persistent=True, anonymized_telemetry=False, persist_directory=persist_dir))

def get_collection(client=None):
    client = client or get_client()
    try:
        return client.get_collection(_COLLECTION)
    except:
        # Use Chroma's default embedding function (ONNX MiniLM via onnxruntime)
        return client.create_collection(_COLLECTION)

def upsert_emails(items: List[Dict[str, Any]], namespace: Optional[str] = None) -> int:
    """
    items: [{ id, text, meta: {...} }]
    meta should include: thread_id, message_id, subject, from, date
    """
    if not items:
        return 0
    ids = [i["id"] for i in items]
    texts = [i["text"] for i in items]
    metadatas = [i.get("meta", {}) for i in items]
    col = get_collection()
    # Let Chroma embed documents using its default ONNX EF
    col.upsert(ids=ids, documents=texts, metadatas=metadatas)
    return len(ids)

def semantic_search(query: str, k: int = 5, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    col = get_collection()
    # Let Chroma embed the query text internally (no manual embeddings)
    res = col.query(query_texts=[query], n_results=k, where=where or {})
    return {
        "ids": res.get("ids", [[]])[0],
        "documents": res.get("documents", [[]])[0],
        "metadatas": res.get("metadatas", [[]])[0],
        "distances": res.get("distances", [[]])[0] if "distances" in res else None,
    }

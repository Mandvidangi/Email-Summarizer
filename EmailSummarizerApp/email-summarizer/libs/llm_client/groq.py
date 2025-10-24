from __future__ import annotations
import json
import re
from typing import Dict, Any
from groq import Groq

from libs.schema.email_summary_v1 import EmailSummaryV1

SYSTEM = (
    "You are a precise email summarizer. "
    "Return ONLY valid JSON (no Markdown, no code fences). "
    "Use this exact schema and constraints:\n"
    "{"
    "  \"schema_version\": \"email_summary.v1\","
    "  \"thread_id\": \"STRING\","
    "  \"subject\": \"STRING\","
    "  \"participants\": [\"STRING\"],"
    "  \"dates\": [\"RFC3339\"],"
    "  \"key_points\": [\"STRING\"],"
    "  \"actions\": ["
    "    {\"who\":\"STRING\",\"what\":\"STRING\",\"due\":\"RFC3339|null\",\"priority\":\"low|medium|high\"}"
    "  ],"
    "  \"sentiment\": \"positive|neutral|negative|mixed\","
    "  \"confidence\": 0.0"
    "}"
)

USER_TMPL = (
    "Summarize the following email thread into the JSON schema. "
    "Rules:\n"
    "- Strict JSON only. No prose, no markdown.\n"
    "- If no due date, use null.\n"
    "- Confidence must be between 0.5 and 1.0 unless the content is an automated alert; then 0.2–0.5.\n"
    "- participants should be plain strings (emails or names), no angle brackets.\n"
    "- dates should be RFC3339 (e.g., 2025-10-18T12:00:00Z).\n\n"
    "THREAD (truncated if long):\n{content}"
)

def _coerce_json(s: str) -> Dict[str, Any]:
    """Strip code fences and parse the first JSON object found."""
    s = s.strip()
    s = re.sub(r"^```(json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))
        

class GroqSummarizer:

    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def summarize_thread(self, content: str) -> EmailSummaryV1:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER_TMPL.format(content=content[:12000])},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or "{}"
        data = _coerce_json(raw)

        # Post-process common quirks before validating
        # 1) participants like "Name <email@x>" -> remove angle brackets
        clean_parts = []
        for p in (data.get("participants") or []):
            p = re.sub(r"[<>]", "", str(p)).strip()
            clean_parts.append(p)
        data["participants"] = clean_parts

        # 2) clamp confidence to [0.2, 1.0] with sensible default
        conf = data.get("confidence", 0.7)
        try:
            conf = float(conf)
        except Exception:
            conf = 0.7
        data["confidence"] = max(0.2, min(1.0, conf))

        return EmailSummaryV1(**data)

    def summarize_chunk_to_bullets(self, content: str) -> dict[str, Any]:
        """
        Map step for long threads: extract key_points[] and actions[] only.
        Returns: {"key_points": [...], "actions": [{"who","what","due","priority"}, ...]}
        """
        map_system = (
            "Extract strictly-JSON bullets from an email chunk. "
            "Return ONLY: {\"key_points\": [\"STRING\"], "
            "\"actions\": [{\"who\":\"STRING\",\"what\":\"STRING\",\"due\":\"RFC3339|null\",\"priority\":\"low|medium|high\"}]}"
        )
        map_user = (
            "EMAIL CHUNK (may be partial):\n"
            f"{content[:3500]}"
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": map_system},
                      {"role": "user", "content": map_user}],
            temperature=0.1,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content or "{}"
        data = _coerce_json(raw)

        # normalize actions fields
        actions = []
        for a in (data.get("actions") or []):
            actions.append({
                "who": (a.get("who") or "Unassigned").strip(),
                "what": (a.get("what") or "").strip(),
                "due": a.get("due") if a.get("due") else None,
                "priority": (a.get("priority") or "medium").lower(),
            })
        return {
            "key_points": [str(k).strip() for k in (data.get("key_points") or []) if str(k).strip()],
            "actions": actions,
        }

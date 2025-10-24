from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator
import json
import sys
from datetime import datetime

SchemaVersion = Literal["email_summary.v1"]
Sentiment = Literal["positive", "neutral", "negative", "mixed"]
Priority = Literal["low", "medium", "high"]

class ActionItem(BaseModel):
    who: str = Field(..., min_length=1)
    what: str = Field(..., min_length=1)
    due: Optional[str] = Field(default=None, description="RFC3339 date or null")
    priority: Optional[Priority] = "medium"

    @field_validator("due")
    @classmethod
    def validate_due(cls, v):
        if v is None:
            return v
        try:
            # basic RFC3339-ish check
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError("due must be RFC3339 or null") from e
        return v

class EmailSummaryV1(BaseModel):
    schema_version: SchemaVersion = "email_summary.v1"
    thread_id: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    participants: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list, description="List of RFC3339 timestamps")
    key_points: List[str] = Field(default_factory=list)
    actions: List[ActionItem] = Field(default_factory=list)
    sentiment: Sentiment = "neutral"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)

    @field_validator("dates")
    @classmethod
    def validate_dates(cls, v):
        for d in v:
            try:
                datetime.fromisoformat(d.replace("Z", "+00:00"))
            except Exception as e:
                raise ValueError("dates must be RFC3339 strings") from e
        return v

def example() -> EmailSummaryV1:
    return EmailSummaryV1(
        thread_id="1850abCxyz",
        subject="Project Update: Q3 Timeline",
        participants=["alice@example.com", "bob@example.com"],
        dates=["2025-10-01T10:00:00Z", "2025-10-02T18:30:00Z"],
        key_points=[
            "Phase-1 complete, blocked on API keys",
            "Need UX approval for dashboard copy",
        ],
        actions=[
            ActionItem(who="Alice", what="Share API key rotation plan", due="2025-10-20T00:00:00Z", priority="high"),
            ActionItem(who="Bob", what="Draft dashboard copy v2", due=None, priority="medium"),
        ],
        sentiment="mixed",
        confidence=0.82,
    )

if __name__ == "__main__":
    if "--export-json-schema" in sys.argv:
        schema = EmailSummaryV1.model_json_schema()
        with open("email_summary_v1.schema.json", "w") as f:
            json.dump(schema, f, indent=2)
        print("Exported email_summary_v1.schema.json")
    elif "--print-example" in sys.argv:
        print(example().model_dump_json(indent=2))

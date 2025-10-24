# libs/db/model.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, ForeignKey, Index, text

Base = declarative_base()


class User(Base):
    """Represents a Google user who has authenticated with the app."""
    __tablename__ = "users"

    google_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    token_json: Mapped[str] = mapped_column(Text)

    summaries: Mapped[List["Summary"]] = relationship("Summary", back_populates="user")


class AppSession(Base):
    """Stores app tokens that map to authenticated users."""
    __tablename__ = "app_sessions"

    app_token: Mapped[str] = mapped_column(String(128), primary_key=True)
    google_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.google_user_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))


class Summary(Base):
    """Stores the summarized email thread results."""
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    google_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.google_user_id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    subject: Mapped[str] = mapped_column(String(512))
    summary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"))

    user: Mapped["User"] = relationship("User", back_populates="summaries")


# helpful indexes
Index("ix_summaries_user_thread", Summary.google_user_id, Summary.thread_id)
Index("ix_sessions_user", AppSession.google_user_id)

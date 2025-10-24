# libs/db/repo.py
from __future__ import annotations
from contextlib import contextmanager
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from libs.db.session import SessionLocal, engine
from libs.db.model import Base, User, AppSession, Summary


# --------------------------------------------------------------------------
# DB Initialization
# --------------------------------------------------------------------------
def init_db() -> None:
    """Create all tables if they don’t exist."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Session:
    """Provide a transactional scope for DB operations."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --------------------------------------------------------------------------
# User & Session Management
# --------------------------------------------------------------------------
def upsert_user_token(*, google_user_id: str, email: str, name: str, token_json: str) -> User:
    """Insert or update user OAuth credentials."""
    with get_db() as db:
        user = db.get(User, google_user_id)
        if user is None:
            user = User(
                google_user_id=google_user_id,
                email=email,
                name=name,
                token_json=token_json,
            )
            db.add(user)
        else:
            user.email = email
            user.name = name
            user.token_json = token_json
        db.flush()
        return user


def get_user_by_google_id(google_user_id: str) -> Optional[User]:
    with get_db() as db:
        return db.get(User, google_user_id)


def set_app_session(app_token: str, google_user_id: str) -> None:
    """Store a bearer token that maps to a user."""
    with get_db() as db:
        existing = db.get(AppSession, app_token)
        if existing:
            existing.google_user_id = google_user_id
            existing.created_at = datetime.utcnow()
        else:
            db.add(AppSession(app_token=app_token, google_user_id=google_user_id))
        db.flush()


def get_user_by_app_token(app_token: str) -> Optional[User]:
    """Resolve a bearer token → User."""
    with get_db() as db:
        sess = db.get(AppSession, app_token)
        if not sess:
            return None
        return db.get(User, sess.google_user_id)


def delete_session(app_token: str) -> None:
    """Remove a stored session."""
    with get_db() as db:
        db.execute(delete(AppSession).where(AppSession.app_token == app_token))


# --------------------------------------------------------------------------
# Summaries Management
# --------------------------------------------------------------------------
def save_summary(
    google_user_id: str,
    thread_id: str,
    subject: str,
    summary_json: str,
    summary_id: str,
) -> Summary:
    """Persist a new email summary."""
    with get_db() as db:
        summary = Summary(
            id=summary_id,
            google_user_id=google_user_id,
            thread_id=thread_id,
            subject=subject,
            summary_json=summary_json,
            created_at=datetime.utcnow(),  # fix for NOT NULL constraint
        )
        db.add(summary)
        db.flush()
        return summary


def list_summaries(google_user_id: str, limit: int = 10) -> List[Summary]:
    """Get recent summaries for a user."""
    with get_db() as db:
        stmt = (
            select(Summary)
            .where(Summary.google_user_id == google_user_id)
            .order_by(Summary.created_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())


def get_latest_summary_for_thread(google_user_id: str, thread_id: str) -> Optional[Summary]:
    """Retrieve the most recent summary for a thread."""
    with get_db() as db:
        stmt = (
            select(Summary)
            .where(
                Summary.google_user_id == google_user_id,
                Summary.thread_id == thread_id,
            )
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        return db.execute(stmt).scalars().first()

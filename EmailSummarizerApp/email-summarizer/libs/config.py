# libs/config.py
from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _get_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}

def _get_int(key: str, default: int) -> int:
    v = os.getenv(key)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default

@dataclass
class Settings:
    # === LLM / Groq ===
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # === Gmail (service acct / local single-user) ===
    GMAIL_CREDENTIALS: str = os.getenv("GMAIL_CREDENTIALS", "credentials.json")
    GMAIL_TOKEN: str = os.getenv("GMAIL_TOKEN", "token.json")

    # === OAuth (multi-user, Web client) ===
    GOOGLE_WEB_CREDENTIALS: str | None = os.getenv("GOOGLE_WEB_CREDENTIALS", "web_credentials.json")
    GOOGLE_OAUTH_REDIRECT_URI: str | None = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://127.0.0.1:8080/auth/google/callback",
    )

    # === UI base URL (Next.js) ===
    UI_URL: str = os.getenv("UI_URL", "http://localhost:3000")

    # === Database (SQLite by default; override for Postgres) ===
    # SQLite example: sqlite:///./data.db
    # Postgres example: postgresql+psycopg2://app:app@127.0.0.1:5432/email_summarizer
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data.db")

    # === App Auth toggles ===
    AUTH_ENABLED: bool = _get_bool("AUTH_ENABLED", False)
    JWT_SECRET: str | None = os.getenv("JWT_SECRET", None)
    JWT_EXPIRES: int = _get_int("JWT_EXPIRES", 86400)  # seconds

    # === Back-compat (some older modules might read DB_URL) ===
    DB_URL: str = os.getenv("DB_URL", "")

    # Convenience flags (derived)
    @property
    def GROQ_ENABLED(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def GOOGLE_WEB_CREDENTIALS_EXISTS(self) -> bool:
        return bool(self.GOOGLE_WEB_CREDENTIALS and os.path.exists(self.GOOGLE_WEB_CREDENTIALS))

    @property
    def GMAIL_CREDS_EXISTS(self) -> bool:
        return os.path.exists(self.GMAIL_CREDENTIALS)

    @property
    def GMAIL_TOKEN_EXISTS(self) -> bool:
        return os.path.exists(self.GMAIL_TOKEN)

# singleton
settings = Settings()

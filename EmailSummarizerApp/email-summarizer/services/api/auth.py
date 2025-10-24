from __future__ import annotations
import os
import secrets
import urllib.parse

from fastapi import APIRouter, Request, HTTPException
from starlette.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from libs.config import settings
from libs.db.repo import upsert_user_token, set_app_session

# --- Recommended for local dev (HTTP callback + relaxed scope comparison) ---
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# --- Use the exact scopes Google returns to avoid "scope changed" errors ---
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]

router = APIRouter(prefix="/auth/google", tags=["auth"])


def _flow() -> Flow:
    """
    Build the OAuth flow using the Web Client credentials.
    Make sure:
      - GOOGLE_WEB_CREDENTIALS points to your downloaded web client JSON (e.g., web_credentials.json)
      - GOOGLE_OAUTH_REDIRECT_URI matches the Authorized redirect URI in Google Cloud Console
    """
    return Flow.from_client_secrets_file(
        settings.GOOGLE_WEB_CREDENTIALS,
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
    )


@router.get("/login")
def login():
    flow = _flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",             # get refresh_token
        include_granted_scopes="true",     # incremental auth
        prompt="consent",                  # always show consent to ensure refresh_token on dev
    )
    # (In production, bind `state` to a server-side session/CSRF token.)
    return RedirectResponse(auth_url)


@router.get("/callback")
def callback(request: Request, state: str | None = None, code: str | None = None):
    if not code:
        raise HTTPException(400, "Missing code")

    flow = _flow()
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        # Most common issue during dev: scope string mismatch.
        # We already set OAUTHLIB_RELAX_TOKEN_SCOPE=1 above, and scopes now match Google's.
        # If it still fails, surface a clear error.
        raise HTTPException(
            status_code=400,
            detail=f"OAuth token exchange failed: {type(e).__name__}: {e}",
        )

    creds = flow.credentials  # has access_token, refresh_token, id_token

    # Parse user identity from id_token (JWT)
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as greq

        info = id_token.verify_oauth2_token(creds.id_token, greq.Request())
    except Exception as e:
        raise HTTPException(400, f"Failed to verify id_token: {type(e).__name__}: {e}")

    google_user_id = info.get("sub")
    email = info.get("email")
    name = info.get("name") or email

    if not google_user_id or not email:
        raise HTTPException(400, "Missing user identity in id_token")

    # Store/refresh the user's token JSON in DB
    upsert_user_token(
        google_user_id=google_user_id,
        email=email,
        name=name,
        token_json=creds.to_json(),
    )

    # Issue an app session token (for the UI) and store mapping in DB
    app_token = secrets.token_urlsafe(32)
    set_app_session(app_token, google_user_id)

    # Redirect to the UI with the session token (UI will read ?token= and call /v1/me/*)
    ui = settings.UI_URL.rstrip("/")
    return RedirectResponse(f"{ui}/app?token={urllib.parse.quote(app_token)}")

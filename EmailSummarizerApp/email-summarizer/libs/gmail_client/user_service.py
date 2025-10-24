from __future__ import annotations
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def gmail_service_from_token_json(token_json: str):
    data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(data)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

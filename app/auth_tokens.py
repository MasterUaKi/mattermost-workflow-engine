# Author: Oleh Riabtsev
# File: app/auth_tokens.py
# Created: 2026-11-23
# Version: 1.0.0

"""
Stateless HMAC-SHA256 token signer and verifier for authenticating Mattermost users
when they open the Visual Workflow Studio from a Direct Message link.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from app.config import Settings


def _get_signing_secret(settings: Settings) -> bytes:
    """Derives an HMAC signing key from webhook secret or bot token."""
    raw_secret = settings.MATTERMOST_WEBHOOK_SECRET or settings.MATTERMOST_BOT_TOKEN
    return raw_secret.encode("utf-8")


def create_studio_session_token(
    settings: Settings,
    *,
    user_id: str,
    username: str,
    ttl_seconds: int = 43200,
) -> str:
    """Generates a URL-safe signed session token valid for 12 hours by default."""
    payload = {
        "uid": user_id,
        "uname": username,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    signature = hmac.new(
        _get_signing_secret(settings),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_payload}.{signature}"


def verify_studio_session_token(settings: Settings, token: str) -> dict[str, Any] | None:
    """Validates signature and expiration of a Studio session token."""
    if not token or "." not in token:
        return None

    encoded_payload, provided_sig = token.rsplit(".", 1)
    expected_sig = hmac.new(
        _get_signing_secret(settings),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    # Restore base64 padding
    padding = "=" * ((4 - len(encoded_payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(encoded_payload + padding).decode("utf-8")
        data = json.loads(decoded)
    except Exception:
        return None

    if int(data.get("exp", 0)) < int(time.time()):
        return None

    if not data.get("uid"):
        return None

    return {
        "user_id": str(data["uid"]),
        "username": str(data.get("uname") or data["uid"]),
    }

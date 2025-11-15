from __future__ import annotations

"""Utility helpers for Schwab OAuth/token management used by CLI and Streamlit UI."""

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse, quote_plus

import requests
from schwab import auth

DEFAULT_CALLBACK_URL = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
DEFAULT_TOKEN_PATH = os.environ.get("SCHWAB_TOKEN_PATH", "./schwab_token.json")


def _resolve_token_path(token_path: str | None) -> str:
    path = token_path or DEFAULT_TOKEN_PATH
    return str(Path(path).expanduser())


def load_token_file(token_path: str | None = None) -> Dict[str, Any]:
    """Load schwab_token.json (if present)."""
    resolved = _resolve_token_path(token_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(resolved)
    with open(resolved, "r", encoding="utf-8") as f:
        return json.load(f)


def token_status(token_path: str | None = None) -> Dict[str, Any]:
    """Return metadata about the stored token."""
    resolved = _resolve_token_path(token_path)
    if not os.path.exists(resolved):
        return {"exists": False, "error": "Token file not found", "token_path": resolved}
    try:
        data = load_token_file(resolved)
        token = data.get("token", {})
        expires_at = token.get("expires_at")
        if not expires_at:
            return {"exists": True, "error": "Token expiration missing", "token_path": resolved}
        now_ts = time.time()
        minutes_remaining = (expires_at - now_ts) / 60.0
        expires_dt = datetime.fromtimestamp(expires_at)
        status = {
            "exists": True,
            "expires_at": expires_at,
            "expires_datetime": expires_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "minutes_remaining": minutes_remaining,
            "hours_remaining": minutes_remaining / 60.0,
            "is_expired": minutes_remaining <= 0,
        }
        if not token.get("refresh_token"):
            status["error"] = "Refresh token missing. Re-run Schwab OAuth to regenerate tokens."
        status["token_path"] = resolved
        return status
    except Exception as exc:  # pragma: no cover - defensive
        return {"exists": True, "error": f"Failed to read token: {exc}", "token_path": resolved}


def _backup_existing_token(resolved_path: str) -> str | None:
    if not os.path.exists(resolved_path):
        return None
    backup_path = resolved_path + ".bak"
    shutil.copy(resolved_path, backup_path)
    return backup_path


def save_token_file(
    tokens: Dict[str, Any],
    token_path: str | None = None,
    creation_ts: float | None = None,
) -> Dict[str, Any]:
    """Persist Schwab tokens to disk (schwab-py compatible format)."""
    resolved = _resolve_token_path(token_path)
    os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
    now_ts = int(creation_ts or time.time())
    token_data = {
        "creation_timestamp": now_ts,
        "token": {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens["expires_in"],
            "expires_at": now_ts + int(tokens["expires_in"]),
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope", "api"),
        },
    }
    if "id_token" in tokens:
        token_data["token"]["id_token"] = tokens["id_token"]

    backup_path = _backup_existing_token(resolved)
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    expires_at = token_data["token"]["expires_at"]
    expires_dt = datetime.fromtimestamp(expires_at)
    minutes_remaining = (expires_at - time.time()) / 60.0
    summary = {
        "token_path": resolved,
        "token_data": token_data,
        "expires_at": expires_at,
        "expires_datetime": expires_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "minutes_remaining": minutes_remaining,
        "hours_remaining": minutes_remaining / 60.0,
    }
    if backup_path:
        summary["backup_path"] = backup_path
    return summary


def build_authorization_url(api_key: str, callback_url: str | None = None) -> str:
    cb = callback_url or DEFAULT_CALLBACK_URL
    return (
        "https://api.schwabapi.com/v1/oauth/authorize?client_id="
        f"{api_key}&redirect_uri={quote_plus(cb)}"
    )


def parse_auth_code(callback_response: str) -> str:
    if not callback_response:
        raise ValueError("No redirect URL provided")
    parsed = urlparse(callback_response.strip())
    params = parse_qs(parsed.query)
    if "code" not in params:
        raise ValueError("Authorization code not found in redirect URL")
    return params["code"][0]


def exchange_code_for_tokens(
    api_key: str,
    app_secret: str,
    callback_url: str,
    auth_code: str,
) -> Dict[str, Any]:
    token_url = "https://api.schwabapi.com/v1/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": callback_url,
    }
    response = requests.post(
        token_url,
        data=payload,
        auth=(api_key, app_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed ({response.status_code}): {response.text[:200]}"
        )
    return response.json()


def complete_manual_oauth(
    api_key: str,
    app_secret: str,
    callback_url: str,
    token_path: str,
    callback_response: str,
) -> Dict[str, Any]:
    auth_code = parse_auth_code(callback_response)
    tokens = exchange_code_for_tokens(api_key, app_secret, callback_url, auth_code)
    summary = save_token_file(tokens, token_path)
    summary.update({"success": True, "auth_code_preview": auth_code[:10]})
    return summary


def refresh_token_file(
    api_key: str,
    app_secret: str,
    token_path: str | None = None,
) -> Dict[str, Any]:
    resolved = _resolve_token_path(token_path)
    if not os.path.exists(resolved):
        return {
            "success": False,
            "message": "Token file not found. Please authenticate first.",
            "needs_reauth": True,
        }
    try:
        old_data = load_token_file(resolved)
        old_expires = old_data.get("token", {}).get("expires_at", 0)
    except Exception as exc:
        return {"success": False, "message": f"Invalid token file: {exc}", "needs_reauth": True}

    try:
        auth.client_from_token_file(resolved, api_key, app_secret)
    except Exception as exc:
        msg = str(exc)
        lower = msg.lower()
        # Treat explicit invalid/expired responses as requiring full re-auth
        hard_markers = ("invalid_grant", "invalid token", "invalid refresh", "refresh token is expired")
        soft_markers = ("temporarily_unavailable", "timeout", "connection", "network", "rate limit", "too many requests")

        if any(m in lower for m in hard_markers):
            needs_reauth = True
        elif any(m in lower for m in soft_markers):
            needs_reauth = False
        else:
            # Default to non-fatal unless clearly signaled otherwise
            needs_reauth = False

        return {
            "success": False,
            "message": f"Token refresh failed: {exc}",
            "error_detail": msg,
            "needs_reauth": needs_reauth,
        }

    try:
        new_data = load_token_file(resolved)
    except Exception as exc:  # pragma: no cover - unexpected IO error
        return {"success": False, "message": f"Failed to read refreshed token: {exc}"}

    new_expires = new_data.get("token", {}).get("expires_at", 0)
    now_ts = time.time()
    minutes_remaining = (new_expires - now_ts) / 60.0 if new_expires else -1

    # If Schwab wrote a new token with a non-decreasing expiry, treat it as success.
    # Some environments may preserve the same expires_at across refreshes; that's fine
    # as long as the access token itself is still accepted by the API.
    if not new_expires:
        return {
            "success": False,
            "message": "Token refresh did not return a new expiration timestamp.",
            "needs_reauth": False,
        }

    if new_expires < old_expires:
        return {
            "success": False,
            "message": "Refreshed token expires earlier than previous token.",
            "needs_reauth": True,
        }

    return {
        "success": True,
        "message": "Token refreshed successfully",
        "new_expiration": datetime.fromtimestamp(new_expires).strftime("%Y-%m-%d %H:%M:%S"),
        "minutes_remaining": minutes_remaining,
        "hours_remaining": minutes_remaining / 60.0,
    }


def reset_token_file(token_path: str | None = None) -> Dict[str, Any]:
    """Delete/backup the token file so a fresh OAuth flow can run."""
    resolved = _resolve_token_path(token_path)
    if not os.path.exists(resolved):
        return {"success": True, "message": "No token file to remove."}
    backup_path = resolved + ".bak"
    shutil.move(resolved, backup_path)
    return {"success": True, "message": "Token file reset.", "backup_path": backup_path}

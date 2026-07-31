"""
Unit tests for services/auth.py — the merged Telegram identity module.

Covers the three behaviors at this seam:
  1. External Mini App auth (get-or-create User from initData "user=" payload)
  2. Internal listener bypass (plain telegram_id integer + X-Internal-Service)
  3. Cryptographic initData verification (HMAC-SHA256, used by reviews)

Error-message contract (from the architecture deepening blueprint):
  - external path, no "user=" in init_data
      -> 403 "Restricted: Alerts can only be managed from inside the Telegram Mini App."
  - other auth failures                          -> 403 "Authentication Failed"
  - verify_init_data without BOT_TOKEN           -> 500 "Server config error: Missing Bot Token"
  - verify_init_data invalid signature           -> 401 "Authentication Failed: Invalid Signature"
"""

import hashlib
import hmac
import json
from urllib.parse import quote

import pytest
from fastapi import HTTPException

from models import User
from services.auth import authenticate, verify_init_data


def _make_init_data(telegram_id, username="tester", **extra):
    """Fake Mini App init_data: user=<url-encoded JSON> (same shape as the webapp)."""
    user_json = json.dumps({"id": telegram_id, "username": username, **extra})
    return f"user={quote(user_json)}"


def _make_crypto_init_data(user_data, bot_token):
    """Build a cryptographically VALID initData string for a known bot token."""
    data = {
        "query_id": "q123",
        "user": json.dumps(user_data),
        "auth_date": "1700000000",
        "chat_instance": "ci1",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return "&".join(f"{k}={quote(v)}" for k, v in data.items())


# =========================================================================
# EXTERNAL PATH — Mini App initData auth
# =========================================================================

def test_authenticate_external_auto_registers_user(db_session):
    """A first-time Mini App user is auto-registered with telegram_id + username."""
    user = authenticate(_make_init_data(111, username="first_timer"), db_session)

    assert isinstance(user, User)
    assert user.telegram_id == 111
    assert user.username == "first_timer"

    count = db_session.scalar(select_count())
    assert count == 1


def test_authenticate_external_reuses_existing_user(db_session):
    """A returning user is looked up, not duplicated."""
    first = authenticate(_make_init_data(222, username="returning"), db_session)
    second = authenticate(_make_init_data(222, username="returning"), db_session)

    assert first.id == second.id
    assert db_session.scalar(select_count()) == 1


# =========================================================================
# INTERNAL BYPASS — index-listener service
# =========================================================================

def test_authenticate_internal_bypass_plain_integer(db_session):
    """X-Internal-Service == 'index-listener' + digit init_data bypasses the Mini App check."""
    user = authenticate("333", db_session, x_internal_service="index-listener")

    assert user.telegram_id == 333
    assert db_session.scalar(select_count()) == 1


def test_authenticate_internal_with_user_payload_still_parses(db_session):
    """Internal caller with a real user payload goes through the normal parse path."""
    user = authenticate(_make_init_data(444), db_session, x_internal_service="index-listener")

    assert user.telegram_id == 444
    assert user.username == "tester"


# =========================================================================
# FAILURE MODES — exact error messages
# =========================================================================

def test_authenticate_missing_user_restricted_message(db_session):
    """External request without 'user=' gets the Mini-App-only restriction message."""
    with pytest.raises(HTTPException) as exc_info:
        authenticate("hash=abc&auth_date=123", db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Restricted: Alerts can only be managed from inside the Telegram Mini App."
    )


def test_authenticate_malformed_user_json_generic_message(db_session):
    """Malformed user JSON falls back to the generic failure message."""
    with pytest.raises(HTTPException) as exc_info:
        authenticate("user=notjson", db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Authentication Failed"


# =========================================================================
# CRYPTOGRAPHIC VERIFICATION — reviews initData (HMAC-SHA256)
# =========================================================================

def test_verify_init_data_valid_signature(monkeypatch):
    """Correct HMAC-SHA256 signature passes and returns the parsed user dict."""
    token = "12345:TESTTOKEN"
    monkeypatch.setattr("services.auth.BOT_TOKEN", token)

    user_data = {"id": 777, "username": "crypto_user", "photo_url": "https://t.me/x.jpg"}
    result = verify_init_data(_make_crypto_init_data(user_data, token))

    assert result == user_data


def test_verify_init_data_invalid_signature(monkeypatch):
    """Tampered hash is rejected with the exact 401 message."""
    token = "12345:TESTTOKEN"
    monkeypatch.setattr("services.auth.BOT_TOKEN", token)

    init_data = _make_crypto_init_data({"id": 777, "username": "crypto_user"}, token)
    # Tamper with the payload AFTER signing: username differs from the signed value.
    tampered = init_data.replace("crypto_user", "crypto_hacker")

    with pytest.raises(HTTPException) as exc_info:
        verify_init_data(tampered)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication Failed: Invalid Signature"


def test_verify_init_data_missing_token(monkeypatch):
    """Server misconfiguration (no BOT_TOKEN) surfaces as a 500."""
    monkeypatch.setattr("services.auth.BOT_TOKEN", None)

    with pytest.raises(HTTPException) as exc_info:
        verify_init_data("user=%7B%7D")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Server config error: Missing Bot Token"


def select_count():
    from sqlalchemy import func, select

    return select(func.count()).select_from(User)

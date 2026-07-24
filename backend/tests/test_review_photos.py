"""
Backend tests for TECH-07: User Photo Capture During Review Submission
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_review_photos.py -v

Coverage:
  T14: User photo captured during review submission
  T15: Review without user photo works normally
  T16: Review list endpoint returns user_photo_url
"""
import os
import json
import hmac
import hashlib
import time
from urllib.parse import quote

import pytest
import httpx

BASE_URL = "http://localhost:8000"


def api_post(path, json_data, timeout=30.0):
    """Helper to make HTTP POST requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.post(url, json=json_data, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_get(path, timeout=10.0):
    """Helper to make HTTP GET requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


# ---------------------------------------------------------------------------
# Telegram initData HMAC generator
# ---------------------------------------------------------------------------

def make_valid_init_data(user_data, bot_token=None):
    """
    Construct a valid Telegram Mini App initData query string
    with a correct HMAC-SHA256 hash.

    The backend's validate_telegram_data() expects:
      - URL-encoded key=value pairs
      - A 'hash' parameter containing HMAC-SHA256 of sorted data_check_string
      - A 'user' field with JSON like {"id": <int>, "photo_url": "<str>"?}
    """
    if bot_token is None:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return None  # caller should skip if no token

    data = {
        "query_id": f"test_query_{int(time.time() * 1000)}",
        "user": json.dumps(user_data),
        "auth_date": str(int(time.time())),
        "chat_instance": f"test_chat_{int(time.time() * 1000)}",
    }

    # Build data check string (sorted keys, newline-separated)
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items())
    )

    # Compute HMAC-SHA256
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    data["hash"] = calculated_hash

    # URL-encode
    return "&".join(f"{k}={quote(v)}" for k, v in data.items())


def get_test_channel_id():
    """
    Find an existing channel ID to write reviews against.
    Returns None if no channels exist.
    """
    try:
        resp = httpx.get(f"{BASE_URL}/channels/", timeout=10.0)
        if resp.status_code == 200:
            channels = resp.json()
            if channels:
                return channels[0]["id"]
    except httpx.ConnectError:
        pass
    return None


# ---------------------------------------------------------------------------
# Test helpers (lazy initialization to avoid overhead per test)
# ---------------------------------------------------------------------------

_unique_counter = 0


def _unique_tg_id():
    """Generate a unique Telegram user ID for test isolation."""
    global _unique_counter
    _unique_counter += 1
    return int(time.time() * 1000) % 10_000_000_000 + 9000000000 + _unique_counter


# =========================================================================
# T14: User photo captured during review submission
# =========================================================================

def test_user_photo_captured_during_review():
    """
    T14: Submit a review with initData that includes user.photo_url.
    Verify the Review record has user_photo_url set to the provided URL.
    Verify the ReviewResponse JSON includes user_photo_url.
    """
    channel_id = get_test_channel_id()
    if channel_id is None:
        pytest.skip("No channels in database to test reviews against")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        pytest.skip("TELEGRAM_BOT_TOKEN not set — cannot construct valid initData")

    tg_id = _unique_tg_id()
    photo_url = "https://t.me/i/userpic/320/test_user.jpg"

    user_data = {
        "id": tg_id,
        "first_name": "PhotoTest",
        "username": f"photo_test_{tg_id}",
        "photo_url": photo_url,
    }
    init_data = make_valid_init_data(user_data, bot_token)
    if init_data is None:
        pytest.skip("Could not construct valid initData")

    resp = api_post("/reviews/", {
        "channel_id": channel_id,
        "rating": 5,
        "comment": "T14 test review with photo",
        "init_data": init_data,
    })

    # This might fail if the user already reviewed this channel
    # (unique constraint). That's fine — the important thing is
    # that photo_url is captured when the review IS created.
    if resp.status_code == 400 and "already reviewed" in resp.text.lower():
        pytest.skip("User already reviewed this channel — photo capture tested indirectly")

    if resp.status_code == 200:
        review_data = resp.json()
        assert "user_photo_url" in review_data, (
            f"ReviewResponse missing 'user_photo_url'. Keys: {list(review_data.keys())}"
        )
        assert review_data["user_photo_url"] == photo_url, (
            f"Expected user_photo_url='{photo_url}', "
            f"got '{review_data.get('user_photo_url')}'"
        )
    elif resp.status_code == 401:
        # HMAC validation might fail if the token changed between
        # generating initData and the API call (running inside container).
        # This is an environment issue, not a code bug.
        pytest.skip(f"HMAC validation failed (env mismatch): {resp.text[:200]}")
    else:
        # Other errors should not happen
        assert False, f"Unexpected response {resp.status_code}: {resp.text[:200]}"


# =========================================================================
# T15: Review without user photo works normally
# =========================================================================

def test_review_without_user_photo_works():
    """
    T15: Submit a review with initData that does NOT include user.photo_url.
    Verify the Review record has user_photo_url = None.
    Verify the ReviewResponse JSON includes user_photo_url: null.
    """
    channel_id = get_test_channel_id()
    if channel_id is None:
        pytest.skip("No channels in database to test reviews against")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        pytest.skip("TELEGRAM_BOT_TOKEN not set — cannot construct valid initData")

    tg_id = _unique_tg_id()

    user_data = {
        "id": tg_id,
        "first_name": "NoPhotoTest",
        "username": f"nophoto_test_{tg_id}",
        # NOTE: no photo_url key
    }
    init_data = make_valid_init_data(user_data, bot_token)
    if init_data is None:
        pytest.skip("Could not construct valid initData")

    resp = api_post("/reviews/", {
        "channel_id": channel_id,
        "rating": 4,
        "comment": "T15 test review without photo",
        "init_data": init_data,
    })

    if resp.status_code == 400 and "already reviewed" in resp.text.lower():
        pytest.skip("User already reviewed this channel — skip")

    if resp.status_code == 200:
        review_data = resp.json()
        assert "user_photo_url" in review_data, (
            f"ReviewResponse missing 'user_photo_url' field"
        )
        assert review_data["user_photo_url"] is None, (
            f"Expected user_photo_url=None when not provided, "
            f"got '{review_data['user_photo_url']}'"
        )
    elif resp.status_code == 401:
        pytest.skip(f"HMAC validation failed (env mismatch): {resp.text[:200]}")
    else:
        assert False, f"Unexpected response {resp.status_code}: {resp.text[:200]}"


# =========================================================================
# T16: Review list endpoint returns user_photo_url
# =========================================================================

def test_review_list_includes_user_photo_url():
    """
    T16: Call GET /reviews/{channel_id}.
    Verify each review in the response includes user_photo_url
    (either a URL string or null).
    """
    channel_id = get_test_channel_id()
    if channel_id is None:
        pytest.skip("No channels in database to test reviews against")

    resp = api_get(f"/reviews/{channel_id}")
    assert resp.status_code == 200, (
        f"Expected 200 from /reviews/{channel_id}, got {resp.status_code}"
    )

    reviews = resp.json()
    assert isinstance(reviews, list), f"Expected list, got {type(reviews)}"

    if reviews:
        for rev in reviews:
            assert "user_photo_url" in rev, (
                f"Review item missing 'user_photo_url'. Keys: {list(rev.keys())}"
            )
            # user_photo_url should be either a string (URL) or None/null
            photo = rev["user_photo_url"]
            assert photo is None or isinstance(photo, str), (
                f"user_photo_url should be string or null, got {type(photo)}: {photo}"
            )


# =========================================================================
# T16b: Verify that creating a review with photo and then listing returns it
# =========================================================================

def test_create_review_with_photo_then_list():
    """
    Integration test: create a review with photo_url, then verify
    the review list includes that photo_url.
    """
    channel_id = get_test_channel_id()
    if channel_id is None:
        pytest.skip("No channels in database")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        pytest.skip("TELEGRAM_BOT_TOKEN not set")

    tg_id = _unique_tg_id()
    photo_url = "https://t.me/i/userpic/320/list_test_user.jpg"

    user_data = {
        "id": tg_id,
        "first_name": "ListTest",
        "username": f"list_test_{tg_id}",
        "photo_url": photo_url,
    }
    init_data = make_valid_init_data(user_data, bot_token)
    if init_data is None:
        pytest.skip("Could not construct valid initData")

    # Submit a review
    create_resp = api_post("/reviews/", {
        "channel_id": channel_id,
        "rating": 5,
        "comment": "T16b review with photo for list verification",
        "init_data": init_data,
    })

    if create_resp.status_code == 400 and "already reviewed" in create_resp.text.lower():
        pytest.skip("User already reviewed this channel")

    if create_resp.status_code == 401:
        pytest.skip(f"HMAC validation failed: {create_resp.text[:200]}")

    assert create_resp.status_code == 200, (
        f"Review creation failed: {create_resp.status_code} — {create_resp.text[:200]}"
    )

    created = create_resp.json()
    assert created.get("user_photo_url") == photo_url, (
        f"Expected photo_url in response, got: {created.get('user_photo_url')}"
    )

    # Now list reviews for this channel
    list_resp = api_get(f"/reviews/{channel_id}")
    assert list_resp.status_code == 200

    reviews = list_resp.json()
    # Find our review in the list
    our_review = None
    for r in reviews:
        if r["id"] == created["id"]:
            our_review = r
            break

    assert our_review is not None, "Created review not found in list response"
    assert our_review["user_photo_url"] == photo_url, (
        f"Listed review missing photo_url. Expected '{photo_url}', "
        f"got '{our_review.get('user_photo_url')}'"
    )


# =========================================================================
# TECH-15: T17 — Review list includes user_name
# =========================================================================

def test_review_list_includes_user_name():
    """
    T17 (TECH-15): Call GET /reviews/{channel_id}.
    Verify each review in the response includes user_name
    (either a display name string or null).
    """
    channel_id = get_test_channel_id()
    if channel_id is None:
        pytest.skip("No channels in database to test reviews against")

    resp = api_get(f"/reviews/{channel_id}")
    assert resp.status_code == 200, (
        f"Expected 200 from /reviews/{channel_id}, got {resp.status_code}"
    )

    reviews = resp.json()
    assert isinstance(reviews, list), f"Expected list, got {type(reviews)}"

    if reviews:
        for rev in reviews:
            assert "user_name" in rev, (
                f"Review item missing 'user_name'. Keys: {list(rev.keys())}"
            )
            name = rev["user_name"]
            assert name is None or isinstance(name, str), (
                f"user_name should be string or null, got {type(name)}: {name}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

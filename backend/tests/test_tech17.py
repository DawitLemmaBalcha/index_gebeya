"""
Backend tests for TECH-17: Bottom Navbar + Stores Dashboard + Alert Management.
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_tech17.py -v

Coverage:
  T1: GET /channels/mine — owner with channels returns channels with product_count
  T2: GET /channels/mine — non-owner returns empty list
  T3: GET /channels/mine — unauthenticated returns 403
  T4: PATCH /alerts/{id}/pause — toggles is_active
  T5: GET /alerts/matches — returns match history
"""
import pytest
import httpx
import time
import os

BASE_URL = "http://localhost:8000"

TEST_IMAGE_A = "suqtestchannel_786_cfa110.jpg"


def api_post(path, json_data, timeout=120.0):
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


def api_patch(path, params=None, timeout=10.0):
    """Helper to make HTTP PATCH requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        if params:
            response = httpx.patch(url, params=params, timeout=timeout)
        else:
            response = httpx.patch(url, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_delete(path, params=None, timeout=10.0):
    """Helper to make HTTP DELETE requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        if params:
            response = httpx.delete(url, params=params, timeout=timeout)
        else:
            response = httpx.delete(url, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


_counter = 0


def _unique():
    global _counter
    _counter += 1
    return f"{int(time.time() * 1000)}_{_counter}"


# =========================================================================
# T1: GET /channels/mine — owner with channels returns channels with product_count
# =========================================================================

def test_channels_mine_owner_with_channels():
    """
    Create a user (telegram_id), register channels via the listener upsert,
    add items to those channels, then call GET /channels/mine with valid
    init_data and verify product_count is correct.
    """
    import json
    tg_id = 900000 + abs(hash(_unique())) % 100000

    # Build init_data string with user= field containing the telegram_id
    user_payload = json.dumps({"id": tg_id, "username": f"testuser{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    # Register channels with this user's telegram_id as registered_by
    ch1_username = f"test_ch_mine_{_unique()}"
    ch2_username = f"test_ch_mine2_{_unique()}"
    ch1_tg_id = tg_id + 1000
    ch2_tg_id = tg_id + 2000

    # Upsert channel 1
    resp1 = api_post("/channels/", {
        "username": ch1_username,
        "title": f"Test Channel {ch1_username}",
        "registered_by": tg_id,
        "telegram_id": ch1_tg_id,
    })
    assert resp1.status_code == 200, f"Channel1 upsert failed: {resp1.text}"
    ch1_id = resp1.json()["id"]

    # Upsert channel 2
    resp2 = api_post("/channels/", {
        "username": ch2_username,
        "title": f"Test Channel {ch2_username}",
        "registered_by": tg_id,
        "telegram_id": ch2_tg_id,
    })
    assert resp2.status_code == 200, f"Channel2 upsert failed: {resp2.text}"
    ch2_id = resp2.json()["id"]

    # Add items to channel 1
    for i in range(2):
        msg_id = int(time.time() * 1000) % 10_000_000 + 9000000 + i
        resp = api_post("/parse-telegram-post", {
            "channel_name": ch1_username,
            "message_id": msg_id,
            "text": f"Test product {i} for mine",
            "image_path": TEST_IMAGE_A,
        })
        assert resp.status_code == 200, f"Ingestion failed: {resp.text}"
        data = resp.json()
        if data["status"] == "error":
            err = str(data.get("error", ""))
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
                pytest.skip(f"AI extraction rate-limited: {err[:120]}")

    # Add 1 item to channel 2
    msg_id = int(time.time() * 1000) % 10_000_000 + 9000000 + 100
    api_post("/parse-telegram-post", {
        "channel_name": ch2_username,
        "message_id": msg_id,
        "text": "Test product for ch2",
        "image_path": TEST_IMAGE_A,
    })

    # Now call GET /channels/mine
    resp = api_get(f"/channels/mine?init_data={init_data}")

    # If endpoint doesn't exist yet, skip with message
    if resp.status_code == 404 or resp.status_code == 405:
        # Endpoint not yet implemented — test will fail (RED)
        pass

    assert resp.status_code == 200, f"GET /channels/mine failed: {resp.status_code} — {resp.text[:300]}"
    channels = resp.json()

    # Should have at least our 2 channels
    mine_channels = [c for c in channels if c["id"] in (ch1_id, ch2_id)]
    assert len(mine_channels) >= 2, f"Expected at least 2 channels, got {len(mine_channels)}"

    for ch in mine_channels:
        assert "id" in ch
        assert "username" in ch
        assert "product_count" in ch, f"ChannelResponse missing 'product_count': keys={list(ch.keys())}"
        assert isinstance(ch["product_count"], int), f"product_count should be int, got {type(ch['product_count'])}"
        if ch["id"] == ch1_id:
            assert ch["product_count"] >= 1, f"Channel1 should have >=1 products, got {ch['product_count']}"
        if ch["id"] == ch2_id:
            # Channel 2 may have 0 or more products depending on dedup
            assert ch["product_count"] >= 0, f"product_count should be >=0, got {ch['product_count']}"


# =========================================================================
# T2: GET /channels/mine — non-owner returns empty list
# =========================================================================

def test_channels_mine_non_owner():
    """
    A user with no channels should get HTTP 200 with empty list.
    """
    import json
    tg_id = 900000 + abs(hash(_unique())) % 100000

    user_payload = json.dumps({"id": tg_id, "username": f"nochannel{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    resp = api_get(f"/channels/mine?init_data={init_data}")

    if resp.status_code == 404 or resp.status_code == 405:
        pass  # Endpoint not yet implemented

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) == 0, f"Expected empty list, got {len(data)} channels"


# =========================================================================
# T3: GET /channels/mine — unauthenticated returns 403
# =========================================================================

def test_channels_mine_unauthenticated():
    """
    Calling without valid init_data should return 403.
    """
    resp = api_get("/channels/mine?init_data=bad_data")

    if resp.status_code == 404 or resp.status_code == 405:
        pass  # Endpoint not yet implemented

    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"


# =========================================================================
# T4: PATCH /alerts/{id}/pause — toggles is_active
# =========================================================================

def test_alerts_pause_toggle():
    """
    Create an alert, pause it (is_active becomes False), pause again
    (is_active becomes True).
    """
    import json
    tg_id = 900000 + abs(hash(_unique())) % 100000

    user_payload = json.dumps({"id": tg_id, "username": f"pausetest{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    # Create an alert
    create_resp = api_post("/alerts/", {
        "query_text": "test pause item",
        "init_data": init_data,
        "preferences": {},
    })
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create alert for pause test: {create_resp.text[:200]}")

    alert = create_resp.json()
    alert_id = alert["id"]
    assert alert["is_active"] is True, "New alert should be active"

    # Pause (toggle to inactive)
    pause1_resp = api_patch(f"/alerts/{alert_id}/pause?init_data={init_data}")
    if pause1_resp.status_code == 404 or pause1_resp.status_code == 405:
        pass  # Endpoint not yet implemented

    assert pause1_resp.status_code == 200, f"Pause failed: {pause1_resp.status_code} — {pause1_resp.text[:200]}"
    data1 = pause1_resp.json()
    assert data1["is_active"] is False, f"Expected is_active=False, got {data1}"
    assert data1.get("status") in ("paused", "resumed")

    # Resume (toggle back to active)
    pause2_resp = api_patch(f"/alerts/{alert_id}/pause?init_data={init_data}")
    assert pause2_resp.status_code == 200, f"Resume failed: {pause2_resp.status_code} — {pause2_resp.text[:200]}"
    data2 = pause2_resp.json()
    assert data2["is_active"] is True, f"Expected is_active=True after resume, got {data2}"

    # Cleanup: delete the alert
    api_delete(f"/alerts/{alert_id}?init_data={init_data}")


# =========================================================================
# T5: GET /alerts/matches — returns match history
# =========================================================================

def test_alerts_matches():
    """
    Create an alert for a known item, verify GET /alerts/matches
    returns match history entries.
    """
    import json
    tg_id = 900000 + abs(hash(_unique())) % 100000

    user_payload = json.dumps({"id": tg_id, "username": f"matchtest{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    # Create an alert
    create_resp = api_post("/alerts/", {
        "query_text": "test match item",
        "init_data": init_data,
        "preferences": {},
    })
    if create_resp.status_code not in (200, 201):
        pytest.skip(f"Cannot create alert: {create_resp.text[:200]}")

    alert = create_resp.json()
    alert_id = alert["id"]

    # Call GET /alerts/matches
    resp = api_get(f"/alerts/matches?init_data={init_data}")

    if resp.status_code == 404 or resp.status_code == 405:
        # Endpoint not yet implemented — test will fail (RED)
        pass

    assert resp.status_code == 200, f"GET /alerts/matches failed: {resp.status_code} — {resp.text[:300]}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"

    # If matches exist (may or may not depending on alert engine),
    # verify the schema
    if len(data) > 0:
        match = data[0]
        assert "id" in match
        assert "match_tier" in match
        assert "match_score" in match
        assert "item_id" in match
        assert "created_at" in match

    # Cleanup: delete the alert
    api_delete(f"/alerts/{alert_id}?init_data={init_data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

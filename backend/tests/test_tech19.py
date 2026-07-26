"""
Backend tests for TECH-19: Processing DMs, Pause/Resume, Remove with Auto-Leave.
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_tech19.py -v

Coverage:
  T1: GET /channels/by-username/{username} — channel info lookup
  T2: GET /channels/by-username/{username} — non-existent returns 404
  T3: PATCH /channels/{id}/pause — pause channel
  T4: PATCH /channels/{id}/pause — resume channel
  T5: DELETE /channels/{id} — remove channel (soft-delete)
  T6: GET /channels/mine — excludes removed channels
  T7: PATCH /channels/{id}/pause — non-owner returns 404
  T8: DELETE /channels/{id} — non-owner returns 404
"""
import pytest
import httpx
import time
import os
import json

BASE_URL = "http://localhost:8000"

INTERNAL_HEADERS = {"X-Internal-Service": "index-listener"}


def api_post(path, json_data, timeout=120.0, headers=None):
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.post(url, json=json_data, timeout=timeout, headers=headers)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_get(path, timeout=10.0, headers=None):
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, timeout=timeout, headers=headers)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_patch(path, json_data=None, params=None, timeout=10.0, headers=None):
    url = f"{BASE_URL}{path}"
    try:
        kwargs = {"timeout": timeout}
        if params:
            kwargs["params"] = params
        if json_data is not None:
            kwargs["json"] = json_data
        if headers:
            kwargs["headers"] = headers
        response = httpx.patch(url, **kwargs)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_delete(path, params=None, timeout=10.0, headers=None):
    url = f"{BASE_URL}{path}"
    try:
        kwargs = {"timeout": timeout}
        if params:
            kwargs["params"] = params
        if headers:
            kwargs["headers"] = headers
        response = httpx.delete(url, **kwargs)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


_counter = 0


def _unique():
    global _counter
    _counter += 1
    return f"{int(time.time() * 1000)}_{_counter}"


# =========================================================================
# T1: GET /channels/by-username/{username} — channel info lookup
# =========================================================================

def test_channel_info_lookup():
    """
    Create a channel, then fetch it via GET /channels/by-username/{username}
    with the internal service header. Verify all fields are returned including
    indexing_paused and is_active.
    """
    ch_username = f"test_infolu_{_unique()}"
    tg_id = 900000 + abs(hash(_unique())) % 100000

    # Create channel via upsert
    resp = api_post("/channels/", {
        "username": ch_username,
        "title": f"Info Lookup Channel {ch_username}",
        "registered_by": tg_id,
        "telegram_id": tg_id + 3000,
    })
    assert resp.status_code == 200, f"Channel upsert failed: {resp.text}"
    ch_data = resp.json()

    # Fetch via by-username endpoint with internal header
    get_resp = api_get(
        f"/channels/by-username/{ch_username}",
        headers=INTERNAL_HEADERS,
    )

    # If endpoint doesn't exist yet, this will be a test failure (RED)
    assert get_resp.status_code == 200, (
        f"GET /channels/by-username failed: {get_resp.status_code} — {get_resp.text[:300]}"
    )

    info = get_resp.json()
    assert info["id"] == ch_data["id"], f"Expected id {ch_data['id']}, got {info.get('id')}"
    assert info["username"] == ch_username
    assert info["registered_by"] == tg_id
    assert "indexing_paused" in info, f"Missing 'indexing_paused' in response: keys={list(info.keys())}"
    assert "is_active" in info, f"Missing 'is_active' in response: keys={list(info.keys())}"
    assert info["indexing_paused"] is False, "New channel should have indexing_paused=False"
    assert info["is_active"] is True, "New channel should have is_active=True"


# =========================================================================
# T2: GET /channels/by-username/{username} — non-existent returns 404
# =========================================================================

def test_channel_info_lookup_not_found():
    """
    Query a non-existent username → should return 404.
    """
    non_existent = f"nonexistent_{_unique()}_channel"
    get_resp = api_get(
        f"/channels/by-username/{non_existent}",
        headers=INTERNAL_HEADERS,
    )

    assert get_resp.status_code == 404, (
        f"Expected 404 for non-existent channel, got {get_resp.status_code}"
    )


# =========================================================================
# T3: PATCH /channels/{id}/pause — pause channel
# =========================================================================

def test_channel_pause():
    """
    Create a channel owned by a user, then pause it via PATCH.
    Verify indexing_paused becomes True.
    """
    tg_id = 900000 + abs(hash(_unique())) % 100000
    user_payload = json.dumps({"id": tg_id, "username": f"pausetest{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    ch_username = f"test_pause_{_unique()}"

    # Create channel via upsert
    resp = api_post("/channels/", {
        "username": ch_username,
        "title": f"Pause Test {ch_username}",
        "registered_by": tg_id,
        "telegram_id": tg_id + 4000,
    })
    assert resp.status_code == 200, f"Channel upsert failed: {resp.text}"
    ch_id = resp.json()["id"]

    # Pause the channel
    pause_resp = api_patch(
        f"/channels/{ch_id}/pause",
        json_data={"indexing_paused": True},
        params={"init_data": init_data},
    )

    assert pause_resp.status_code == 200, (
        f"PATCH pause failed: {pause_resp.status_code} — {pause_resp.text[:300]}"
    )
    data = pause_resp.json()
    assert data["status"] == "ok", f"Expected status='ok', got {data}"

    # Verify via channel info lookup
    info_resp = api_get(
        f"/channels/by-username/{ch_username}",
        headers=INTERNAL_HEADERS,
    )
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["indexing_paused"] is True, f"Expected indexing_paused=True, got {info}"


# =========================================================================
# T4: PATCH /channels/{id}/pause — resume channel
# =========================================================================

def test_channel_resume():
    """
    Pause a channel, then resume it. Verify indexing_paused becomes False.
    """
    tg_id = 900000 + abs(hash(_unique())) % 100000
    user_payload = json.dumps({"id": tg_id, "username": f"resumetest{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    ch_username = f"test_resume_{_unique()}"

    resp = api_post("/channels/", {
        "username": ch_username,
        "title": f"Resume Test {ch_username}",
        "registered_by": tg_id,
        "telegram_id": tg_id + 5000,
    })
    assert resp.status_code == 200
    ch_id = resp.json()["id"]

    # Pause first
    api_patch(
        f"/channels/{ch_id}/pause",
        json_data={"indexing_paused": True},
        params={"init_data": init_data},
    )

    # Now resume
    resume_resp = api_patch(
        f"/channels/{ch_id}/pause",
        json_data={"indexing_paused": False},
        params={"init_data": init_data},
    )

    assert resume_resp.status_code == 200, (
        f"Resume failed: {resume_resp.status_code} — {resume_resp.text[:300]}"
    )
    data = resume_resp.json()
    assert data["status"] == "ok"

    # Verify
    info_resp = api_get(
        f"/channels/by-username/{ch_username}",
        headers=INTERNAL_HEADERS,
    )
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["indexing_paused"] is False, f"Expected indexing_paused=False after resume, got {info}"


# =========================================================================
# T5: DELETE /channels/{id} — remove channel (soft-delete)
# =========================================================================

def test_channel_remove():
    """
    Remove a channel via DELETE. Verify is_active becomes False (soft-delete).
    """
    tg_id = 900000 + abs(hash(_unique())) % 100000
    user_payload = json.dumps({"id": tg_id, "username": f"removetest{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    ch_username = f"test_remove_{_unique()}"

    resp = api_post("/channels/", {
        "username": ch_username,
        "title": f"Remove Test {ch_username}",
        "registered_by": tg_id,
        "telegram_id": tg_id + 6000,
    })
    assert resp.status_code == 200
    ch_id = resp.json()["id"]

    # Remove channel
    del_resp = api_delete(
        f"/channels/{ch_id}",
        params={"init_data": init_data},
    )

    # If leaveChat fails (no real bot token), we still expect the DB to be updated
    # The endpoint should handle Telegram API failures gracefully
    assert del_resp.status_code == 200, (
        f"DELETE remove failed: {del_resp.status_code} — {del_resp.text[:300]}"
    )
    data = del_resp.json()
    assert data["status"] == "ok", f"Expected status='ok', got {data}"

    # Verify via channel info lookup
    info_resp = api_get(
        f"/channels/by-username/{ch_username}",
        headers=INTERNAL_HEADERS,
    )
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["is_active"] is False, f"Expected is_active=False after remove, got {info}"


# =========================================================================
# T6: GET /channels/mine — excludes removed channels
# =========================================================================

def test_channels_mine_excludes_removed():
    """
    Create two channels for a user, remove one. GET /channels/mine should
    only return the active channel.
    """
    tg_id = 900000 + abs(hash(_unique())) % 100000
    user_payload = json.dumps({"id": tg_id, "username": f"excludetest{_unique()}"})
    init_data = f"user={user_payload}&auth_date=1&hash=abc"

    ch1_username = f"test_excl1_{_unique()}"
    ch2_username = f"test_excl2_{_unique()}"

    resp1 = api_post("/channels/", {
        "username": ch1_username,
        "title": f"Exclude Ch1 {ch1_username}",
        "registered_by": tg_id,
        "telegram_id": tg_id + 7000,
    })
    assert resp1.status_code == 200
    ch1_id = resp1.json()["id"]

    resp2 = api_post("/channels/", {
        "username": ch2_username,
        "title": f"Exclude Ch2 {ch2_username}",
        "registered_by": tg_id,
        "telegram_id": tg_id + 8000,
    })
    assert resp2.status_code == 200
    ch2_id = resp2.json()["id"]

    # Remove channel 1
    api_delete(f"/channels/{ch1_id}", params={"init_data": init_data})

    # Get my channels — should only have ch2
    mine_resp = api_get(f"/channels/mine?init_data={init_data}")

    assert mine_resp.status_code == 200, (
        f"GET /channels/mine failed: {mine_resp.status_code} — {mine_resp.text[:300]}"
    )
    channels = mine_resp.json()
    channel_ids = [c["id"] for c in channels]

    assert ch1_id not in channel_ids, (
        f"Removed channel {ch1_id} should not appear in /mine, got: {channel_ids}"
    )
    assert ch2_id in channel_ids, (
        f"Active channel {ch2_id} should appear in /mine, got: {channel_ids}"
    )


# =========================================================================
# T7: PATCH /channels/{id}/pause — non-owner returns 404
# =========================================================================

def test_channel_pause_non_owner():
    """
    A non-owner user trying to pause a channel should get 404
    (channel not found for that user).
    """
    owner_tg = 900000 + abs(hash(_unique())) % 100000
    non_owner_tg = owner_tg + 99999

    owner_init_data = f"user={json.dumps({'id': owner_tg, 'username': 'ownertest'})}&auth_date=1&hash=abc"
    non_owner_init_data = f"user={json.dumps({'id': non_owner_tg, 'username': 'intruder'})}&auth_date=1&hash=abc"

    ch_username = f"test_nonowner_pause_{_unique()}"

    resp = api_post("/channels/", {
        "username": ch_username,
        "title": f"Non-Owner Pause {ch_username}",
        "registered_by": owner_tg,
        "telegram_id": owner_tg + 10000,
    })
    assert resp.status_code == 200
    ch_id = resp.json()["id"]

    # Non-owner tries to pause
    pause_resp = api_patch(
        f"/channels/{ch_id}/pause",
        json_data={"indexing_paused": True},
        params={"init_data": non_owner_init_data},
    )

    assert pause_resp.status_code == 404, (
        f"Non-owner should get 404, got {pause_resp.status_code}: {pause_resp.text[:200]}"
    )


# =========================================================================
# T8: DELETE /channels/{id} — non-owner returns 404
# =========================================================================

def test_channel_remove_non_owner():
    """
    A non-owner user trying to remove a channel should get 404.
    """
    owner_tg = 900000 + abs(hash(_unique())) % 100000
    non_owner_tg = owner_tg + 99999

    owner_init_data = f"user={json.dumps({'id': owner_tg, 'username': 'ownertest2'})}&auth_date=1&hash=abc"
    non_owner_init_data = f"user={json.dumps({'id': non_owner_tg, 'username': 'intruder2'})}&auth_date=1&hash=abc"

    ch_username = f"test_nonowner_remove_{_unique()}"

    resp = api_post("/channels/", {
        "username": ch_username,
        "title": f"Non-Owner Remove {ch_username}",
        "registered_by": owner_tg,
        "telegram_id": owner_tg + 10000,
    })
    assert resp.status_code == 200
    ch_id = resp.json()["id"]

    # Non-owner tries to remove
    del_resp = api_delete(
        f"/channels/{ch_id}",
        params={"init_data": non_owner_init_data},
    )

    assert del_resp.status_code == 404, (
        f"Non-owner should get 404, got {del_resp.status_code}: {del_resp.text[:200]}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

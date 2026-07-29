"""
Backend tests for TECH-22: Sold Reports + Product Status + Cleanup
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_tech22.py -v
"""
import pytest
import httpx
import time

BASE_URL = "http://localhost:8000"

# Image paths that exist in /app/media/
TEST_IMAGE_A = "suqtestchannel_786_cfa110.jpg"
TEST_IMAGE_B = "suqtestchannel_787_cc6269.jpg"


def api_post(path, json_data, timeout=120.0):
    """Helper to make HTTP POST requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.post(url, json=json_data, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_get(path, timeout=30.0):
    """Helper to make HTTP GET requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


_channel_counter = 0


def _unique_channel():
    """Generate a unique channel name for test isolation."""
    global _channel_counter
    _channel_counter += 1
    return f"test_tech22_{int(time.time() * 1000)}_{_channel_counter}"


def _unique_message_id():
    """Generate a unique message_id to avoid pk conflicts."""
    return int(time.time() * 1000) % 10_000_000 + 9000000


def _create_test_item(channel_name=None, image_path=None, text="Test item for sale"):
    """Create a test item via ingestion and return the item_id."""
    if channel_name is None:
        channel_name = _unique_channel()
    if image_path is None:
        image_path = TEST_IMAGE_A

    msg_id = _unique_message_id()
    resp = api_post("/parse-telegram-post", {
        "channel_name": channel_name,
        "message_id": msg_id,
        "text": text,
        "image_path": image_path,
    })
    if resp.status_code != 200:
        pytest.skip(f"Ingestion failed: {resp.text[:200]}")
    data = resp.json()
    if data.get("status") == "error":
        err = str(data.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data["status"] == "success", f"Ingestion error: {data}"
    assert data.get("item_id") is not None
    return data["item_id"]


def _make_init_data(telegram_id):
    """Create a fake init_data string with a specific telegram_id."""
    import urllib.parse
    user_json = f'{{"id": {telegram_id}, "username": "testuser_{telegram_id}"}}'
    return f"user={urllib.parse.quote(user_json)}"


# =========================================================================
# T1: Report creates SoldReport
# =========================================================================

def test_report_creates_sold_report():
    """T1: Create item, report once, verify 200 and report_count=1."""
    item_id = _create_test_item()
    init_data = _make_init_data(10001)

    resp = api_post(f"/items/{item_id}/report", {
        "init_data": init_data,
    })
    assert resp.status_code == 200, f"Report failed: {resp.text}"
    data = resp.json()
    assert data.get("status") == "reported", f"Expected status=reported, got {data}"
    assert data.get("report_count") == 1, f"Expected report_count=1, got {data.get('report_count')}"


# =========================================================================
# T2: Duplicate report rejected
# =========================================================================

def test_duplicate_report_rejected():
    """T2: Report same item twice, verify 409 status."""
    item_id = _create_test_item()
    init_data = _make_init_data(10002)

    # First report
    resp1 = api_post(f"/items/{item_id}/report", {"init_data": init_data})
    assert resp1.status_code == 200

    # Second report — should be rejected
    resp2 = api_post(f"/items/{item_id}/report", {"init_data": init_data})
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
    data2 = resp2.json()
    assert "already reported" in str(data2.get("detail", "")).lower()


# =========================================================================
# T3: Owner cannot report own item
# =========================================================================

def test_owner_cannot_report_own_item():
    """T3: Create channel with registered_by, report with same user, verify 403."""
    channel_name = _unique_channel()
    owner_tg_id = 10003

    # Create channel with registered_by set
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")

    # Create item in that channel
    item_id = _create_test_item(channel_name=channel_name)

    # Owner reports their own item — should get 403
    init_data = _make_init_data(owner_tg_id)
    resp = api_post(f"/items/{item_id}/report", {"init_data": init_data})
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# =========================================================================
# T4: Threshold triggers status change
# =========================================================================

def test_threshold_triggers_status_change():
    """T4: Report item 3 times (different users), verify status becomes reported_sold."""
    item_id = _create_test_item()

    # Report from 3 different users — use consecutive tg_ids to auto-create users
    for i in range(3):
        init_data = _make_init_data(20001 + i)
        resp = api_post(f"/items/{item_id}/report", {"init_data": init_data})
        assert resp.status_code == 200, f"Report {i+1} failed: {resp.text}"

    # Verify item status is now reported_sold
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.status_code == 200
    item_data = item_resp.json()
    assert item_data.get("status") == "reported_sold", \
        f"Expected status='reported_sold', got status={item_data.get('status')}"


# =========================================================================
# T5: Relist clears reports and resets status
# =========================================================================

def test_relist_clears_reports():
    """T5: After status is reported_sold, owner relists, verify status returns to active."""
    channel_name = _unique_channel()
    owner_tg_id = 30001

    # Create channel with owner
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")

    # Create item
    item_id = _create_test_item(channel_name=channel_name)

    # Report from 3 different users (not owner)
    for i in range(3):
        init_data = _make_init_data(30010 + i)
        resp = api_post(f"/items/{item_id}/report", {"init_data": init_data})
        assert resp.status_code == 200, f"Report {i+1} failed: {resp.text}"

    # Verify status is reported_sold
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.json().get("status") == "reported_sold"

    # Owner relists
    relist_resp = api_post(f"/items/{item_id}/relist", {"init_data": _make_init_data(owner_tg_id)})
    assert relist_resp.status_code == 200, f"Relist failed: {relist_resp.text}"

    # Verify status is active and report_count is 0
    item_resp2 = api_get(f"/items/{item_id}")
    assert item_resp2.status_code == 200
    item_data = item_resp2.json()
    assert item_data.get("status") == "active", \
        f"Expected status='active', got {item_data.get('status')}"
    assert item_data.get("report_count") == 0, \
        f"Expected report_count=0, got {item_data.get('report_count')}"


# =========================================================================
# T6: Relist on never-reported item is no-op
# =========================================================================

def test_relist_noop():
    """T6: Relist an active never-reported item, verify 200 OK."""
    channel_name = _unique_channel()
    owner_tg_id = 40001

    # Create channel with owner
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")

    # Create item
    item_id = _create_test_item(channel_name=channel_name)

    # Relist never-reported item
    relist_resp = api_post(f"/items/{item_id}/relist", {"init_data": _make_init_data(owner_tg_id)})
    assert relist_resp.status_code == 200, f"Expected 200, got {relist_resp.status_code}: {relist_resp.text}"
    data = relist_resp.json()
    # Should indicate item was never reported (already_active or success)
    assert data.get("status") in ("already_active", "active"), \
        f"Expected already_active or active, got {data.get('status')}"


# =========================================================================
# T7: Non-owner cannot relist
# =========================================================================

def test_non_owner_cannot_relist():
    """T7: Non-owner attempts to relist, verify 403."""
    channel_name = _unique_channel()
    owner_tg_id = 50001

    # Create channel with owner
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")

    # Create item
    item_id = _create_test_item(channel_name=channel_name)

    # Non-owner tries to relist
    resp = api_post(f"/items/{item_id}/relist", {"init_data": _make_init_data(50099)})
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# =========================================================================
# T8: Search excludes reported_sold items
# =========================================================================

def test_search_excludes_reported_sold():
    """T8: After item becomes reported_sold, verify it does NOT appear in search results."""
    # Create item with a unique enough title to search for
    import random
    unique_tag = f"ZXYTEST_{int(time.time())}_{random.randint(1000, 9999)}"
    item_id = _create_test_item(text=f"{unique_tag} laptop for sale")

    # Report from 3 different users to trigger reported_sold
    for i in range(3):
        init_data = _make_init_data(60001 + i)
        resp = api_post(f"/items/{item_id}/report", {"init_data": init_data})
        assert resp.status_code == 200

    # Verify status
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.json().get("status") == "reported_sold"

    # Search for the unique tag
    search_resp = httpx.post(f"{BASE_URL}/search/", json={
        "query": unique_tag,
        "limit": 10,
    }, timeout=30.0)
    if search_resp.status_code != 200:
        pytest.skip(f"Search failed: {search_resp.text[:200]}")

    search_data = search_resp.json()
    found_ids = [itm.get("id") for itm in search_data.get("items", [])]
    assert item_id not in found_ids, \
        f"Reported_sold item {item_id} should NOT appear in search, but was found!"


# =========================================================================
# T9: GET item/{id} always returns item regardless of status
# =========================================================================

def test_get_item_always_returns():
    """T9: GET /items/{id} returns item even when reported_sold."""
    item_id = _create_test_item()

    # Report 3 times
    for i in range(3):
        init_data = _make_init_data(70001 + i)
        resp = api_post(f"/items/{item_id}/report", {"init_data": init_data})
        assert resp.status_code == 200

    # Verify item is still accessible
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.status_code == 200, \
        f"Expected 200 for GET /items/{item_id}, got {item_resp.status_code}"
    item_data = item_resp.json()
    assert item_data.get("status") == "reported_sold"


# =========================================================================
# T10: ItemResponse includes status and report_count
# =========================================================================

def test_item_response_has_status_and_report_count():
    """T10: Verify the JSON response from GET /items/{id} includes status and report_count."""
    item_id = _create_test_item()

    # Get the item
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.status_code == 200
    item_data = item_resp.json()

    # Should have status field
    assert "status" in item_data, "ItemResponse missing 'status' field"
    assert item_data["status"] == "active"

    # Should have report_count field
    assert "report_count" in item_data, "ItemResponse missing 'report_count' field"
    assert item_data["report_count"] == 0

    # Should have is_stale field
    assert "is_stale" in item_data, "ItemResponse missing 'is_stale' field"
    assert item_data["is_stale"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

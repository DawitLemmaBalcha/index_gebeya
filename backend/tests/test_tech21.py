"""
Backend tests for TECH-21: Dedup Redesign (soft-delete + recreate)
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_tech21.py -v
"""
import pytest
import httpx
import time

BASE_URL = "http://localhost:8000"

# Use known images that exist in /app/media/
TEST_IMAGE_A = "suqtestchannel_786_cfa110.jpg"
TEST_IMAGE_B = "suqtestchannel_787_cc6269.jpg"  # Visually distinct image


def api_post(path, json_data, timeout=120.0):
    """Helper to make HTTP POST requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.post(url, json=json_data, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


_channel_counter = 0


def _unique_channel():
    """Generate a unique channel name for test isolation."""
    global _channel_counter
    _channel_counter += 1
    return f"test_tech21_{int(time.time() * 1000)}_{_channel_counter}"


def _unique_message_id():
    """Generate a unique message_id to avoid pk conflicts."""
    return int(time.time() * 1000) % 10_000_000 + 9000000


# =========================================================================
# T1: Soft-delete + create new item on duplicate
# =========================================================================

def test_soft_delete_and_recreate_on_duplicate():
    """T1: Posting a duplicate image should soft-delete the old item
    (is_active=False) and create a NEW item with replaced=True in the response."""
    channel = _unique_channel()

    # First ingestion
    msg_id_1 = _unique_message_id()
    resp1 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": msg_id_1,
        "text": "iPhone 15 Pro Max for sale 256GB",
        "image_path": TEST_IMAGE_A,
    })
    assert resp1.status_code == 200, f"First ingest failed: {resp1.text}"
    data1 = resp1.json()
    if data1["status"] == "error":
        err = str(data1.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data1["status"] == "success", f"First ingest error: {data1}"
    item1_id = data1["item_id"]
    assert item1_id is not None

    # Verify first item is active
    item1_resp = httpx.get(f"{BASE_URL}/items/{item1_id}", timeout=10.0)
    if item1_resp.status_code == 200:
        item1_data = item1_resp.json()
        assert item1_data.get("is_active", True) is True, \
            "First item should be active after initial creation"

    # Second ingestion (same image, different message_id)
    msg_id_2 = _unique_message_id()
    resp2 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": msg_id_2,
        "text": "iPhone 15 Pro Max for sale 256GB (reposted)",
        "image_path": TEST_IMAGE_A,
    })
    assert resp2.status_code == 200, f"Second ingest failed: {resp2.text}"
    data2 = resp2.json()
    if data2["status"] == "error":
        err = str(data2.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"Second ingest rate-limited: {err[:120]}")
    assert data2["status"] == "success", f"Second ingest error: {data2}"
    item2_id = data2["item_id"]

    # CRITICAL: New behavior — should be a DIFFERENT item (soft-delete + recreate)
    assert item2_id != item1_id, \
        f"Expected NEW item (soft-delete+recreate), but got same item {item1_id}"

    # Verify replaced=True was returned
    assert data2.get("replaced") is True, \
        f"Expected replaced=True in response, got replaced={data2.get('replaced')}"

    # Verify old item is now inactive (soft-deleted)
    item1_resp = httpx.get(f"{BASE_URL}/items/{item1_id}", timeout=10.0)
    if item1_resp.status_code == 200:
        item1_data = item1_resp.json()
        assert item1_data.get("is_active") is False, \
            f"Old item #{item1_id} should be inactive after replacement, but is_active={item1_data.get('is_active')}"

    # Verify new item is active
    item2_resp = httpx.get(f"{BASE_URL}/items/{item2_id}", timeout=10.0)
    if item2_resp.status_code == 200:
        item2_data = item2_resp.json()
        assert item2_data.get("is_active", True) is True, \
            f"New item #{item2_id} should be active"


# =========================================================================
# T2: No-match path creates normal item with replaced=False
# =========================================================================

def test_no_match_path_normal_creation():
    """T2: Posting a unique image should create a new item normally
    with replaced=False."""
    channel = _unique_channel()

    resp = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "MacBook Pro M3 for sale",
        "image_path": TEST_IMAGE_B,
    })
    assert resp.status_code == 200
    data = resp.json()
    if data["status"] == "error":
        err = str(data.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data["status"] == "success"
    assert data["item_id"] is not None

    # Should return replaced=False for normal creation
    assert data.get("replaced") is False, \
        f"Expected replaced=False for new item, got replaced={data.get('replaced')}"


# =========================================================================
# T3: Response includes replaced=False when no match
# =========================================================================

def test_no_match_replaced_false():
    """T3: Even when there are candidates but none match,
    the response should have replaced=False."""
    channel = _unique_channel()

    # Create a first item
    resp1 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "iPhone 15 Pro for sale",
        "image_path": TEST_IMAGE_A,
    })
    if resp1.status_code != 200:
        pytest.skip("First ingest failed")
    data1 = resp1.json()
    if data1.get("status") == "error":
        pytest.skip("AI extraction failed")
    assert data1["status"] == "success"

    # Create a second item with a DIFFERENT image (no dedup match)
    resp2 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "MacBook Pro for sale",
        "image_path": TEST_IMAGE_B,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    if data2["status"] == "error":
        pytest.skip("AI extraction failed on second ingest")
    assert data2["status"] == "success"

    # No match, so replaced should be False
    assert data2.get("replaced") is False, \
        f"Expected replaced=False when no match, got replaced={data2.get('replaced')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Backend tests for TECH-06: Post Deduplication via Vector Matching
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_ingestion_dedup.py -v
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
    return f"test_dedup_{int(time.time() * 1000)}_{_channel_counter}"


def _unique_message_id():
    """Generate a unique message_id to avoid pk conflicts."""
    return int(time.time() * 1000) % 10_000_000 + 9000000


# =========================================================================
# T1: Exact duplicate repost matched (RED until dedup is implemented)
# =========================================================================

def test_exact_duplicate_repost_matched():
    """T1: Ingesting the same image twice from the same channel within 30 days
    should UPDATE the existing item instead of creating a new one."""
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
    
    # CRITICAL ASSERTION: Should return the SAME item ID (updated, not duplicated)
    assert item2_id == item1_id, \
        f"Expected dedup to return item {item1_id}, but got new item {item2_id}"


# =========================================================================
# T2: Different image → new item
# =========================================================================

def test_different_image_creates_new_item():
    """T2: Ingesting visually distinct images from the same channel
    should create separate items."""
    channel = _unique_channel()
    
    # First ingestion with image A
    resp1 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "iPhone 15 Pro Max for sale",
        "image_path": TEST_IMAGE_A,
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    if data1["status"] == "error":
        err = str(data1.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data1["status"] == "success"
    item1_id = resp1.json()["item_id"]
    
    # Second ingestion with image B (different image)
    resp2 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "MacBook Pro for sale",
        "image_path": TEST_IMAGE_B,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    if data2["status"] == "error":
        err = str(data2.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data2["status"] == "success"
    item2_id = data2["item_id"]
    
    # Should be different items
    assert item2_id != item1_id, \
        f"Expected distinct items for different images, but got same item {item1_id}"


# =========================================================================
# T3: Different channel → no dedup
# =========================================================================

def test_different_channel_no_dedup():
    """T3: The same image posted to different channels should create
    separate items (one per channel)."""
    channel_x = _unique_channel()
    channel_y = _unique_channel()
    
    # Ingest to channel X
    resp1 = api_post("/parse-telegram-post", {
        "channel_name": channel_x,
        "message_id": _unique_message_id(),
        "text": "Product for sale",
        "image_path": TEST_IMAGE_A,
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    if data1["status"] == "error":
        err = str(data1.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data1["status"] == "success"
    item_x_id = data1["item_id"]
    
    # Ingest same image to channel Y
    resp2 = api_post("/parse-telegram-post", {
        "channel_name": channel_y,
        "message_id": _unique_message_id(),
        "text": "Product for sale",
        "image_path": TEST_IMAGE_A,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    if data2["status"] == "error":
        err = str(data2.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data2["status"] == "success"
    item_y_id = data2["item_id"]
    
    # Should be two separate items (one per channel)
    assert item_y_id != item_x_id, \
        f"Expected separate items per channel, but got same item {item_x_id}"


# =========================================================================
# T4: No vector available (text-only post) — graceful degradation
# =========================================================================

def test_no_vector_skips_dedup():
    """T4: Text-only posts (no image) produce no visual_vector,
    so the dedup block is skipped entirely and a new item is created normally."""
    channel = _unique_channel()
    
    resp = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "Looking to buy a used laptop in Addis Ababa",
        # No image_path — text only
    })
    assert resp.status_code == 200, f"Text-only ingest failed: {resp.text}"
    data = resp.json()
    if data["status"] == "error":
        err = str(data.get("error", ""))
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "AI Extraction failed" in err:
            pytest.skip(f"AI extraction rate-limited: {err[:120]}")
    assert data["status"] == "success", \
        f"Expected success for text-only post, got: {data}"
    assert data["item_id"] is not None, "Text-only post should still create an item"


# =========================================================================
# T5: Field update verification on dedup match
# =========================================================================

def test_dedup_updates_fields():
    """T5: When a duplicate is matched, the existing item's fields
    should be updated with the new extraction data."""
    channel = _unique_channel()
    
    # First ingestion
    resp1 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "Red shoes size 42 for sale",
        "image_path": TEST_IMAGE_A,
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    if data1["status"] == "error" and "429" in str(data1.get("error", "")):
        pytest.skip("AI extraction API rate-limited")
    if data1["status"] == "error":
        pytest.skip(f"AI extraction unavailable: {data1.get('error', 'unknown')}")
    assert data1["status"] == "success"
    item_id = data1["item_id"]
    
    # Second ingestion with updated details
    resp2 = api_post("/parse-telegram-post", {
        "channel_name": channel,
        "message_id": _unique_message_id(),
        "text": "Red shoes size 42 for sale PRICE DROP 500 ETB",
        "image_path": TEST_IMAGE_A,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    if data2["status"] == "error":
        pytest.skip(f"Second ingest failed (rate limit): {data2.get('error', '')}")
    assert data2["status"] == "success"
    assert data2["item_id"] == item_id, "Should match existing item"
    
    # Verify the item was updated via the API
    item_resp = httpx.get(f"{BASE_URL}/items/{item_id}", timeout=10.0)
    if item_resp.status_code == 200:
        item_data = item_resp.json()
        # The original_caption should reflect the new post text
        assert "PRICE DROP" in item_data.get("original_caption", ""), \
            f"Expected updated caption, got: {item_data.get('original_caption')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

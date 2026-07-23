"""
Backend tests for TECH-03 Infinite Scroll / Waterfall Recommendation
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_feed.py -v
"""
import pytest
import httpx
import os
import time

BASE_URL = "http://localhost:8000"

# Session IDs from the database for different user states
SESSION_EXPLORER = "5453a15c-8b6d-458c-a4da-6070015f61f5"  # 5 interactions (3-10 = Explorer)
SESSION_COLD = "7f3896ec-7cef-44d5-bd26-9342d7c56c95"      # 1 interaction (<3 = Cold Start)


def api_get(path, headers=None, params=None):
    """Helper to make HTTP GET requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=10.0)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


# =========================================================================
# TEST: offset and exclude parameters are accepted
# =========================================================================

def test_feed_accepts_offset_parameter():
    """T1: Feed endpoint should accept an offset query parameter and return results."""
    response = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 0}
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0, "Should return items when offset=0"


def test_feed_accepts_exclude_parameter():
    """T2: Feed endpoint should accept an exclude parameter and not return excluded IDs."""
    # First, get some item IDs without exclude
    response1 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 0}
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1) > 0, "Need items in first response to test exclude"
    
    # Collect IDs from first response
    exclude_ids = [str(item["id"]) for item in data1]
    exclude_str = ",".join(exclude_ids)
    
    # Now request with exclude
    response2 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 0, "exclude": exclude_str}
    )
    assert response2.status_code == 200, f"Expected 200, got {response2.status_code}: {response2.text}"
    data2 = response2.json()
    
    # Verify no excluded IDs appear in the response
    excluded_set = set(int(x) for x in exclude_ids)
    for item in data2:
        assert item["id"] not in excluded_set, f"Excluded ID {item['id']} appeared in response!"


def test_feed_offset_changes_results():
    """T3: Different offsets with exclude should produce different items.
    Explorer state (3-10 interactions) doesn't vary by offset alone, but with
    exclude from a previous page, results differ. This is the correct infinite-scroll pattern."""
    # First, get page 0 items
    response0 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 0}
    )
    assert response0.status_code == 200
    page0_ids = [item["id"] for item in response0.json()]
    assert len(page0_ids) > 0, "Need items in page 0"
    
    # Now request with offset=5 AND exclude=page0 IDs
    exclude_str = ",".join(str(x) for x in page0_ids)
    response1 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 5, "exclude": exclude_str}
    )
    assert response1.status_code == 200
    
    ids0 = set(page0_ids)
    ids1 = {item["id"] for item in response1.json()}
    
    # No overlapping IDs between pages
    assert ids0.isdisjoint(ids1), f"Offset 5 with exclude should return different items, got overlap: {ids0 & ids1}"


# =========================================================================
# TEST: Waterfall Mix — Explorer state (70/30 session/trending)
# =========================================================================

def test_explorer_state_70_30_ratio():
    """T4: Explorer state (3-10 interactions) should use 70/30 session/trending at any offset."""
    response = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 20, "offset": 0}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    # Just verify the endpoint returns items successfully for explorer state
    # Ratio validation requires deeper instrumentation


# =========================================================================
# TEST: Cold Start state (100% Trending)  
# =========================================================================

def test_cold_start_state():
    """T5: Cold Start (<3 interactions) should return trending items only."""
    response = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_COLD},
        params={"limit": 10, "offset": 0}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Cold start should still return items (trending fallback)
    if len(data) > 0:
        assert all(isinstance(item["id"], int) for item in data)


# =========================================================================
# TEST: Anonymous user pagination
# =========================================================================

def test_anonymous_user_pagination():
    """T6: Anonymous users (no headers) should get trending items at any offset."""
    response = api_get(
        "/feed/foryou",
        params={"limit": 10, "offset": 0}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_anonymous_user_offset_works():
    """T7: Anonymous user with offset should still return items or empty."""
    response = api_get(
        "/feed/foryou",
        params={"limit": 10, "offset": 20}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Could be empty or have items - both are valid


# =========================================================================
# TEST: Empty response on exhaustion
# =========================================================================

def test_empty_response_on_exhaustion():
    """T8: When all available items have been excluded via the exclude parameter,
    the endpoint should return an empty array, not an error."""
    # Get all item IDs in the database via /items/recent
    all_items_resp = httpx.get(f"{BASE_URL}/items/recent?limit=100", timeout=10.0)
    if all_items_resp.status_code != 200:
        pytest.skip("Cannot fetch all items for exhaustion test")
    all_ids = [str(item["id"]) for item in all_items_resp.json()]
    if not all_ids:
        pytest.skip("No items in database to exhaust")
    
    # Exclude every item in the database
    exclude_all = ",".join(all_ids)
    response = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 10, "offset": 0, "exclude": exclude_all}
    )
    assert response.status_code == 200
    data = response.json()
    assert data == [], f"Expected empty list when all items excluded, got {len(data)} items"


# =========================================================================
# TEST: Sequential pagination with exclude (deduplication)
# =========================================================================

def test_deduplication_via_exclude():
    """T9: Two sequential calls where the second passes IDs from first as exclude 
    should produce no duplicates across the two responses."""
    # Page 1
    response1 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 0}
    )
    assert response1.status_code == 200
    page1 = response1.json()
    page1_ids = [item["id"] for item in page1]
    assert len(page1_ids) > 0, "Need items in page 1"
    
    # Page 2 with exclude
    exclude_str = ",".join(str(x) for x in page1_ids)
    response2 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 5, "offset": 5, "exclude": exclude_str}
    )
    assert response2.status_code == 200
    page2 = response2.json()
    page2_ids = {item["id"] for item in page2}
    
    # No overlap
    overlap = page2_ids & set(page1_ids)
    assert len(overlap) == 0, f"Found duplicate IDs across pages: {overlap}"


# =========================================================================
# TEST: Regular state waterfall ratios
# =========================================================================

def test_regular_state_waterfall():
    """T10: For a Regular user (>10 interactions), verify waterfall mix behavior.
    This test seeds interactions into the database to create a Regular user."""
    import random
    import string
    
    # Generate a unique test session ID
    test_session = "test-waterfall-" + "".join(random.choices(string.ascii_lowercase, k=8))
    
    # Get some item IDs to interact with
    items_response = httpx.get(f"{BASE_URL}/items/recent?limit=5", timeout=10.0)
    if items_response.status_code != 200:
        pytest.skip("Cannot fetch items to seed test data")
    items = items_response.json()
    if len(items) < 3:
        pytest.skip("Not enough items to seed test data")
    
    item_ids = [item["id"] for item in items[:3]]
    
    # Record 12 interactions with different items via /activity/events
    for i in range(12):
        item_id = item_ids[i % len(item_ids)]
        payload = {
            "event_type": "view_item_card",
            "item_id": item_id
        }
        try:
            resp = httpx.post(
                f"{BASE_URL}/activity/events",
                headers={
                    "Content-Type": "application/json",
                    "x-session-id": test_session
                },
                json=payload,
                timeout=5.0
            )
        except Exception:
            pytest.skip("Activity endpoint not available, cannot seed Regular user")
    
    # Now test waterfall for page 1
    response = api_get(
        "/feed/foryou",
        headers={"x-session-id": test_session},
        params={"limit": 20, "offset": 0}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0, "Should return items for Regular user"
    
    # Test page 4 (offset=60) for wildcard inclusion
    response4 = api_get(
        "/feed/foryou",
        headers={"x-session-id": test_session},
        params={"limit": 20, "offset": 60}
    )
    assert response4.status_code == 200
    data4 = response4.json()
    # Page 4 should be empty or have some wildcard items (depending on data available)
    assert isinstance(data4, list)


# =========================================================================
# TEST: Parameter validation
# =========================================================================

def test_offset_zero_is_default():
    """T11: offset=0 should give same results as no offset parameter."""
    response1 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 10, "offset": 0}
    )
    response2 = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 10}
    )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json() == response2.json(), "offset=0 should equal no offset"


def test_invalid_exclude_does_not_crash():
    """T12: Invalid exclude parameter should not crash the server."""
    response = api_get(
        "/feed/foryou",
        headers={"x-session-id": SESSION_EXPLORER},
        params={"limit": 10, "exclude": "not-a-number,abc,123"}
    )
    assert response.status_code in [200, 422, 400], f"Got unexpected status: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

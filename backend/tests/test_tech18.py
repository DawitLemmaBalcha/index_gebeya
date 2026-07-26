"""
Backend tests for TECH-18: Price UX, Bot Commands, Item Card Fallback
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_tech18.py -v
"""
import pytest
import httpx

BASE_URL = "http://localhost:8000"

SESSION_CASUAL = "5453a15c-8b6d-458c-a4da-6070015f61f5"


def api_post(path, json_body, headers=None):
    """Helper for POST requests to the API."""
    url = f"{BASE_URL}{path}"
    default_headers = {"Content-Type": "application/json"}
    if headers:
        default_headers.update(headers)
    try:
        response = httpx.post(url, json=json_body, headers=default_headers, timeout=15.0)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


# =========================================================================
# TEST: exclude_unpriced parameter filters out null/zero-price items
# =========================================================================

def test_search_exclude_unpriced_returns_only_priced_items():
    """T1: When exclude_unpriced=True, all returned items must have price > 0."""
    response = api_post(
        "/search/",
        json_body={
            "query": "phone",
            "limit": 50,
            "exclude_unpriced": True,
        },
        headers={"x-session-id": SESSION_CASUAL},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "items" in data, "Response should have 'items' key"
    
    items = data["items"]
    
    # If results are returned, all must have price > 0
    if items:
        unpriced = [item for item in items if item["price"] is None or item["price"] == 0]
        assert len(unpriced) == 0, (
            f"Found {len(unpriced)} unpriced items when exclude_unpriced=True. "
            f"First unpriced item: {unpriced[0] if unpriced else 'N/A'}"
        )
    
    # Verify the same query WITHOUT exclude_unpriced may return unpriced items
    # (only if the DB actually has unpriced items - if not, this is a no-op check)
    response2 = api_post(
        "/search/",
        json_body={
            "query": "phone",
            "limit": 50,
            "exclude_unpriced": False,
        },
        headers={"x-session-id": SESSION_CASUAL},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    items2 = data2["items"]
    
    # With exclude_unpriced=False, we should get >= results than with True
    # (because we're not filtering out any items)
    assert len(items2) >= len(items), (
        f"Expected unfiltered search (exclude_unpriced=False) to return >= items ({len(items2)}) "
        f"than filtered search (exclude_unpriced=True) ({len(items)})"
    )

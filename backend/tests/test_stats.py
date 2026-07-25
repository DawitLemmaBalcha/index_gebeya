"""
Backend tests for TECH-16 Stats Endpoint
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_stats.py -v
"""
import pytest
import httpx

BASE_URL = "http://localhost:8000"


def api_get(path, headers=None, params=None):
    """Helper to make HTTP GET requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=10.0)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


# =========================================================================
# TEST 1: Stats endpoint returns counts for a populated database
# =========================================================================

def test_stats_returns_counts():
    """T1: GET /items/stats should return product_count and channel_count."""
    response = api_get("/items/stats")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "product_count" in data, f"Missing product_count in response: {data}"
    assert "channel_count" in data, f"Missing channel_count in response: {data}"
    assert isinstance(data["product_count"], int)
    assert isinstance(data["channel_count"], int)
    assert data["product_count"] >= 0
    assert data["channel_count"] >= 0


# =========================================================================
# TEST 2: Stats endpoint returns category_counts
# =========================================================================

def test_stats_returns_category_counts():
    """T2: GET /items/stats should return category_counts dict."""
    response = api_get("/items/stats")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "category_counts" in data, f"Missing category_counts in response: {data}"
    assert isinstance(data["category_counts"], dict)
    # Each value should be an integer >= 0
    for cat, count in data["category_counts"].items():
        assert isinstance(cat, str)
        assert isinstance(count, int)
        assert count >= 0

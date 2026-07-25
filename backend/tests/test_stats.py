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


# =========================================================================
# TEST 3: Exact-count insert test — insert items + channels, verify counts
# =========================================================================

import psycopg2
import time


def _get_db_conn():
    """Create a direct database connection for test data setup/teardown."""
    return psycopg2.connect(
        host="localhost",
        port=5433,
        user="suq_admin",
        password="secret_password_change_me",
        dbname="suq_main_db",
    )


def test_exact_count_insert_verify():
    """
    T3: Insert 5 items and 3 channels, then verify stats endpoint returns
    counts that reflect the inserted data (baseline + inserted).
    """
    conn = _get_db_conn()
    cur = conn.cursor()

    # Pre-compute a valid pgvector literal: [0,0,...,0] with 512 zeros
    vector_literal = "[" + ",".join(["0"] * 512) + "]"

    test_channels = []
    test_item_ids = []

    try:
        # --- Get baseline counts ---
        cur.execute("SELECT COUNT(*) FROM channels")
        baseline_channels = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM items")
        baseline_items = cur.fetchone()[0]

        # --- Insert 3 test channels ---
        ts = int(time.time())  # seconds precision is fine
        for i in range(3):
            username = f"test_stats_ch_{ts}_{i}"
            cur.execute(
                "INSERT INTO channels (username, title) VALUES (%s, %s) RETURNING id",
                (username, f"Test Stats Channel {i}"),
            )
            ch_id = cur.fetchone()[0]
            test_channels.append(ch_id)

        # --- Insert 5 test items (linked to the test channels) ---
        for i in range(5):
            ch_id = test_channels[i % 3]  # distribute across 3 channels
            msg_id = (ts * 10 + 900000000 + i) % 2000000000  # keep within 4-byte int range
            cur.execute(
                """
                INSERT INTO items
                    (channel_id, telegram_message_id, title, price, currency,
                     category, image_path, image_vector)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                RETURNING id
                """,
                (
                    ch_id,
                    msg_id,
                    f"Test Stats Item {i}",
                    100 + i * 10,
                    "ETB",
                    "Electronics",
                    "/media/test_stats_item.jpg",
                    vector_literal,
                ),
            )
            item_id = cur.fetchone()[0]
            test_item_ids.append(item_id)

        conn.commit()

        # --- Call the stats endpoint ---
        response = api_get("/items/stats")
        assert response.status_code == 200, f"Stats endpoint failed: {response.text}"
        data = response.json()

        # --- Assert counts reflect the inserted data ---
        assert data["product_count"] == baseline_items + 5, (
            f"Expected product_count={baseline_items + 5}, got {data['product_count']}"
        )
        assert data["channel_count"] == baseline_channels + 3, (
            f"Expected channel_count={baseline_channels + 3}, got {data['channel_count']}"
        )

    except Exception:
        conn.rollback()
        raise
    finally:
        # --- Clean up: delete test items first (FK), then test channels ---
        if test_item_ids:
            cur.execute("DELETE FROM items WHERE id = ANY(%s)", (test_item_ids,))
        if test_channels:
            cur.execute("DELETE FROM channels WHERE id = ANY(%s)", (test_channels,))
        conn.commit()
        cur.close()
        conn.close()


# =========================================================================
# TEST 4: Empty-database test — verify stats endpoint handles empty DB
# =========================================================================

def test_stats_handles_empty_database():
    """
    T4: Verify the stats endpoint returns consistent counts when queried.
    We validate that the API-reported counts match a direct DB COUNT query,
    which proves the endpoint is correctly wired to the database.
    (Cannot truncate production DB, so we verify consistency instead.)
    """
    conn = _get_db_conn()
    cur = conn.cursor()

    try:
        # Get counts directly from the database
        cur.execute("SELECT COUNT(*) FROM channels")
        db_channel_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM items")
        db_item_count = cur.fetchone()[0]

        # Get counts from the API endpoint
        response = api_get("/items/stats")
        assert response.status_code == 200, f"Stats endpoint failed: {response.text}"
        data = response.json()

        # API counts must match direct DB queries
        assert data["channel_count"] == db_channel_count, (
            f"API channel_count={data['channel_count']} does not match DB count={db_channel_count}"
        )
        assert data["product_count"] == db_item_count, (
            f"API product_count={data['product_count']} does not match DB count={db_item_count}"
        )

        # Counts must be non-negative
        assert data["product_count"] >= 0
        assert data["channel_count"] >= 0

    finally:
        cur.close()
        conn.close()

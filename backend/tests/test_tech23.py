"""
Backend tests for TECH-23: Inventory Management
These tests hit the running API at localhost:8000.
Run with: pytest tests/test_tech23.py -v
"""
import pytest
import httpx
import time
import os
import json
import urllib.parse

BASE_URL = "http://localhost:8000"

# Image paths that exist in /app/media/
TEST_IMAGE_A = "suqtestchannel_786_cfa110.jpg"
TEST_IMAGE_B = "suqtestchannel_787_cc6269.jpg"


# =========================================================================
# HTTP HELPERS
# =========================================================================

def api_post(path, json_data=None, params=None, timeout=120.0):
    """Helper to make HTTP POST requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.post(url, json=json_data, params=params, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_get(path, params=None, timeout=30.0):
    """Helper to make HTTP GET requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, params=params, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


def api_patch(path, json_data=None, params=None, timeout=30.0):
    """Helper to make HTTP PATCH requests to the API."""
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.patch(url, json=json_data, params=params, timeout=timeout)
        return response
    except httpx.ConnectError:
        pytest.skip("API not reachable at localhost:8000")


# =========================================================================
# DB HELPERS (for bulk item creation and ItemEdit verification)
# =========================================================================

def _get_db_url():
    """Get database URL from environment."""
    return (
        f"postgresql://{os.getenv('DB_USER', 'suq_admin')}:"
        f"{os.getenv('DB_PASSWORD', 'secret_password_change_me')}@"
        f"{os.getenv('DB_HOST', 'db')}:{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'suq_main_db')}"
    )


def _db_execute(sql, params=None):
    """Execute raw SQL and return all rows. Returns None if DB unavailable."""
    try:
        import psycopg2
        conn = psycopg2.connect(_get_db_url())
        try:
            cur = conn.cursor()
            cur.execute(sql, params or {})
            if cur.description:
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
            return result
        finally:
            conn.close()
    except Exception:
        return None


def _db_insert_many(sql_template, rows):
    """Insert many rows into DB. Returns True on success."""
    try:
        import psycopg2
        conn = psycopg2.connect(_get_db_url())
        try:
            cur = conn.cursor()
            for row in rows:
                cur.execute(sql_template, row)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"[DB WARN] _db_insert_many failed: {e}")
        return False


def _count_item_edits(item_id):
    """Count ItemEdit records for an item via raw SQL. Returns None if unavailable."""
    rows = _db_execute(
        "SELECT COUNT(*) FROM item_edits WHERE item_id = %s",
        (item_id,)
    )
    if rows is not None:
        return rows[0][0]
    return None


def _count_sold_reports(item_id):
    """Count SoldReport records for an item. Returns None if DB unavailable."""
    rows = _db_execute(
        "SELECT COUNT(*) FROM sold_reports WHERE item_id = %s",
        (item_id,)
    )
    if rows is not None:
        return rows[0][0]
    return None


# =========================================================================
# TEST HELPERS
# =========================================================================

_channel_counter = 0
_msg_id_counter = 0


def _unique_channel():
    """Generate a unique channel name for test isolation."""
    global _channel_counter
    _channel_counter += 1
    return f"test_tech23_{int(time.time() * 1000)}_{_channel_counter}"


def _unique_message_id():
    """Generate a unique message_id using a monotonic counter to avoid pk conflicts."""
    global _msg_id_counter
    _msg_id_counter += 1
    # Use a high base + counter to guarantee uniqueness within a test session
    return 90_000_000 + (int(time.time() * 1000) % 1_000_000) + _msg_id_counter


def _make_init_data(telegram_id):
    """Create a fake init_data string with a specific telegram_id."""
    user_json = f'{{"id": {telegram_id}, "username": "testuser_{telegram_id}"}}'
    return f"user={urllib.parse.quote(user_json)}"


def _create_test_item(channel_name=None, image_path=None, text="Test item for sale",
                       owner_tg_id=None):
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


def _create_owned_item(channel_name, owner_tg_id, text="Test item for sale"):
    """Create a test item AND register the channel to an owner.
    Returns (item_id, channel_id)."""
    # First create/register the channel
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")
    channel_data = resp_ch.json()

    # Create item
    item_id = _create_test_item(channel_name=channel_name, text=text)

    # Get item to find channel_id
    item_resp = api_get(f"/items/{item_id}")
    if item_resp.status_code == 200:
        channel_id = item_resp.json().get("channel", {}).get("id")
    else:
        channel_id = channel_data.get("id")

    return item_id, channel_id


def _db_create_owned_item(channel_name, owner_tg_id, text="Test item",
                           status="active", price=150.0):
    """Create an owned channel + item via DB (no AI pipeline).
    Returns (item_id, channel_id). Much faster and avoids rate-limit skips."""
    # Register channel via API
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")
    channel_data = resp_ch.json()
    channel_id = channel_data.get("id")

    if not channel_id:
        pytest.skip("Could not get channel_id")

    # Insert item directly into DB
    msg_id = _unique_message_id()
    rows = _db_execute(
        """INSERT INTO items
           (channel_id, telegram_message_id, title, description, price,
            currency, category, subcategory, image_path, is_active, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (channel_id, msg_id, text, f"Description of {text}",
         price, "ETB", "Electronics", "Phones",
         TEST_IMAGE_A, True, status)
    )
    if rows:
        return rows[0][0], channel_id

    pytest.skip(f"DB insertion failed for owned item in channel {channel_name}")


def _create_channel_with_bulk_items(owner_tg_id, count=25):
    """Create a channel owned by owner_tg_id and bulk-insert count items via DB.
    Returns (channel_id, item_ids)."""
    channel_name = _unique_channel()

    # Register channel via API
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")
    channel_data = resp_ch.json()
    channel_id = channel_data.get("id")

    if not channel_id:
        pytest.skip("Could not get channel_id")

    # Bulk-insert items via DB for speed (avoids AI extraction rate limits)
    item_ids = []
    for i in range(count):
        msg_id = _unique_message_id()
        rows = _db_execute(
            """INSERT INTO items
               (channel_id, telegram_message_id, title, description, price,
                currency, category, subcategory, image_path, is_active, status,
                image_vector)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (channel_id, msg_id, f"Test Item {i+1}", f"Description {i+1}",
             100.0 + i, "ETB", "Electronics", "Phones",
             TEST_IMAGE_A, True, "active", None)
        )
        if rows:
            item_ids.append(rows[0][0])
        else:
            # Fallback: create via API
            try:
                item_id = _create_test_item(channel_name=channel_name,
                                            text=f"Bulk item {i+1}")
                item_ids.append(item_id)
            except Exception:
                pass

    return channel_id, item_ids


# =========================================================================
# T1: GET /channels/{id}/items — pagination
# =========================================================================

def test_channel_items_pagination():
    """T1: Create 25 items, test pagination with limit=10 at offsets 0, 10, 20."""
    owner_tg_id = 91001
    channel_id, item_ids = _create_channel_with_bulk_items(owner_tg_id, count=25)

    if len(item_ids) < 25:
        pytest.skip(f"Only created {len(item_ids)}/25 bulk items, skipping pagination test")

    init_data = _make_init_data(owner_tg_id)
    params = {"init_data": init_data, "limit": 10}

    # Page 1: offset=0
    params["offset"] = 0
    resp1 = api_get(f"/channels/{channel_id}/items", params=params)
    assert resp1.status_code == 200, f"Page 1 failed: {resp1.text[:200]}"
    page1 = resp1.json()
    assert len(page1) == 10, f"Expected 10 items on page 1, got {len(page1)}"

    # Page 2: offset=10
    params["offset"] = 10
    resp2 = api_get(f"/channels/{channel_id}/items", params=params)
    assert resp2.status_code == 200, f"Page 2 failed: {resp2.text[:200]}"
    page2 = resp2.json()
    assert len(page2) == 10, f"Expected 10 items on page 2, got {len(page2)}"

    # Page 3: offset=20
    params["offset"] = 20
    resp3 = api_get(f"/channels/{channel_id}/items", params=params)
    assert resp3.status_code == 200, f"Page 3 failed: {resp3.text[:200]}"
    page3 = resp3.json()
    assert len(page3) == 5, f"Expected 5 items on page 3, got {len(page3)}"

    # Verify no overlap between pages (unique item_ids across pages)
    page1_ids = {itm["id"] for itm in page1}
    page2_ids = {itm["id"] for itm in page2}
    page3_ids = {itm["id"] for itm in page3}
    assert len(page1_ids & page2_ids) == 0, "Pages 1 and 2 should have no overlapping items"
    assert len(page1_ids & page3_ids) == 0, "Pages 1 and 3 should have no overlapping items"
    assert len(page2_ids & page3_ids) == 0, "Pages 2 and 3 should have no overlapping items"


# =========================================================================
# T2: GET /channels/{id}/items — status filter
# =========================================================================

def test_channel_items_status_filter():
    """T2: Filter items by status=sold vs status=all."""
    owner_tg_id = 92001
    channel_name = _unique_channel()

    # Register channel
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")
    channel_data = resp_ch.json()
    channel_id = channel_data.get("id")

    if not channel_id:
        pytest.skip("Could not get channel_id")

    # Use DB insertion for items to avoid dedup issues (same image in same
    # channel would cause the ingestion pipeline to soft-delete earlier items).
    items_to_insert = []

    # 3 active items
    for i in range(3):
        items_to_insert.append((channel_id, _unique_message_id(),
                                f"Active item {i+1}", "active"))

    # 2 sold items
    for i in range(2):
        items_to_insert.append((channel_id, _unique_message_id(),
                                f"Sold item {i+1}", "sold"))

    # 1 reported_sold item
    items_to_insert.append((channel_id, _unique_message_id(),
                            "Reported sold item", "reported_sold"))

    item_ids = []
    for (cid, msg_id, title, status) in items_to_insert:
        rows = _db_execute(
            """INSERT INTO items
               (channel_id, telegram_message_id, title, description, price,
                currency, category, subcategory, image_path, is_active, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (cid, msg_id, title, f"Desc: {title}", 100.0,
             "ETB", "Electronics", "Phones",
             TEST_IMAGE_A, True, status)
        )
        if rows:
            item_ids.append(rows[0][0])

    if len(item_ids) < 6:
        pytest.skip(f"Only created {len(item_ids)}/6 items, skipping filter test")

    active_ids = item_ids[0:3]
    sold_ids = item_ids[3:5]
    rpt_item_id = item_ids[5]

    # If DB-inserted items need their status set (sold/reported_sold), do it now.
    # Via DB they're already set, but verify.
    init_data = _make_init_data(owner_tg_id)

    # Fetch with status=sold
    resp_sold = api_get(f"/channels/{channel_id}/items", params={
        "init_data": init_data, "status": "sold", "limit": 50,
    })
    assert resp_sold.status_code == 200, f"Status sold filter failed: {resp_sold.text}"
    sold_items = resp_sold.json()

    # All returned items should have status "sold"
    for itm in sold_items:
        assert itm.get("status") == "sold", \
            f"Expected status='sold', got '{itm.get('status')}' for item {itm.get('id')}"

    # Should contain our sold items
    returned_sold_ids = {itm["id"] for itm in sold_items}
    for sid in sold_ids:
        assert sid in returned_sold_ids, f"Sold item {sid} not found in status=sold results"

    # Fetch with status=all (no filter)
    resp_all = api_get(f"/channels/{channel_id}/items", params={
        "init_data": init_data, "status": "all", "limit": 50,
    })
    assert resp_all.status_code == 200
    all_items = resp_all.json()
    all_ids = {itm["id"] for itm in all_items}

    # All items (active + sold + reported_sold) should be in "all" results
    for aid in active_ids:
        assert aid in all_ids, f"Active item {aid} missing from status=all results"
    for sid in sold_ids:
        assert sid in all_ids, f"Sold item {sid} missing from status=all results"
    assert rpt_item_id in all_ids, f"Reported_sold item {rpt_item_id} missing from status=all"


# =========================================================================
# T3: GET /channels/{id}/items — ownership check
# =========================================================================

def test_channel_items_ownership_check():
    """T3: Non-owner attempts to fetch items → 404."""
    owner_tg_id = 94001
    channel_name = _unique_channel()

    # Owner creates channel
    resp_ch = api_post("/channels/", {
        "username": channel_name,
        "registered_by": owner_tg_id,
    })
    if resp_ch.status_code != 200:
        pytest.skip(f"Channel creation failed: {resp_ch.text[:200]}")
    channel_id = resp_ch.json().get("id")

    # Create an item
    _create_test_item(channel_name=channel_name, text="Owner's item")

    # Non-owner (different tg_id) tries to fetch
    non_owner_init = _make_init_data(94999)
    resp = api_get(f"/channels/{channel_id}/items", params={
        "init_data": non_owner_init,
    })
    assert resp.status_code == 404, \
        f"Expected 404 for non-owner, got {resp.status_code}: {resp.text[:200]}"


# =========================================================================
# T4: PATCH /items/{id} — successful edit
# =========================================================================

def test_patch_item_successful_edit():
    """T4: Update title and price of owned item → 200, verify values AND ItemEdit records."""
    owner_tg_id = 95001
    channel_name = _unique_channel()
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="Original Title for 150 ETB")
    init_data = _make_init_data(owner_tg_id)

    # Patch title and price
    new_title = f"Updated Title {int(time.time())}"
    new_price = 250.0
    resp = api_patch(
        f"/items/{item_id}",
        json_data={"title": new_title, "price": new_price},
        params={"init_data": init_data},
    )
    assert resp.status_code == 200, f"PATCH failed: {resp.status_code} — {resp.text[:300]}"
    updated = resp.json()
    assert updated.get("title") == new_title, \
        f"Expected title '{new_title}', got '{updated.get('title')}'"
    assert updated.get("price") == new_price, \
        f"Expected price {new_price}, got {updated.get('price')}"

    # Verify ItemEdit records were created (DB check)
    edit_count = _count_item_edits(item_id)
    if edit_count is not None:
        assert edit_count == 2, \
            f"Expected 2 ItemEdit records (title + price), found {edit_count}"
    else:
        print("[WARN] Cannot verify ItemEdit records — DB unreachable")


# =========================================================================
# T5: PATCH /items/{id} — forbidden edit
# =========================================================================

def test_patch_item_forbidden_edit():
    """T5: Non-owner attempts to edit → 403."""
    owner_tg_id = 96001
    channel_name = _unique_channel()
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="Owner's item")

    # Non-owner tries to patch
    non_owner_init = _make_init_data(96999)
    resp = api_patch(
        f"/items/{item_id}",
        json_data={"title": "Hacked Title"},
        params={"init_data": non_owner_init},
    )
    assert resp.status_code == 403, \
        f"Expected 403 for non-owner edit, got {resp.status_code}: {resp.text[:200]}"
    detail = resp.json().get("detail", "")
    assert "own" in detail.lower() or "edit" in detail.lower(), \
        f"Expected ownership error, got: {detail}"


# =========================================================================
# T6: POST /items/{id}/sold — mark as sold
# =========================================================================

def test_mark_item_sold():
    """T6: Mark as sold → status 'sold'; mark again → still 'sold' (idempotent)."""
    owner_tg_id = 97001
    channel_name = _unique_channel()
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="Item for sale")
    init_data = _make_init_data(owner_tg_id)

    # First: mark as sold
    resp1 = api_post(f"/items/{item_id}/sold", params={"init_data": init_data})
    assert resp1.status_code == 200, f"Mark sold failed: {resp1.text[:200]}"
    data1 = resp1.json()
    assert data1.get("status") == "sold", \
        f"Expected status='sold', got '{data1.get('status')}'"

    # Verify via GET
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.status_code == 200
    assert item_resp.json().get("status") == "sold"

    # Second: mark as sold again (idempotent)
    resp2 = api_post(f"/items/{item_id}/sold", params={"init_data": init_data})
    assert resp2.status_code == 200, f"Second mark sold failed: {resp2.text[:200]}"
    data2 = resp2.json()
    assert data2.get("status") == "sold", \
        f"Expected status='sold' on second call, got '{data2.get('status')}'"


# =========================================================================
# T7: POST /items/{id}/relist — relist
# =========================================================================

def test_relist_item():
    """T7: Relist a sold item → status 'active'; verify SoldReport records deleted."""
    owner_tg_id = 98001
    channel_name = _unique_channel()

    # Create channel with owner and an item
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="Item to relist",
                                                 status="active")

    # Mark as sold first
    init_data = _make_init_data(owner_tg_id)
    sold_resp = api_post(f"/items/{item_id}/sold", params={"init_data": init_data})
    assert sold_resp.status_code == 200

    # Report 3 times to create SoldReport records (simulating reported_sold state)
    for i in range(3):
        reporter_init = _make_init_data(99000 + i)
        api_post(f"/items/{item_id}/report", {"init_data": reporter_init})

    # Relist (this endpoint uses JSON body with init_data)
    relist_resp = api_post(f"/items/{item_id}/relist",
                            json_data={"init_data": init_data})
    assert relist_resp.status_code == 200, \
        f"Relist failed: {relist_resp.status_code} — {relist_resp.text[:200]}"
    data = relist_resp.json()
    assert data.get("status") == "active", \
        f"Expected status='active', got '{data.get('status')}'"

    # Verify item status via GET
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.status_code == 200
    assert item_resp.json().get("status") == "active", \
        "Item status should be 'active' after relist"

    # Verify SoldReport records were deleted
    report_count = _count_sold_reports(item_id)
    if report_count is not None:
        assert report_count == 0, \
            f"Expected 0 SoldReport records after relist, found {report_count}"
    else:
        print("[WARN] Cannot verify SoldReport deletion — DB unreachable")


# =========================================================================
# T8: POST /items/{id}/clear-reports — clear without relist
# =========================================================================

def test_clear_reports():
    """T8: Clear reports on reported_sold item → status unchanged, reports gone."""
    owner_tg_id = 100001
    channel_name = _unique_channel()

    # Create channel with owner and item (via DB for speed, avoid AI rate limits)
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="Reported item",
                                                 status="active")

    # We need the item to be in reported_sold status. The SoldReport endpoint
    # doesn't exist as an owner action, so we report via API (from non-owners).
    # Report 3 times to reach reported_sold threshold
    for i in range(3):
        reporter_init = _make_init_data(101000 + i)
        api_post(f"/items/{item_id}/report", {"init_data": reporter_init})

    # Verify status is reported_sold
    item_resp = api_get(f"/items/{item_id}")
    assert item_resp.status_code == 200
    assert item_resp.json().get("status") == "reported_sold", \
        "Expected reported_sold status after 3 reports"

    # Verify reports exist
    before_count = _count_sold_reports(item_id)

    # Clear reports (query param)
    init_data = _make_init_data(owner_tg_id)
    clear_resp = api_post(f"/items/{item_id}/clear-reports",
                           params={"init_data": init_data})
    assert clear_resp.status_code == 200, \
        f"Clear reports failed: {clear_resp.status_code} — {clear_resp.text[:200]}"
    clear_data = clear_resp.json()
    # Status should remain reported_sold (not changed to active)
    assert clear_data.get("status") == "reported_sold", \
        f"Expected status='reported_sold', got '{clear_data.get('status')}'"

    # Verify reports are gone
    after_count = _count_sold_reports(item_id)
    if after_count is not None:
        assert after_count == 0, \
            f"Expected 0 reports after clear, found {after_count}"
        if before_count is not None:
            assert before_count > 0, "Reports should have existed before clearing"


# =========================================================================
# T9: Edit history logging
# =========================================================================

def test_edit_history_logging():
    """T9: Edit title only → 1 ItemEdit. Edit title+price+specs → 3 ItemEdits."""
    owner_tg_id = 102001
    channel_name = _unique_channel()
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="History test item")
    init_data = _make_init_data(owner_tg_id)

    # ---- Test A: Edit title only → expect 1 ItemEdit ----
    resp_a = api_patch(
        f"/items/{item_id}",
        json_data={"title": "Title Only Change"},
        params={"init_data": init_data},
    )
    assert resp_a.status_code == 200, f"Title-only edit failed: {resp_a.text[:200]}"
    assert resp_a.json().get("title") == "Title Only Change"

    edit_count_a = _count_item_edits(item_id)
    if edit_count_a is not None:
        assert edit_count_a == 1, \
            f"Expected 1 ItemEdit after title-only change, found {edit_count_a}"
    else:
        print("[WARN] Cannot verify ItemEdit records — DB unreachable")

    # ---- Test B: Edit title + price + specs in one request → expect 3 ItemEdits ----
    resp_b = api_patch(
        f"/items/{item_id}",
        json_data={
            "title": "Multi-field Change",
            "price": 350.0,
            "specs": {"brand": "TestBrand", "model": "X100"},
        },
        params={"init_data": init_data},
    )
    assert resp_b.status_code == 200, f"Multi-field edit failed: {resp_b.text[:200]}"
    updated = resp_b.json()
    assert updated.get("title") == "Multi-field Change"
    assert updated.get("price") == 350.0

    # Total should now be 1 (from test A) + 3 (from test B) = 4
    total_edits = _count_item_edits(item_id)
    if total_edits is not None:
        assert total_edits == 4, \
            f"Expected 4 total ItemEdits (1 title + 1 title + 1 price + 1 specs), found {total_edits}"


# =========================================================================
# T10: Re-trigger alert matching
# =========================================================================

def test_alert_matching_retrigger():
    """T10: Edit price → process_new_item is called (endpoint succeeds).
    Edit only title → endpoint succeeds without issues."""
    owner_tg_id = 103001
    channel_name = _unique_channel()
    item_id, channel_id = _db_create_owned_item(channel_name, owner_tg_id,
                                                 text="Alert re-trigger test item")
    init_data = _make_init_data(owner_tg_id)

    # ---- Test A: Edit price → should trigger process_new_item ----
    # We can't directly verify process_new_item was called from HTTP tests,
    # but we can verify the endpoint succeeds and the item is updated.
    resp_price = api_patch(
        f"/items/{item_id}",
        json_data={"price": 500.0},
        params={"init_data": init_data},
    )
    assert resp_price.status_code == 200, \
        f"Price edit (with re-process) failed: {resp_price.text[:200]}"
    updated = resp_price.json()
    assert updated.get("price") == 500.0, "Price should be updated"

    # Verify an ItemEdit record for price exists
    edit_count_price = _count_item_edits(item_id)
    if edit_count_price is not None:
        assert edit_count_price >= 1, \
            f"Expected at least 1 ItemEdit (price), found {edit_count_price}"

    # ---- Test B: Edit only title → should NOT trigger process_new_item ----
    # Again, we verify the endpoint succeeds without errors.
    resp_title = api_patch(
        f"/items/{item_id}",
        json_data={"title": "Title Only No Alert"},
        params={"init_data": init_data},
    )
    assert resp_title.status_code == 200, \
        f"Title-only edit failed: {resp_title.text[:200]}"
    assert resp_title.json().get("title") == "Title Only No Alert"

    # Verify that ItemEdit was created for the title change
    total_edits = _count_item_edits(item_id)
    if total_edits is not None:
        assert total_edits >= 2, \
            f"Expected at least 2 ItemEdits (price + title), found {total_edits}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

# TECH-22 Blueprint: Sold Reports + Product Status + Cleanup

**Date:** 2026-07-29
**Parent:** NB-41
**Context:** `docs/behaviors/sold-reports.md`

---

## Goal

Add crowdsourced sold-reporting, item status lifecycle, configurable cleanup constants, and a daily background cleanup task, plus owner DM notifications on status transitions.

---

## Files to Modify/Create

| Action | File Path |
|--------|-----------|
| MODIFY | `backend/models.py` |
| MODIFY | `backend/constants.py` |
| MODIFY | `backend/main.py` |
| MODIFY | `backend/schemas.py` |
| MODIFY | `backend/api/routes/items.py` |
| MODIFY | `backend/services/search.py` |
| MODIFY | `backend/services/recommendation.py` |
| CREATE | `backend/services/cleanup.py` |
| MODIFY | `frontend/src/pages/ProductPage.jsx` |
| MODIFY | `frontend/src/components/ItemCard.jsx` |
| CREATE | `backend/tests/test_tech22.py` |

---

## Strict Import Map

### 1. `backend/models.py` — New model imports already available

- **Add to `Item` class:**
  - `status` = `Column(String, default="active", nullable=False)` — valid values: `active`, `sold`, `reported_sold`, `soft_deleted`, `removed`

- **New class `SoldReport`:**
  - `__tablename__` = `"sold_reports"`
  - `__table_args__` = `(UniqueConstraint('user_id', 'item_id', name='_user_item_sold_report_uc'),)`
  - `id` = `Column(Integer, primary_key=True, index=True)`
  - `user_id` = `Column(Integer, ForeignKey("users.id"), nullable=False)`
  - `item_id` = `Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)`
  - `created_at` = `Column(DateTime(timezone=True), server_default=func.now())`
  - Relationships: `user = relationship("User")`, `item = relationship("Item")`

  _No new imports needed — Column, Integer, String, DateTime, ForeignKey, func, UniqueConstraint are already imported._

### 2. `backend/constants.py` — New constants added inline

- `CROWDSOURCE_SOLD_THRESHOLD: int = _get_config("CROWDSOURCE_SOLD_THRESHOLD", 3, int)`
- `SOFT_DELETED_RETENTION_DAYS: int = _get_config("SOFT_DELETED_RETENTION_DAYS", 30, int)`
- `REPORTED_SOLD_RETENTION_DAYS: int = _get_config("REPORTED_SOLD_RETENTION_DAYS", 7, int)`
- `STALE_ITEM_DAYS: int = _get_config("STALE_ITEM_DAYS", 14, int)`

  _No new imports needed — `_get_config` is local, constants declared as module-level variables._

### 3. `backend/main.py` — Schema migration block

- In `startup_event()`, add a new try/except block (Phase 3) after the TECH-21b block:
  - `ALTER TABLE items ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active'`
  - `CREATE TABLE IF NOT EXISTS sold_reports (...)` — use raw DDL for idempotent creation
  - Log with prefix `✅ TECH-22 schema migration verified`

  _No new imports needed for migration DDL — `text`, `engine` already imported._

### 4. `backend/schemas.py` — New/modified Pydantic models

- **Modify `ItemBase`:**
  - Add `status: Optional[str] = "active"`

- **Modify `ItemResponse`:**
  - Add `status: str = "active"`

- **New `SoldReportCreate`:**
  - `init_data: str` _(for Telegram auth, no direct fields — item_id comes from path)_

- **New `SoldReportResponse`:**
  - `id: int`, `user_id: int`, `item_id: int`, `created_at: datetime`
  - `report_count: Optional[int] = None` _(injected by route, populated when querying)_
  - `Config.from_attributes = True`

  _Imports already present: `BaseModel`, `Optional`, `datetime`, `List`._

### 5. `backend/api/routes/items.py` — New endpoints + auth helper + filter addition

**New imports needed (add at top):**
```python
import os
import httpx
from sqlalchemy import func as sql_func
from models import SoldReport, Notification, User
from constants import CROWDSOURCE_SOLD_THRESHOLD
from schemas import SoldReportCreate, SoldReportResponse
from services.analytics import AnalyticsService  # already imported
```

- **`_auth_user_from_init_data(init_data: str, db: Session) -> User`** — Copy the helper from `channels.py` (lines 125-166) into items.py as a module-level function. Mirror exact logic: parse init_data, extract telegram_id, lookup or auto-create User, return User. _Rationale: avoids circular import from channels route._

- **`_send_owner_dm(db: Session, channel_id: int, message: str) -> None`** — Helper function:
  1. Query Channel by id to get `registered_by`
  2. If `registered_by` is None, return (no DM for anonymous channels)
  3. Read `BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")`
  4. If BOT_TOKEN is set, use `httpx.AsyncClient(timeout=10.0)` to POST to `https://api.telegram.org/bot{BOT_TOKEN}/sendMessage` with `chat_id=channel.registered_by` and `text=message`
  5. Log warning on failure (do not raise — DM is best-effort)
  6. _Note: This mirrors the pattern in channels.py lines 271-295 and 363-381._

- **`POST /items/{item_id}/report`** — `report_item_as_sold`:
  1. `item_id: int`, `body: SoldReportCreate`, `db: Session = Depends(get_db)`
  2. Call `_auth_user_from_init_data(body.init_data, db)` → get `user`
  3. Query `Item` by `item_id` → raise 404 if missing
  4. Check ownership: query `Channel` by `item.channel_id`; if `channel.registered_by == user.telegram_id` → raise 403 `"You cannot report your own product"`
  5. Check duplicate: query `SoldReport` where `user_id == user.id AND item_id == item_id` → if exists, raise 409 `"You already reported this as sold."`
  6. Create `SoldReport(user_id=user.id, item_id=item_id)`, `db.add`, `db.commit`
  7. Count reports: `report_count = db.query(sql_func.count(SoldReport.id)).filter(SoldReport.item_id == item_id).scalar()`
  8. If `report_count >= CROWDSOURCE_SOLD_THRESHOLD` (and item.status currently `"active"`):
     - Set `item.status = "reported_sold"`, `db.commit`
     - Call `_send_owner_dm(db, item.channel_id, f"⚠️ Your listing '{item.title}' on @{channel.username} has been reported as sold by {report_count} buyers. It has been hidden from search. If this is incorrect, re-list it from your Stores tab.")`
  9. Return `{"status": "reported", "report_count": report_count}`

- **`POST /items/{item_id}/relist`** — `relist_item`:
  1. `item_id: int`, `body: SoldReportCreate`, `db: Session = Depends(get_db)`
  2. Call `_auth_user_from_init_data(body.init_data, db)` → get `user`
  3. Query `Item` by `item_id` → raise 404
  4. Query `Channel` by `item.channel_id`; if `channel.registered_by != user.telegram_id` → raise 403 `"Only the channel owner can re-list this item"`
  5. If item.status is already `"active"` and there are no SoldReport records → return `{"status": "already_active", "message": "Item was never reported"}`
  6. Delete all `SoldReport` records: `db.query(SoldReport).filter(SoldReport.item_id == item_id).delete()`
  7. Set `item.status = "active"`, `db.commit`
  8. Return `{"status": "active", "message": "Item re-listed successfully"}`

- **`GET /items/recent`** — Add filter: exclude non-active statuses. Modify the select statement to add `.where(Item.status == "active")`.
- **`GET /items/{item_id}`** — No status filter (still show item with any status for product page visibility).
- **`GET /items/{item_id}/related`** — Add filter: add `.where(Item.status == "active")` to the related items query (after the image search returns results, filter them client-side for status).

### 6. `backend/services/search.py` — Status filter in search SQL

- **In `_execute_search_sql`** (line 65 WHERE clause):
  - Add condition: `AND i.status = 'active'` to the WHERE clause of `scored_items` CTE.

  _This ensures search results only return active items. No import changes needed._

### 7. `backend/services/recommendation.py` — Status filter in feed queries

- **In `get_recent_items`** (line 36): Add `.where(Item.status == "active")` to the select.
- **In `get_trending_items`** (multiple item lookups): Add `.where(Item.status == "active")` to the select at line 68.
- **In `get_session_feed`** (line 107): Add `.where(Item.status == "active")` to the select.
- **In `get_discovery_feed`** (line 166): Add `.where(Item.status == "active")` to the sub_query.
- **In `get_wildcard_feed`** (line 223): Add `.where(Item.status == "active")` to the select.

  _No import changes needed._

### 8. `backend/services/cleanup.py` — NEW FILE

**Imports:**
```python
import os
import logging
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from database import SessionLocal
from models import Item, Channel, UserInteraction
from constants import (
    SOFT_DELETED_RETENTION_DAYS,
    REPORTED_SOLD_RETENTION_DAYS,
    STALE_ITEM_DAYS,
)
```

**Functions:**

- **`_send_cleanup_dm(channel_id: int, message: str) -> None`** — Same pattern as `_send_owner_dm` in items.py: query Channel, get registered_by, send via Telegram Bot API, log on failure.

- **`run_daily_cleanup() -> dict`** — Top-level synchronous function, returns summary dict:
  1. Create `db = SessionLocal()`
  2. **Soft-deleted cleanup:** Query `Item` where `status == "soft_deleted"` AND `created_at < (now_utc - timedelta(days=SOFT_DELETED_RETENTION_DAYS))`. For each item: attempt `_send_cleanup_dm` (message includes item title and channel username). Then `db.delete(item)`. Count deleted.
  3. **Reported-sold cleanup:** Query `Item` where `status == "reported_sold"` AND `created_at < (now_utc - timedelta(days=REPORTED_SOLD_RETENTION_DAYS))`. For each item: attempt `_send_cleanup_dm` (message: `"🗑️ Your listing '[title]' was removed after being reported sold and unaddressed for [X] days."`). Then `db.delete(item)`. Count deleted.
  4. **Stale item flagging:** Query `Item` where `status == "active"` AND `created_at < (now_utc - timedelta(days=STALE_ITEM_DAYS))`. For each item: check if there are any `UserInteraction` records where `UserInteraction.item_id == item.id`. If zero interactions exist, set `item.status = "stale"`. (NOTE: The behavior spec says "May be outdated label" — we add a `"stale"` status value for future frontend use, but items remain visible in feed/search since they're still technically active. Alternatively, keep them active and just track staleness in a separate boolean. For this phase, add a `stale` status that retains active visibility — but wait, the search/feed filters only show `status == "active"` items. So we need `stale` to also be visible. Adjust search/feed WHERE clause to include `status IN ('active', 'stale')`.)
  5. `db.commit()`, `db.close()`
  6. Return `{"soft_deleted_removed": N, "reported_sold_removed": N, "stale_flagged": N}`

- **`run_cleanup_and_log() -> None`** — Wrapper: calls `run_daily_cleanup()`, logs results with logger.

**Registration in `backend/main.py`:**
- At the bottom of `startup_event()`, import `from services.cleanup import run_cleanup_and_log` and create a background thread or APScheduler job. Since the project has no APScheduler dependency currently, use a simple `threading.Timer`:
  ```python
  import threading
  def _schedule_cleanup():
      run_cleanup_and_log()
      threading.Timer(86400, _schedule_cleanup).start()  # 24h
  threading.Timer(60, _schedule_cleanup).start()  # first run after 60s
  ```
  Wrap in try/except to avoid blocking startup.

### 9. `frontend/src/pages/ProductPage.jsx` — Report button + status badges

**New imports:** Add `AlertTriangle, Ban, RefreshCw, Flag` from `lucide-react` (add to existing lucide import line).

**New state variables:**
- `reportLoading` (bool, default false)
- `reportError` (string | null, default null)
- `reportCount` (number | null, default null)
- `currentUserId` (number | null, default null) — read from `localStorage.getItem('index_user_id')` on mount.

**In `fetchProductData` (useEffect):**
- After fetching item data, set `reportCount` from `item.report_count` (if present in API response).
- Read `currentUserId` from localStorage.

**Below the "Alert Me" button** (in the RIGHT COL, under the price/action card), add a new section:

- **Status badge row:** Display status badge based on `item.status`:
  - `sold` → red badge: "Sold" with `Ban` icon
  - `reported_sold` → amber badge: "⚠️ Reported Sold (N reports)" with `AlertTriangle` icon
  - `stale` → gray badge: "May be outdated" with `Clock` icon
  - `active` → no badge (or green "Active" for owners)
  - `soft_deleted` or `removed` → red badge: "Removed" with `Ban` icon

- **"Report as Sold" button** (only if item.status is `active` AND `currentUserId != item.channel?.registered_by`):
  - Styled as a secondary/outline button below the status badge
  - Shows `Flag` icon + "Report as Sold"
  - On click: POST to `{API_BASE_URL}/items/{id}/report` with `init_data` from `window.Telegram.WebApp.initData`
  - On success: update `reportCount` locally, show toast "Reported! Thank you."
  - On 409: show "You already reported this as sold."
  - On 403: button should not appear (ownership check), but if it somehow fires, show "Cannot report your own product."
  - Loading state: disable button

- **"Re-list" button** (only if item.status is `reported_sold` AND `currentUserId == item.channel?.registered_by`):
  - Shows `RefreshCw` icon + "Re-list Item"
  - On click: POST to `{API_BASE_URL}/items/{id}/relist` with `init_data`
  - On success: set `item.status = "active"`, clear `reportCount`, reload or update state
  - Loading state: disable button

**Modify the GET item response handling:** After `setItem(itemData)`, set reportCount if the API response includes it.

_Note: The current GET /items/{id} endpoint does not return report_count. We can either add it to the ItemResponse schema or make a separate API call. For simplicity, add a `report_count` field to `ItemResponse` schema in `schemas.py` (injected by the route, not from DB model). In the GET /items/{id} route, add a subquery to count SoldReport records and inject into the response._

**Telegram initData access:** Use `window.Telegram?.WebApp?.initData` with a fallback — if not available (e.g., browser testing), use a dummy value. Wrap in a helper:

```javascript
const getInitData = () => {
    if (window.Telegram?.WebApp?.initData) return window.Telegram.WebApp.initData;
    return "user=%7B%22id%22%3A%200%7D"; // dummy for dev
};
```

### 10. `frontend/src/components/ItemCard.jsx` — Status badges

**New imports:** Add `Ban, AlertTriangle` from `lucide-react` to existing import line.

**Status badge logic:**
- Add a `getStatusBadge()` function (pattern matches existing `getMatchBadge()`):
  - If `item.status === 'sold'`: render an absolute-positioned top-right badge (amber/red) with `Ban` icon and "Sold" text
  - If `item.status === 'reported_sold'`: render absolute top-right badge (amber) with `AlertTriangle` and "⚠️ Reported"
  - If `item.status === 'stale'`: render a subtle gray badge "May be outdated"
  - Otherwise return null

- Insert `{getStatusBadge()}` alongside `{getMatchBadge()}` in the card render. Use different positioning (e.g., right side or below the match badge) to avoid overlap. Suggested: match badge stays top-left, status badge goes top-right (replacing the current condition badge position — maybe merge or position below).

_Note on the condition badge: The existing condition badge at `top-2 right-2` shows `item.condition`. For items with status badges, we can either replace it or abut it. To keep changes minimal, show the status badge at `top-2 right-2` for items with a non-active status, and keep the condition badge for active items only._

### 11. `backend/tests/test_tech22.py` — NEW FILE

**Test structure:** Follow existing pattern from `test_tech21.py` (httpx to localhost:8000).

**Helper functions:**
- `api_post(path, json_data)` — same as in test_tech21
- `_unique_channel()` — same pattern
- `_unique_message_id()` — same pattern

**Test cases:**

1. **T1: Report creates SoldReport** — Create test channel, create item via ingestion, POST /items/{id}/report with valid init_data, verify 200 and report_count=1.

2. **T2: Duplicate report rejected** — Report same item twice, verify 409 and "already reported" message.

3. **T3: Owner cannot report own item** — Create channel with registered_by matching test user, report own item, verify 403.

4. **T4: Threshold triggers status change** — Report item 3 times (from 3 different users or mock users), verify item status becomes "reported_sold".

5. **T5: Relist clears reports and resets status** — After T4, owner relists item, verify status returns to "active" and all SoldReport records deleted.

6. **T6: Relist on never-reported item is no-op** — Relist an active item with no reports, verify 200 with "already_active" or success message.

7. **T7: Non-owner cannot relist** — Non-owner attempts to relist, verify 403.

8. **T8: Search excludes non-active items** — After an item becomes reported_sold, verify it does not appear in text search or image search results.

9. **T9: GET item/{id} always returns item regardless of status** — After item is reported_sold, verify GET /items/{id} still returns the item.

10. **T10: ItemResponse includes status and report_count** — Verify the JSON response from GET /items/{id} includes `status` and `report_count` fields.

---

## Step-by-Step Execution (for @build agent)

### Step 1: Extend `backend/models.py`
1. Add `status = Column(String, default="active", nullable=False)` to the `Item` class. Place it after the `is_active` column. Add a comment: `# TECH-22: Item lifecycle status (active, sold, reported_sold, soft_deleted, removed, stale)`.
2. Add the `SoldReport` class after `ItemImage`. Define it exactly as in the import map above: `__tablename__ = "sold_reports"`, unique constraint on `(user_id, item_id)`, columns: `id`, `user_id` (FK users.id), `item_id` (FK items.id CASCADE), `created_at`. Add `user` and `item` relationships.
3. Run `docker compose restart backend` after completing Step 3 to apply schema.

### Step 2: Add constants to `backend/constants.py`
1. Add the four new constants after the existing TIER thresholds (line 66+): `CROWDSOURCE_SOLD_THRESHOLD` (env: `CROWDSOURCE_SOLD_THRESHOLD`, default 3), `SOFT_DELETED_RETENTION_DAYS` (env: `SOFT_DELETED_RETENTION_DAYS`, default 30), `REPORTED_SOLD_RETENTION_DAYS` (env: `REPORTED_SOLD_RETENTION_DAYS`, default 7), `STALE_ITEM_DAYS` (env: `STALE_ITEM_DAYS`, default 14).
2. Add a section comment: `# --- Sold Reports & Cleanup (TECH-22) ---` before these.

### Step 3: Add schema migration to `backend/main.py`
1. Inside `startup_event()`, after the TECH-21b migration block (after line 100), add a new try/except block with:
   - `ALTER TABLE items ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active'`
   - Raw DDL to create `sold_reports` table IF NOT EXISTS: `id SERIAL PRIMARY KEY`, `user_id INTEGER NOT NULL REFERENCES users(id)`, `item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE`, `created_at TIMESTAMPTZ DEFAULT NOW()`, `CONSTRAINT _user_item_sold_report_uc UNIQUE(user_id, item_id)`
   - Log `"✅ TECH-22 schema migration verified (items.status, sold_reports)"`
2. After the last phase (index creation), add Phase 5.5: import and schedule the cleanup task. Catch any import errors gracefully.

### Step 4: Update `backend/schemas.py`
1. Add `status: Optional[str] = "active"` to `ItemBase`.
2. Add `status: str = "active"` to `ItemResponse`.
3. Add `report_count: Optional[int] = None` to `ItemResponse` (this is injected by routes, not from the DB model — used for GET item detail responses).
4. Add `SoldReportCreate(BaseModel): init_data: str`.
5. Add `SoldReportResponse(BaseModel): id: int, user_id: int, item_id: int, created_at: datetime, report_count: Optional[int] = None` with `from_attributes = True`.

### Step 5: Add endpoints to `backend/api/routes/items.py`
1. Add the new imports at the top (os, httpx, sql_func, SoldReport, Notification, User, constants).
2. Copy `_auth_user_from_init_data` from `channels.py` as a module-level function.
3. Add `_send_owner_dm(db, channel_id, message)` helper.
4. Add `POST /items/{item_id}/report` endpoint.
5. Add `POST /items/{item_id}/relist` endpoint.
6. Modify `GET /items/recent` to filter `Item.status == "active"`.
7. Modify `GET /items/{item_id}` to inject `report_count` into response (count SoldReport records for that item_id).
8. Modify `GET /items/{item_id}/related` to filter by `status == "active"` on returned items.

### Step 6: Add status filter to `backend/services/search.py`
1. In `_execute_search_sql`, add `AND i.status = 'active'` to the WHERE clause in the `scored_items` CTE (around line 69-70).

### Step 7: Add status filter to `backend/services/recommendation.py`
1. In `get_recent_items`: add `.where(Item.status == "active")` to the select statement (line 35-36).
2. In `get_trending_items`: add `.where(Item.status == "active")` to the select at line 68.
3. In `get_session_feed`: add `.where(Item.status == "active")` to the select at line 106-107.
4. In `get_discovery_feed`: add `.where(Item.status == "active")` to the select at line 165-166.
5. In `get_wildcard_feed`: add `.where(Item.status == "active")` to the select at line 222-223.

### Step 8: Create `backend/services/cleanup.py`
1. Create the file with all imports listed in the Import Map.
2. Write `_send_cleanup_dm(channel_id, message)` — mirrors the DM helper from items.py.
3. Write `run_daily_cleanup()` — the three cleanup phases (soft-deleted removal, reported-sold removal, stale flagging).
4. Write `run_cleanup_and_log()` — wrapper with logging.
5. **IMPORTANT:** For the stale flagging, the initial filter in search/recommendation uses `status == 'active'`. If stale items should remain visible, either:
   - **Option A (recommended):** Add a boolean `is_stale` column instead of using status. Then the stale check only sets `is_stale=True` on active items. The search/feed filter stays as-is.
   - **Option B:** Use `status IN ('active', 'stale')` in search/feed WHERE clauses.
   - **Choose Option A** for this blueprint — it's cleaner: add `is_stale = Column(Boolean, default=False)` to Item model (in step 1), add a migration DDL, and the cleanup sets `is_stale=True` instead of changing status. The frontend badge reads `is_stale`.

### Step 9: Register cleanup in `backend/main.py`
1. In `startup_event()`, at the end, add a try/except block that imports `run_cleanup_and_log` from `services.cleanup` and starts a `threading.Timer` chain (run first after 60 seconds, then every 86400 seconds).
2. Catch and log any ImportError to avoid crashing startup.

### Step 10: Update `frontend/src/pages/ProductPage.jsx`
1. Add `AlertTriangle, Flag, RefreshCw, Clock` to the lucide-react import.
2. Add state variables: `reportLoading`, `reportError`, `reportCount`.
3. Add `getInitData()` helper function.
4. Add `currentUserId` from localStorage in useEffect.
5. Extract `reportCount` from item API response.
6. Add status badge rendering (between price line and action buttons).
7. Add "Report as Sold" button (conditional on status=active, not owner).
8. Add "Re-list" button (conditional on status=reported_sold, is owner).
9. Add report/relist handler functions that POST to the API.

### Step 11: Update `frontend/src/components/ItemCard.jsx`
1. Add `Ban, AlertTriangle` to lucide-react import.
2. Add `getStatusBadge()` function.
3. Render status badge in the card (alongside or replacing condition badge for non-active items).
4. Pass `item.status` and `item.is_stale` through — they're already available from the ItemResponse.

### Step 12: Create `backend/tests/test_tech22.py`
1. Create file with imports: `pytest`, `httpx`, `time`, `json`.
2. Write test helper functions (`api_post`, `_unique_channel`, `_unique_message_id`, `_create_test_item`).
3. Write the 10 test cases as described in Testing Requirements.

---

## Testing Requirements (for @build agent)

Create `backend/tests/test_tech22.py` with the following test functions:

1. **`test_report_creates_sold_report`** — Create item, report once, verify 200, verify SoldReport exists in DB (query via API or direct DB).
2. **`test_duplicate_report_rejected`** — Report same item twice, verify 409 status.
3. **`test_owner_cannot_report_own_item`** — Create channel with registered_by, create item in that channel, report with same user, verify 403.
4. **`test_threshold_triggers_status_change`** — Create item, report it 3 times (use different `init_data` values to simulate different users, or directly create SoldReport records), verify item status becomes "reported_sold".
5. **`test_relist_clears_reports`** — After status is reported_sold, owner relists, verify status returns to "active" and report_count is 0.
6. **`test_relist_noop`** — Relist an active never-reported item, verify 200 OK.
7. **`test_non_owner_cannot_relist`** — Non-owner attempts relist, verify 403.
8. **`test_search_excludes_reported_sold`** — Item is reported_sold, verify it does NOT appear in text search results.
9. **`test_get_item_always_returns`** — GET /items/{id} returns item even when reported_sold; verify status field is present.
10. **`test_item_response_has_status_and_report_count`** — Verify the JSON response from GET /items/{id} includes `status` and `report_count` top-level fields.

**Run with:** `docker compose exec backend pytest tests/test_tech22.py -v` after completing all implementation steps.

---

## Post-Implementation Verification

1. Restart backend: `docker compose restart backend`
2. Check logs: `docker compose logs backend | grep "TECH-22"`
3. Verify the column exists: `docker compose exec db psql -U $DB_USER -d $DB_NAME -c "\d items"` — should show `status` column.
4. Run tests: `docker compose exec backend pytest tests/test_tech22.py -v`
5. Check frontend: navigate to any product page, verify "Report as Sold" button appears, click it, verify error/loading states.

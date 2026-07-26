# TECH-19 Blueprint — Processing DMs, Pause/Resume, Remove with Auto-Leave

**Date:** 2026-07-26
**Parent Ticket:** NB-38
**Priority:** HIGH

---

## Goal

Implement processing notification DMs (one message edited from "pending" to "done"), channel pause/resume with DB flag and DM notification, and channel removal with Telegram `leaveChat` auto-leave and DM notification — all gated behind the `registered_by` field.

---

## Files to Modify

1. **`backend/models.py`** — Channel model: add `indexing_paused` and `is_active` columns
2. **`backend/schemas.py`** — Add new Pydantic models for channel pause/resume request and channel info response
3. **`backend/api/routes/channels.py`** — Add `GET /channels/by-username/{username}`, extend `PATCH /channels/{id}` for pause/resume, add `DELETE /channels/{id}` for remove/auto-leave
4. **`listener/client.py`** — Add `get_channel_info()` and `send_dm()` helper functions
5. **`listener/worker.py`** — Integrate processing DM lifecycle: lookup channel info, send initial DM, edit on result
6. **`listener/main.py`** — Pass the `app.bot` instance to `background_worker`
7. **`frontend/src/pages/StoresPage.jsx`** — Add confirmation modals, wire Pause/Resume/Remove buttons to API calls
8. **`listener/monitor.py`** — No changes needed; worker handles all DM logic post-dequeue

---

## Strict Import Map

### backend/models.py — New Columns on `Channel`

Add two new columns to the existing `Channel` class (no new imports needed):

| Column | Type | Default | Purpose |
|---|---|---|---|
| `indexing_paused` | `Boolean` | `False` | Gate to skip ingestion for paused channels |
| `is_active` | `Boolean` | `True` | Soft-delete flag: False when channel is removed |

These use `from sqlalchemy import Boolean` which is already imported on line 1 of `models.py`.

### backend/schemas.py — New Pydantic Models

Add the following new schemas. All required imports (`BaseModel`, `Optional`) are already present.

- **`ChannelPauseRequest`**: `indexing_paused: bool` — body for PATCH pause/resume toggle
- **`ChannelInfoResponse`**: `id: int`, `username: str`, `registered_by: Optional[int]`, `indexing_paused: bool`, `is_active: bool` — returned by the new channel-info lookup endpoint
- **`ChannelActionResponse`**: `status: str`, `message: Optional[str]` — generic response for pause/resume/remove actions

Also update **`OwnerChannelResponse`** to include `indexing_paused: bool = False` so the frontend can display real pause state.

### backend/api/routes/channels.py — New Endpoints & Models

**New Pydantic models defined locally in the routes file** (inline, not in schemas.py, to match the existing pattern of `ChannelUpdate` defined at line 23):

- **`ChannelAction`**: `init_data: str` — query param for auth on PATCH/DELETE

**New endpoint functions:**

| Function | Route | Method | Auth |
|---|---|---|---|
| `get_channel_by_username` | `/channels/by-username/{username}` | GET | Internal (X-Internal-Service header) |
| `toggle_channel_pause` | `/channels/{channel_id}/pause` | PATCH | `init_data` query param |
| `remove_channel` | `/channels/{channel_id}` | DELETE | `init_data` query param |

**New imports needed** (add to existing imports in `channels.py`):
- `from schemas import ChannelInfoResponse, ChannelPauseRequest, ChannelActionResponse` — extend existing schemas import line

**Existing imports that are already available and will be reused:**
- `import os` — already imported (for `BOT_TOKEN`)
- `import httpx` — already imported (for Telegram API calls)
- `from sqlalchemy.orm import Session` — already imported
- `from fastapi import APIRouter, Depends, HTTPException, Header` — already imported
- `from database import get_db` — already imported
- `from models import Channel, User, Item` — already imported

Add `from sqlalchemy import update` (or just use `db.query(...).first()` then set attributes — consistent with existing pattern).

### listener/client.py — New Helper Functions

**New function `get_channel_info(username: str) -> dict`:**

- Calls `GET {API_BASE}/channels/by-username/{username}` with `INTERNAL_HEADERS`
- Returns a dict with keys: `id`, `registered_by`, `indexing_paused`, `is_active`
- Returns `None` if the channel is not found or request fails
- Uses `httpx.AsyncClient(timeout=10.0)` — already imported pattern

**Existing constants reused:**
- `API_BASE` — imported from config
- `INTERNAL_HEADERS` — defined at line 5

### listener/worker.py — Processing DM Lifecycle

**Function signature change:** `background_worker(queue: asyncio.Queue, bot)` — accept bot instance as second parameter.

**New imports needed:**
- `from telegram import Bot` — for type hinting (if desired) and to access `send_message` / `edit_message_text`
- `from .client import get_channel_info` — add to existing import from client

**Existing imports that remain:**
- `asyncio` — already imported
- `send_to_api` — already imported from client (line 2)
- `logger` — already imported from config (line 3)
- `HEARTBEAT_INTERVAL`, `MAX_RETRIES_LIMIT` — already imported from config (line 3)

### listener/main.py — Pass Bot to Worker

**Line 57 change:** `asyncio.create_task(background_worker(job_queue))` changes to `asyncio.create_task(background_worker(job_queue, app.bot))`.

**No new imports needed.** The `app` parameter is already available in the `post_init` closure.

### frontend/src/pages/StoresPage.jsx — Modal & API Wiring

**New imports needed:**
- The `Pause`, `Play`, `Trash2` lucide-react icons are ALREADY imported (line 2). Keep using them.
- Add `X` from `lucide-react` for the modal close button.

**Existing hooks and utilities reused:**
- `useOwnerChannels` — already imported (line 3); extend its return value with `togglePause` and `removeChannel` functions (see below)
- `API_BASE_URL` from `../config` — will be used in new `fetch` calls
- `getAnalyticsHeaders` from `../utils/analytics` — reuse for authenticated API calls

### frontend/src/hooks/useOwnerChannels.js — Extend Hook

**New return values to add:**
- `togglePause(channelId: int, pause: bool) -> Promise` — calls `PATCH /channels/{channelId}/pause`
- `removeChannel(channelId: int) -> Promise` — calls `DELETE /channels/{channelId}`
- Both functions accept `initData` (from `window.Telegram.WebApp.initData`) and pass it as query param
- On success, call `fetchChannels()` to refresh the channel list

**No new imports needed.**

---

## Step-by-Step Execution

### Phase 1 — Database Model & Migration

**Step 1.1:** In `backend/models.py`, inside the `Channel` class (around line 122, after `registered_by`), add two new columns:
- `indexing_paused` — Boolean, default=False, nullable=False
- `is_active` — Boolean, default=True, nullable=False

**Step 1.2:** Create the ALTER TABLE migration SQL. Since the project uses SQLAlchemy's `Base.metadata.create_all()` in `main.py` startup (line 61), and SQLAlchemy does NOT auto-migrate existing tables, you must write a standalone migration block in `backend/main.py` inside `startup_event()` (Phase 2 area, around line 62) that executes:

```sql
ALTER TABLE channels ADD COLUMN IF NOT EXISTS indexing_paused BOOLEAN DEFAULT FALSE;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
```

Use `conn.execute(text(...))` within the existing `with engine.begin() as conn:` block, following the same pattern as the index creation logic starting at line 70. Use `IF NOT EXISTS` guards to make the migration idempotent on restarts.

**Step 1.3:** In `backend/schemas.py`, update `OwnerChannelResponse` (line 162) to include:
- `indexing_paused: bool = False`
- `is_active: bool = True`
- Keep the existing `is_active: bool = True` on line 170 but change it to be sourced from the DB field rather than hardcoded

Also add three new schema classes at the end of the file:
- `ChannelPauseRequest(BaseModel)` with field `indexing_paused: bool`
- `ChannelInfoResponse(BaseModel)` with fields `id: int`, `username: str`, `registered_by: Optional[int]`, `indexing_paused: bool`, `is_active: bool` (with `from_attributes = True`)
- `ChannelActionResponse(BaseModel)` with fields `status: str`, `message: Optional[str] = None`

### Phase 2 — Backend Endpoints

**Step 2.1:** Add `GET /channels/by-username/{username}` endpoint in `backend/api/routes/channels.py`. This is an internal endpoint for the listener worker:
- Accept `username: str` path parameter
- Accept `X-Internal-Service` header to verify the caller (check against `"index-listener"` — consistent with the `INTERNAL_HEADERS` defined in `listener/client.py`)
- Query `db.query(Channel).filter(Channel.username == username).first()`
- Return 404 if not found
- Return `ChannelInfoResponse` with the channel's id, username, registered_by, indexing_paused, is_active
- Use existing `Depends(get_db)` for DB session

**Step 2.2:** Extend the existing `PATCH /channels/{channel_id}` endpoint (line 34) to also accept pause/resume toggling. There are two approaches; choose the cleaner one:

*Option A (recommended):* Create a separate `PATCH /channels/{channel_id}/pause` endpoint to avoid overloading the existing photo-update endpoint:
- Accept query param `init_data: str` for authentication
- Accept body as `ChannelPauseRequest` with `indexing_paused: bool`
- Authenticate via `_auth_user_from_init_data(init_data, db)` (already defined at line 124)
- Load channel: `db.query(Channel).filter(Channel.id == channel_id, Channel.registered_by == user.telegram_id).first()`
- Return 404 if not found or not owned by user
- Set `channel.indexing_paused = body.indexing_paused`
- Commit and refresh
- **Send DM using Telegram Bot API**: Use `BOT_TOKEN` and `httpx` to call `sendMessage` to the owner (channel.registered_by). The message text differs for pause vs resume:
  - Pause: "⏸️ @{channel.username} is paused. Your products remain indexed but new posts won't appear. Tap Resume in Stores anytime."
  - Resume: "▶️ @{channel.username} is active again. New posts will appear in the marketplace."
- Return `ChannelActionResponse(status="ok")`
- If the DM send fails, log a warning but still return success (the DB change is the source of truth)

**Step 2.3:** Add `DELETE /channels/{channel_id}` endpoint:
- Accept query param `init_data: str` for authentication
- Authenticate via `_auth_user_from_init_data(init_data, db)`
- Load channel: `db.query(Channel).filter(Channel.id == channel_id, Channel.registered_by == user.telegram_id).first()`
- Return 404 if not found or not owned by user
- Call Telegram `getChat` API via `httpx` to get the channel's numeric chat_id: `https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id=@{channel.username}`
- If `getChat` succeeds, extract the `result.id` and call `leaveChat`: `https://api.telegram.org/bot{BOT_TOKEN}/leaveChat?chat_id={chat_id}`
- If `leaveChat` fails (bot already removed, etc.), log the error but continue — per Rule 3.3, the DB is still updated
- Mark channel as removed: set `channel.is_active = False`
- Commit DB changes
- **Send DM** via `sendMessage` API: "👋 I've left @{channel.username}. Your existing products stay indexed. Add me back anytime to resume."
- If the DM send fails, log a warning but still return success
- Return `ChannelActionResponse(status="ok")`

**Step 2.4:** In `GET /channels/mine` (line 171), update the query to filter out inactive channels: add `Channel.is_active == True` to the `select(Channel).where(...)` clause. Also, in the `OwnerChannelResponse` construction (line 193), replace the hardcoded `is_active=True` with `is_active=not channel.indexing_paused` so the frontend badge reflects the real pause state (green "ACTIVE" vs amber "PAUSED").

### Phase 3 — Listener: Processing DM Lifecycle

**Step 3.1:** In `listener/client.py`, add a new async function `get_channel_info(username: str) -> Optional[dict]`:
- Accept a Telegram channel username (without `@` prefix)
- Call `GET {API_BASE}/channels/by-username/{username}` with `INTERNAL_HEADERS`
- On success (200), return the JSON dict
- On failure (404, connection error, etc.), log a warning and return `None`
- Use `httpx.AsyncClient(timeout=10.0)` — consistent with existing pattern

**Step 3.2:** In `listener/worker.py`, modify `background_worker` to accept a second argument `bot` (the `telegram.Bot` instance). The new processing loop inside the `while True` block, after pulling a payload from the queue and BEFORE calling `send_to_api`:

1. Extract `channel_name` from the payload
2. Call `get_channel_info(channel_name)` to look up channel metadata
3. If the channel is not found in DB (returns None), proceed with the API call as before (no DM, no skip — the ingestion endpoint will auto-create the channel)
4. If `channel_info.get('indexing_paused')` is True, log that the channel is paused, skip the API call entirely, call `queue.task_done()`, and `continue` to the next job
5. If `channel_info.get('is_active')` is False, log that the channel was removed, skip the API call, call `queue.task_done()`, and `continue`
6. If `channel_info.get('registered_by')` is set (non-None, non-zero):
   - Send initial DM via `await bot.send_message(chat_id=registered_by, text="⏳ Processing your post from @{channel_name}...")`
   - Capture the returned `telegram.Message` object to get the `message_id` for editing
7. Call `send_to_api(payload)` as before — capture the return value (`success: bool`)
8. After the API call:
   - **If success** AND a DM was sent:
     - Call `send_to_api` a second time? No — we need the extracted data. But `send_to_api` currently returns only `bool`. We need it to return richer data.
     
     **WAIT — Design Decision:** Modify `send_to_api` to return `Optional[dict]` instead of `bool`. The dict contains:
     - `success: bool`
     - `item_id: Optional[int]`
     - `title: Optional[str]`
     - `price: Optional[float]`
     - `status_code: int`
     
     Then in worker.py, after `result = await send_to_api(payload)`:
     - If `result['success']` and DM was sent: Edit the DM message to `"✅ Indexed: {title} — {price} ETB"` (or `"Ask for Price"` if price is None/0)
     - If `not result['success']` and DM was sent: Edit the DM to `"❌ Could not process your post from @{channel_name}. The post may not contain a product or an image."`
9. If no `registered_by` is set, skip all DM logic — just call `send_to_api` as before

**Step 3.3:** In `listener/client.py`, refactor `send_to_api`:
- Change return type from `bool` to `Optional[dict]`
- On HTTP 200 success, parse the response JSON to extract `item_id` from `data.get('item_id')`, `title` from `data.get('extracted_data', {}).get('title')`, `price` from `data.get('extracted_data', {}).get('price')`
- Return dict: `{"success": True, "item_id": ..., "title": ..., "price": ..., "status_code": 200}`
- On failure (non-200, exception), return `{"success": False, "status_code": status_code_if_any, "error": str(e)}`
- The retry logic in worker.py currently checks `success = await send_to_api(payload)` — update to check `result and result.get('success')`

**Step 3.4:** In `listener/main.py`, inside the `post_init` async function (around line 57), change:
```python
asyncio.create_task(background_worker(job_queue))
```
to:
```python
asyncio.create_task(background_worker(job_queue, app.bot))
```

### Phase 4 — Frontend Confirmation Modals & API Wiring

**Step 4.1:** In `frontend/src/hooks/useOwnerChannels.js`, add two new functions to the hook's return value:

- **`togglePause(channelId, pause)`**: 
  - `POST` or `PATCH` to `${API_BASE_URL}/channels/${channelId}/pause?init_data=${encodeURIComponent(initData)}` with body `JSON.stringify({indexing_paused: pause})`
  - `Content-Type: application/json`
  - On success, call `fetchChannels()` to refresh
  - On failure, set `error` state

- **`removeChannel(channelId)`**:
  - `DELETE` to `${API_BASE_URL}/channels/${channelId}?init_data=${encodeURIComponent(initData)}`
  - On success, call `fetchChannels()` to refresh (the channel will disappear since `GET /mine` will exclude inactive ones)
  - On failure, set `error` state

Both functions reuse the `getInitData()` helper already in the hook (line 14). If `initData` is null (not in Telegram), return early with `setError('NOT_IN_TELEGRAM')`.

**Step 4.2:** In `frontend/src/pages/StoresPage.jsx`, add state for the confirmation modal:
- `const [modalState, setModalState] = useState(null)` where `null` = closed, and non-null = `{ type: 'pause' | 'resume' | 'remove', channel }`
- Add `const [actionLoading, setActionLoading] = useState(false)` to track API call in progress

**Step 4.3:** Destructure `togglePause` and `removeChannel` from the `useOwnerChannels()` hook call (line 6).

**Step 4.4:** Replace the disabled Pause/Resume button (lines 113-119) with an enabled button that:
- Calls `setModalState({ type: channel.is_active ? 'pause' : 'resume', channel })` on click
- Uses the `Pause` icon for active channels, `Play` icon for paused channels
- Text: "Pause" or "Resume" based on `is_active`
- Styling: Use `bg-brand-50 text-brand-700` for active state, `bg-amber-50 text-amber-700` for paused state (replace the muted gray disabled styles)

**Step 4.5:** Replace the disabled Remove button (lines 120-127) with an enabled button that:
- Calls `setModalState({ type: 'remove', channel })` on click
- Uses `Trash2` icon
- Text: "Remove"
- Styling: `bg-red-50 text-red-600 hover:bg-red-100` (replace the gray disabled styles)

**Step 4.6:** Render a confirmation modal component when `modalState` is not null. The modal should be a fixed overlay (`fixed inset-0 z-50 flex items-center justify-center`) with a backdrop (`bg-black/40`) and a centered card (`bg-white rounded-2xl p-6 max-w-sm w-full mx-4 shadow-xl`).

Modal content varies by type:
- **Pause:** Title "Pause Indexing", body "Pause indexing for @{channel.username}? Your products stay in the catalog but new posts won't appear. You can resume anytime.", primary button "Pause" (brand-600), secondary "Cancel"
- **Resume:** No confirmation modal needed per spec (Rule 2.5) — call `togglePause` directly on button click, no modal
- **Remove:** Title "Remove Channel", body "Remove @{channel.username} from Index Gebeya? The bot will leave your channel. Existing products stay in the catalog but new posts won't be indexed. You can add the bot back anytime.", primary button "Remove" (red-600), secondary "Cancel"

Modal buttons:
- Primary button calls the appropriate action (`togglePause` or `removeChannel`), sets `setActionLoading(true)`, waits for completion, then closes modal and sets `setActionLoading(false)`
- Secondary "Cancel" button simply closes the modal (`setModalState(null)`)
- Disable both buttons while `actionLoading` is true, show a spinner on the primary button

**Step 4.7:** In the channel card's status badge (line 79-87), update the logic to use `indexing_paused` instead of `is_active` for the Paused indicator:
- If `channel.indexing_paused` → amber badge "PAUSED"
- If not paused → green badge "ACTIVE"

The `is_active` from the backend already reflects `not channel.indexing_paused` (set in Step 2.4), so the existing badge logic still works correctly. No change needed — just verify the data flows right.

### Phase 5 — Monitor Skip for Paused Channels

**Step 5.1:** In `listener/monitor.py`, the `handle_channel_post` function does NOT need modification. The skip logic is handled in the worker (Step 3.2, points 4-5). The monitor simply captures posts and puts them on the queue; the worker checks `indexing_paused` before making the API call. This keeps the monitor's critical path fast and avoids adding an HTTP call per captured post.

---

## Testing Requirements

### Backend Tests (add to `backend/tests/test_channels.py` or create `backend/tests/test_tech19.py`)

1. **Channel Info Lookup (GET /channels/by-username/{username}):**
   - Create a channel, query it, verify all fields (including `indexing_paused` and `is_active`) are returned
   - Query a non-existent username → 404

2. **Pause Channel (PATCH /channels/{id}/pause):**
   - Create a channel with `registered_by` set to a test user's telegram_id
   - Call PATCH with valid init_data → verify `indexing_paused` becomes True
   - Call PATCH with non-owner init_data → verify 404 (channel not found for that user)
   - Call PATCH without init_data → verify 403

3. **Resume Channel (PATCH /channels/{id}/pause):**
   - Toggle `indexing_paused` back to False → verify flag cleared

4. **Remove Channel (DELETE /channels/{id}):**
   - Mock `httpx` calls to Telegram API (`getChat`, `leaveChat`, `sendMessage`)
   - Call DELETE with valid init_data → verify `is_active` becomes False
   - Verify `leaveChat` is called with correct chat_id
   - If `leaveChat` throws (mock exception) → verify `is_active` is still set to False (Rule 3.3)
   - Call DELETE with non-owner init_data → verify 404

5. **Get My Channels excludes removed:**
   - Create two channels for a user, remove one via DELETE
   - Call GET /channels/mine → only the active channel is returned

### Listener Tests

6. **Worker skips paused channel:**
   - Mock `get_channel_info` to return `indexing_paused=True`
   - Push a job to the queue
   - Verify `send_to_api` is NOT called
   - Verify the job is dequeued via `task_done()`

7. **Worker skips removed channel:**
   - Mock `get_channel_info` to return `is_active=False`
   - Verify `send_to_api` is NOT called

8. **Worker sends and edits DM for registered channel:**
   - Mock `get_channel_info` to return `registered_by=12345`
   - Mock `send_to_api` to return success with title/price
   - Verify `bot.send_message` is called with initial "⏳ Processing..." text
   - Verify `bot.edit_message_text` is called with "✅ Indexed: ..." text
   - Verify edit includes the title and price from the API response

9. **Worker sends failure DM on API error:**
   - Mock `send_to_api` to return failure
   - Verify DM is edited to "❌ Could not process..." text

10. **Worker does NOT send DM when registered_by is None:**
    - Mock `get_channel_info` to return `registered_by=None`
    - Verify `bot.send_message` is NEVER called

11. **send_to_api returns enriched dict:**
    - Verify the return type is a dict with keys: `success`, `item_id`, `title`, `price`, `status_code`
    - Verify backwards compatibility: callers that checked `if await send_to_api(payload):` can now check `result.get('success')`

### Frontend Tests

12. **Modal opens on Pause click:**
    - Render a channel card with `is_active=True`
    - Click the Pause button
    - Verify modal appears with correct channel name and confirmation text
    - Click Cancel → modal closes
    - Click Confirm → API call fires, modal closes, channel list refreshes

13. **Resume fires immediately (no modal):**
    - Render a channel card with `is_active=False` (paused)
    - Click the Resume button
    - Verify API call fires directly, no modal appears

14. **Modal opens on Remove click:**
    - Click the Remove button
    - Verify modal appears with warning text
    - Click Confirm → API call fires, channel disappears from list

15. **Error state on API failure:**
    - Mock API to return 500
    - Click Confirm → verify error message is displayed to user

# TECH-07: Channel and User Profile Photos — Implementation Blueprint

**Date:** 2026-07-24
**Parent Ticket:** NB-22
**Goal:** Replace letter-avatar placeholders on product pages and review cards with real photos: channel profile pictures fetched via Telegram Bot API, and user profile photos captured from the Mini App's initData during review submission.

---

## Files to Modify/Create

| Action  | File Path                                      |
|---------|------------------------------------------------|
| MODIFY  | `backend/models.py`                            |
| MODIFY  | `backend/schemas.py`                           |
| MODIFY  | `backend/api/routes/ingestion.py`              |
| MODIFY  | `backend/api/routes/reviews.py`                |
| CREATE  | `backend/api/routes/channels.py`               |
| MODIFY  | `backend/main.py`                              |
| MODIFY  | `listener/config.py`                           |
| CREATE  | `listener/photo_refresher.py`                  |
| MODIFY  | `listener/main.py`                             |
| MODIFY  | `frontend/src/pages/ProductPage.jsx`           |

No changes to `ReviewModal.jsx` — review photos are displayed in the review list section within `ProductPage.jsx`, not in the submission modal. (The tech backlog's affected-files mapping to `ReviewModal.jsx` is superseded by the actual component layout observed in the codebase.)

---

## Strict Import Map

### 1. New imports for `backend/api/routes/ingestion.py`

| Import Statement                                           | Purpose                                              |
|------------------------------------------------------------|------------------------------------------------------|
| `import os`                                                | Already imported (line 1)                            |
| `import httpx`                                             | Call Telegram Bot API (`getChat`) for photo fetch    |
| (no new model imports needed — `Channel` already imported) |                                                      |

### 2. New imports for `backend/api/routes/reviews.py`

No new imports required. The `validate_telegram_data()` function already parses the `user` JSON object from initData. We only need to extract the `photo_url` key from the dictionary it returns.

### 3. New imports for `backend/api/routes/channels.py` (NEW FILE)

| Import Statement                               | Purpose                                                 |
|------------------------------------------------|---------------------------------------------------------|
| `import os`                                    | Read `TELEGRAM_BOT_TOKEN` from environment              |
| `import httpx`                                 | Call Telegram Bot API (`getFile`) for photo download URL|
| `from fastapi import APIRouter, Depends, HTTPException` | Route definition and error handling               |
| `from fastapi.responses import RedirectResponse` | Redirect client to Telegram CDN for the photo         |
| `from sqlalchemy.orm import Session`           | Database session dependency                             |
| `from database import get_db`                  | Dependency injection for DB session                     |
| `from models import Channel`                   | Query the channel record                                |
| `from schemas import ChannelResponse`          | Response model for list/update endpoints                |
| `from typing import List`                      | Return type hint for list endpoint                      |
| `import logging`                               | Logging                                                 |

### 4. New imports for `listener/photo_refresher.py` (NEW FILE)

| Import Statement                                   | Purpose                                             |
|----------------------------------------------------|-----------------------------------------------------|
| `import asyncio`                                   | `asyncio.sleep()` for 24-hour loop                  |
| `from telegram import Bot`                         | Type hint for the bot instance                      |
| `from telegram.error import TelegramError`         | Handle failed `get_chat` calls gracefully           |
| `import httpx`                                     | Call backend API endpoints (list channels, update)  |
| `from config import logger, API_BASE`              | Logging and API URL construction                    |

### 5. New imports for `listener/main.py`

| Import Statement                                          | Purpose                                      |
|-----------------------------------------------------------|----------------------------------------------|
| `from photo_refresher import channel_photo_refresher`     | Register the daily background task           |

### 6. New column additions — `backend/models.py`

**Channel model** — add one new column after `is_verified` (line 119) and before `created_at` (line 121):

| Column             | Type        | Constraints | Purpose                                              |
|--------------------|-------------|-------------|------------------------------------------------------|
| `photo_file_id`    | `String`    | nullable    | Telegram's `big_file_id` for the channel's profile photo |

**Review model** — add one new column after `comment` (line 140) and before `created_at` (line 141):

| Column             | Type        | Constraints | Purpose                                              |
|--------------------|-------------|-------------|------------------------------------------------------|
| `user_photo_url`   | `Text`      | nullable    | URL to the reviewer's Telegram profile photo          |

### 7. New fields in `backend/schemas.py`

**`ChannelResponse` schema** — add one new field after `review_count` (line 16):

| Field              | Type                  | Purpose                                         |
|--------------------|-----------------------|-------------------------------------------------|
| `photo_file_id`    | `Optional[str]` = None| Internal field for the listener's daily refresher|

**`ReviewResponse` schema** — add one new field after `comment` (line 35):

| Field              | Type                  | Purpose                                         |
|--------------------|-----------------------|-------------------------------------------------|
| `user_photo_url`   | `Optional[str]` = None| URL to reviewer's profile photo (from Telegram CDN)|

### 8. No new exports

No existing exports are modified. The new `channels.py` route module and `photo_refresher.py` module are additive.

---

## Architectural Decisions

### A. Backend calls Telegram API directly (not proxied through listener)

The backend already reads `TELEGRAM_BOT_TOKEN` from the environment (used in `reviews.py` for HMAC validation). Both `ingestion.py` (photo fetch on first encounter) and `channels.py` (photo redirect endpoint) will call the Telegram Bot API directly using `httpx`. This avoids adding latency through the listener and keeps the API self-contained.

### B. Photo serving uses HTTP 307 redirect to Telegram CDN

The `GET /channels/{channel_id}/photo` endpoint does NOT proxy or download the image. Instead, it:
1. Resolves `photo_file_id` → `file_path` via `getFile`
2. Returns `RedirectResponse(url=f"https://api.telegram.org/file/bot{TOKEN}/{file_path}", status_code=307)`

This avoids consuming backend bandwidth, and photos served from Telegram's CDN will auto-update when the channel changes their profile picture. A 307 (Temporary Redirect) is used instead of 301 because the underlying CDN URL may rotate.

### C. Photo fetch on first ingestion is fire-and-forget (non-blocking)

In `ingestion.py`, the `getChat` call to fetch the channel photo happens inline during ingestion. If it fails (network error, rate limit, channel has no photo), the error is logged at WARNING level and ingestion proceeds normally. A missing photo does not block item creation.

### D. Daily refresh runs as an asyncio background task in the listener

The listener already has two background tasks (`background_worker`, `notification_poller`) launched in `main.py`'s `post_init` hook. The new `channel_photo_refresher` follows the same pattern. It loops forever with a 24-hour sleep between cycles.

---

## Step-by-Step Execution

---

### PHASE 1: Database Models (`backend/models.py`)

#### Step 1: Add `photo_file_id` to `Channel`

In the `Channel` class (line 108), insert a new column after `is_verified` (line 119) and before `created_at` (line 121):

- Column name: `photo_file_id`
- Type: `Column(String, nullable=True)`
- Purpose: stores the `big_file_id` from Telegram's `ChatPhoto` object

#### Step 2: Add `user_photo_url` to `Review`

In the `Review` class (line 128), insert a new column after `comment` (line 140) and before `created_at` (line 141):

- Column name: `user_photo_url`
- Type: `Column(Text, nullable=True)`
- Purpose: stores the `photo_url` field from Telegram Mini App initData

---

### PHASE 2: Schema Updates (`backend/schemas.py`)

#### Step 3: Add `photo_file_id` to `ChannelResponse`

In the `ChannelResponse` class (line 14), add a new field after `review_count` (line 16):

- Field: `photo_file_id: Optional[str] = None`

This field is for internal use (the listener daily refresher reads it to compare).

#### Step 4: Add `user_photo_url` to `ReviewResponse`

In the `ReviewResponse` class (line 30), add a new field after `comment` (line 35):

- Field: `user_photo_url: Optional[str] = None`

This field is returned in API responses so the frontend can display reviewer photos.

---

### PHASE 3: Channel Photo Fetch on First Ingestion (`backend/api/routes/ingestion.py`)

#### Step 5: Add `import httpx` and `import os`

At the top of `ingestion.py`, add `import httpx` (alongside the existing `import os` at line 1) if not already present. Verify that `import os` is already there (it is — line 1).

#### Step 6: Fetch channel photo after channel resolution

After the channel resolution block (after line 98: `db.flush()`), insert a conditional block that fetches the channel photo if `photo_file_id` is None.

Logic:
- Check: `if channel.photo_file_id is None:`
- Inside the block:
  1. Construct the Telegram API URL for `getChat`:
     - `url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id=@{channel.username}"`
     - Use `os.getenv("TELEGRAM_BOT_TOKEN")` — the backend already reads this env var in `reviews.py`
  2. Make an async GET request using `httpx.AsyncClient(timeout=10.0)`:
     ```python
     async with httpx.AsyncClient(timeout=10.0) as client:
         response = await client.get(url)
         if response.status_code == 200:
             data = response.json()
             if data.get("ok") and data["result"].get("photo"):
                 channel.photo_file_id = data["result"]["photo"]["big_file_id"]
                 logger.info(f"📸 Fetched photo for channel @{channel.username}")
             else:
                 logger.info(f"ℹ️ Channel @{channel.username} has no photo")
         else:
             logger.warning(f"⚠️ Failed to fetch chat info for @{channel.username}: {response.status_code}")
     ```
  3. If the request fails or the channel has no photo, log a warning and continue — do NOT raise an exception. Ingestion must not be blocked.
  4. If a photo was fetched, the `channel.photo_file_id` is already set on the ORM object (which was added to the session). It will be committed with the next `db.commit()` (either in the dedup block or the item creation block below).

- **Edge cases handled:**
  - Channel with no photo → `result.photo` is absent → log info, continue.
  - Network error → `httpx` raises exception → catch with try/except, log warning, continue.
  - Rate limiting from Telegram → 429 status → log warning, continue (photo will be fetched by the daily refresher later).

- **Async safety:** The `parse_telegram_post` endpoint is already `async def`. The `httpx.AsyncClient` call is awaitable and will not block the event loop.

- **Token security:** Read `BOT_TOKEN` from `os.getenv("TELEGRAM_BOT_TOKEN")` at the top of the function, not as a module-level constant (same pattern as `reviews.py` line 18).

---

### PHASE 4: New Channels Route (`backend/api/routes/channels.py` — CREATE)

Create a new file at `backend/api/routes/channels.py` with three endpoints.

#### Step 7: Create the file with imports

Create the file with the imports listed in the Import Map (section 3 above). Also add:

```python
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
router = APIRouter()
logger = logging.getLogger("index_channels")
```

#### Step 8: Add `GET /channels/` — List active channels

Purpose: Used by the listener's daily photo refresher to discover all channels.

- Route: `@router.get("/", response_model=List[ChannelResponse])`
- Implementation: Query all `Channel` rows from the database, return as a list.
- No authentication required (this is an internal endpoint called by the listener within the Docker network). The listener already uses `X-Internal-Service` headers for other endpoints.
- Use a simple `db.query(Channel).all()` call.
- This endpoint returns `photo_file_id` in the response (via `ChannelResponse` schema) so the listener can compare it against the current Telegram value.

#### Step 9: Add `PATCH /channels/{channel_id}` — Update channel

Purpose: Used by the listener's daily refresher to update `photo_file_id` when it changes.

- Route: `@router.patch("/{channel_id}", response_model=ChannelResponse)`
- Accept a JSON body with an optional `photo_file_id` field and an optional `title` field.
- Query the channel by ID, update the provided fields, commit, and return the updated channel.
- If the channel does not exist, return 404.
- The request body schema should be a simple Pydantic model: `ChannelUpdate(photo_file_id: Optional[str] = None, title: Optional[str] = None)`.

Define a new Pydantic model inside `channels.py` (not in `schemas.py` since it's only used internally):

```python
from pydantic import BaseModel

class ChannelUpdate(BaseModel):
    photo_file_id: Optional[str] = None
    title: Optional[str] = None
```

#### Step 10: Add `GET /channels/{channel_id}/photo` — Serve channel photo

Purpose: Called by the frontend to display the channel's profile picture.

- Route: `@router.get("/{channel_id}/photo")`
- Steps:
  1. Query the channel by ID. If not found, return 404.
  2. If `channel.photo_file_id` is None, return 404 with detail `"No photo available for this channel"`.
  3. Call the Telegram Bot API `getFile` endpoint:
     - `url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={channel.photo_file_id}"`
     - Use `httpx.AsyncClient(timeout=10.0)` for the async GET request.
  4. Parse the response. If `ok` is true, extract `result.file_path`.
  5. Construct the download URL: `f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"`
  6. Return `RedirectResponse(url=download_url, status_code=307)` — a Temporary Redirect so the browser fetches the image directly from Telegram's CDN.
- Error handling:
  - If `getFile` fails (network error, invalid file_id), return 502 with detail `"Failed to resolve photo URL"`.
  - Log the error at WARNING level.
- **Performance note:** This endpoint makes an outbound HTTP call on every request. To avoid this on every product page load, the `@build` agent should add `Cache-Control` headers on the redirect response:
  - `Cache-Control: public, max-age=3600` (browser cache for 1 hour)
  - This way, repeat visits within an hour don't hit the endpoint at all.

#### Step 11: Register the channels router in `backend/main.py`

In `main.py`:
- Add the import: `from api.routes import channels` (line 12, alongside the other route imports)
- Add the router registration: `app.include_router(channels.router, prefix="/channels", tags=["Channels"])` (after the existing router registrations, around line 134)

---

### PHASE 5: Capture User Photo During Review Submission (`backend/api/routes/reviews.py`)

#### Step 12: Extract `photo_url` from initData

In the `create_review` function (line 54), after the `tg_user` dict is parsed (line 60):

- Extract `photo_url = tg_user.get("photo_url")` — this field is present in Telegram Mini App initData for users who have public profile photos.
- If `photo_url` is not present, it will be `None` (handled by the nullable column).

#### Step 13: Store `photo_url` on the Review record

In the `Review` constructor call (line 88), add the `user_photo_url` field:

- `user_photo_url=photo_url`

The existing constructor call:
```python
new_review = Review(
    user_id=user.id,
    channel_id=payload.channel_id,
    rating=payload.rating,
    comment=payload.comment
)
```
Should become:
```python
new_review = Review(
    user_id=user.id,
    channel_id=payload.channel_id,
    rating=payload.rating,
    comment=payload.comment,
    user_photo_url=photo_url
)
```

No other changes needed in this file — the `ReviewResponse` schema (already updated in Step 4) will now include `user_photo_url` in API responses automatically via `from_attributes = True`.

---

### PHASE 6: Listener Daily Photo Refresh

#### Step 14: Add config setting (`listener/config.py`)

Add a new configuration constant after `ALBUM_BUFFER_DELAY` (line 32):

```python
# CHANNEL PHOTO REFRESH (in seconds — default to 24 hours)
CHANNEL_PHOTO_REFRESH_INTERVAL = float(os.getenv("PHOTO_REFRESH_INTERVAL", "86400.0"))
```

This allows tuning the interval via environment variable for testing (e.g., set to 60 for 1-minute refresh during development).

#### Step 15: Create `listener/photo_refresher.py` (NEW FILE)

Create a new module with a single async function `channel_photo_refresher(bot: Bot)`.

**Function signature:**
```python
async def channel_photo_refresher(bot: Bot):
```

**Logic:**
1. Log startup: `logger.info(f"📸 Channel Photo Refresher started (interval: {CHANNEL_PHOTO_REFRESH_INTERVAL}s)")`
2. Enter an infinite loop (`while True`):
   a. Call `GET {API_BASE}/channels/` to fetch all channels from the backend.
      - Use `httpx.AsyncClient(timeout=30.0)`.
      - If the request fails, log an error and sleep for the interval before retrying.
      - Parse the JSON response into a list of channel dicts.
   b. Log the count: `logger.info(f"📸 Refreshing photos for {len(channels)} channels")`
   c. Iterate over each channel:
      - Extract `channel_id`, `username`, and current `photo_file_id` from the channel dict.
      - If `username` is missing or empty, skip this channel (cannot resolve Telegram chat without username).
      - Construct the chat identifier: `f"@{username}"`
      - Call `bot.get_chat(chat_id)`:
        - Wrap in try/except for `TelegramError` — log a warning and skip to the next channel on failure (e.g., channel banned, deleted, or bot kicked out).
      - If `chat.photo` exists:
        - Extract `new_photo_id = chat.photo.big_file_id`
        - Compare with `current_photo_file_id` (from the backend response).
        - If different (or `current_photo_file_id` is None):
          - Call `PATCH {API_BASE}/channels/{channel_id}` with `{"photo_file_id": new_photo_id}`.
          - Log: `logger.info(f"📸 Updated photo for @{username}")`
      - If `chat.photo` does not exist:
        - If `current_photo_file_id` is not None, the channel removed their photo — set `photo_file_id` to null. Call `PATCH {API_BASE}/channels/{channel_id}` with `{"photo_file_id": None}`.
        - Log: `logger.info(f"📸 Channel @{username} no longer has a photo")`
      - Add a small delay between channels (e.g., `await asyncio.sleep(0.5)`) to avoid hitting Telegram rate limits if there are many channels. Calculate dynamically: if channels > 500, use shorter sleep; if < 100, sleep 1s.
   d. After all channels are processed, log completion and sleep for `CHANNEL_PHOTO_REFRESH_INTERVAL` seconds.
   e. Wrap the entire loop body in try/except to catch unexpected errors — log the error and continue the loop.

**Rate limit considerations:**
- `getChat` is not heavily rate-limited by Telegram (unlike `sendMessage`). A 0.5-1 second delay between calls should be safe for up to several hundred channels.
- If the bot is in very many channels (1000+), consider batching or using `asyncio.gather` with a semaphore.

#### Step 16: Register the refresher in `listener/main.py`

In `post_init` (line 50), add a third background task:

```python
# C. Channel Photo Refresher
asyncio.create_task(channel_photo_refresher(app.bot))
logger.info("✅ Channel Photo Refresher Injected")
```

Add this after the existing notification poller task (line 56).

Also add the import at the top of the file (see Import Map section 5).

---

### PHASE 7: Frontend Changes

#### Step 17: Display channel photo on ProductPage (`frontend/src/pages/ProductPage.jsx`)

**Location:** The channel trust card section (line 171 onwards). Currently, the channel avatar is a letter-avatar div (lines 173-175):

```jsx
<div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-bold text-xl">
    {item.channel?.username?.[0]?.toUpperCase() || "S"}
</div>
```

**Replace with:**
- An `<img>` tag that loads the channel photo from the new endpoint.
- Use `onError` to fall back to the letter-avatar when the image fails to load (channel has no photo, network error, etc.).

**Implementation approach:**
- Create two elements: the `<img>` (hidden on error) and the letter-avatar div (hidden when image loads successfully).
- Use React state to track whether the image loaded successfully:
  ```jsx
  const [channelPhotoLoaded, setChannelPhotoLoaded] = useState(true);
  ```
- The `<img>` element:
  - `src="{API_BASE_URL}/channels/{item.channel?.id}/photo"`
  - `onLoad={() => setChannelPhotoLoaded(true)}`
  - `onError={() => setChannelPhotoLoaded(false)}`
  - `className="w-12 h-12 rounded-full object-cover"`
  - `alt={item.channel?.username || "Channel"}`
  - Use conditional rendering: show `<img>` only when `channelPhotoLoaded` is true and `item.channel?.id` exists.
- The letter-avatar div: show only when `channelPhotoLoaded` is false or channel has no id.
- Both should have the same dimensions (`w-12 h-12`) and styling (`rounded-full`) to ensure consistent layout.

#### Step 18: Display user photo on review cards (`frontend/src/pages/ProductPage.jsx`)

**Location:** The review list section (lines 207-222). Currently, each review card shows a generic `<User>` icon (line 211):

```jsx
<User size={12} className="text-gray-400"/>
```

**Replace with:**
- If `rev.user_photo_url` exists, show an `<img>` with that URL.
- If not, show the existing `<User>` icon as fallback.

**Implementation approach:**
- Inside the review card div (line 208), replace the `<User>` icon with a conditional:
  ```jsx
  {rev.user_photo_url ? (
      <img
          src={rev.user_photo_url}
          alt="Reviewer"
          className="w-5 h-5 rounded-full object-cover"
          onError={(e) => {
              e.target.style.display = 'none';
              e.target.nextSibling.style.display = 'inline';
          }}
      />
  ) : null}
  <User size={12} className={`text-gray-400 ${rev.user_photo_url ? 'hidden' : ''}`} />
  ```
- The `onError` handler hides the broken image and reveals the fallback `<User>` icon. This handles cases where the Telegram CDN URL is expired or invalid.
- Both elements should be wrapped inside the same flex container that currently holds the `<User>` icon.

**Note on `ReviewModal.jsx`:** The tech backlog's affected-files list includes `ReviewModal.jsx`, but review photos are displayed in the review list rendered inside `ProductPage.jsx`. The `ReviewModal` component is only for submitting reviews and does not display review data. No changes to `ReviewModal.jsx` are required for this feature. If future changes add a "posting as" user preview to the submission modal, that can be done in a separate ticket.

---

### PHASE 8: Database Migration

#### Step 19: Run database migration

The `Base.metadata.create_all(bind=engine)` call in `backend/main.py` (line 60) runs with `CREATE TABLE IF NOT EXISTS` semantics via SQLAlchemy. However, this does NOT add columns to existing tables.

The `@build` agent must either:
- **Option A (recommended):** Manually execute `ALTER TABLE` statements in PostgreSQL:
  ```sql
  ALTER TABLE channels ADD COLUMN IF NOT EXISTS photo_file_id VARCHAR;
  ALTER TABLE reviews ADD COLUMN IF NOT EXISTS user_photo_url TEXT;
  ```
- **Option B:** Use Alembic for migration management (add Alembic to the project, generate and run a migration).

Since the project does not currently use Alembic, Option A is simpler and consistent with how the project currently handles schema changes. The `IF NOT EXISTS` clause ensures the migration is idempotent and safe to run multiple times.

The `@build` agent should run these SQL statements against the database container (hostname `db` or `shield-db`, port 5432) and verify the columns exist before proceeding.

---

## Testing Requirements

The `@build` agent must implement and verify the following test cases:

### Channel Photo Tests

1. **Photo fetched on first ingestion:**
   - Ingest a post from a channel that has never been seen before.
   - Verify that the `Channel` record's `photo_file_id` is populated after ingestion.
   - Verify the log line: `📸 Fetched photo for channel @<username>`.

2. **Photo not re-fetched on subsequent ingestion:**
   - Ingest a second post from the same channel.
   - Verify that the `getChat` API is NOT called (because `photo_file_id` is already set).
   - Verify no duplicate log lines for photo fetch.

3. **Channel with no photo does not block ingestion:**
   - Test with a channel that has no profile photo in Telegram.
   - Verify that the item is still created successfully.
   - Verify the log line: `ℹ️ Channel @<username> has no photo`.
   - Verify `photo_file_id` remains `None` on the channel record.

4. **Network failure during photo fetch does not block ingestion:**
   - Simulate a network error during the `getChat` call (or use a mock).
   - Verify the item is still created successfully.
   - Verify a WARNING log is emitted.
   - Verify `photo_file_id` remains `None`.

### Photo Serving Endpoint Tests

5. **Photo endpoint returns redirect for channel with photo:**
   - Call `GET /channels/{channel_id}/photo` for a channel with a valid `photo_file_id`.
   - Verify response status is 307 (Temporary Redirect).
   - Verify the `Location` header points to `https://api.telegram.org/file/bot<TOKEN>/...`.

6. **Photo endpoint returns 404 for channel with no photo:**
   - Call `GET /channels/{channel_id}/photo` for a channel with `photo_file_id = None`.
   - Verify response status is 404.
   - Verify response detail: `"No photo available for this channel"`.

7. **Photo endpoint returns 404 for non-existent channel:**
   - Call `GET /channels/{channel_id}/photo` with a channel ID that does not exist.
   - Verify response status is 404.

8. **Photo endpoint includes Cache-Control header:**
   - Verify the 307 response includes `Cache-Control: public, max-age=3600`.

### Daily Refresh Tests

9. **Daily refresher updates photo when it changes:**
   - Set a channel's `photo_file_id` to a known old value.
   - Run the refresher.
   - Verify `PATCH /channels/{channel_id}` is called with the new `photo_file_id`.
   - Verify the log line: `📸 Updated photo for @<username>`.

10. **Daily refresher skips channels with unchanged photos:**
    - Set a channel's `photo_file_id` to the correct current value.
    - Run the refresher.
    - Verify `PATCH` is NOT called for this channel (no unnecessary DB writes).

11. **Daily refresher nullifies photo when channel removes it:**
    - Set a channel's `photo_file_id` to a value, but the channel no longer has a photo.
    - Run the refresher.
    - Verify `PATCH /channels/{channel_id}` is called with `{"photo_file_id": null}`.

12. **Daily refresher handles API failure gracefully:**
    - Simulate the backend `/channels/` endpoint returning an error (e.g., 500).
    - Verify the refresher logs an error and sleeps for the interval before retrying.
    - Verify the refresher does not crash.

13. **Daily refresher handles Telegram errors per-channel:**
    - Simulate `getChat` raising a `TelegramError` for a specific channel (e.g., bot kicked out).
    - Verify that channel is skipped (logged as warning).
    - Verify the refresher continues to the next channel.

### User Photo Tests

14. **User photo captured during review submission:**
    - Submit a review with initData that includes `user.photo_url`.
    - Verify the `Review` record has `user_photo_url` set to the provided URL.
    - Verify the `ReviewResponse` JSON includes `user_photo_url`.

15. **Review without user photo works normally:**
    - Submit a review with initData that does NOT include `user.photo_url` (user has no public photo).
    - Verify the `Review` record has `user_photo_url = None`.
    - Verify the `ReviewResponse` JSON includes `user_photo_url: null`.

16. **Review list endpoint returns user_photo_url:**
    - Call `GET /reviews/{channel_id}`.
    - Verify each review in the response includes `user_photo_url` (either a URL string or null).

### Frontend Tests

17. **Channel photo displays on product page:**
    - Navigate to a product page for a channel with a photo.
    - Verify the channel avatar area shows an `<img>` element (not the letter-avatar div).
    - Verify the `src` attribute is `{API_BASE_URL}/channels/{channel_id}/photo`.

18. **Letter-avatar fallback when channel has no photo:**
    - Navigate to a product page for a channel without a photo.
    - Verify the letter-avatar div is displayed.
    - Verify the `<img>` element is hidden or absent.

19. **Letter-avatar fallback when image fails to load:**
    - Navigate to a product page where the photo endpoint returns an error or 404.
    - Verify the `onError` handler triggers and the letter-avatar fallback is shown.
    - Verify no broken image icon is visible.

20. **User photo displays on review cards:**
    - Navigate to a product page with reviews that include `user_photo_url`.
    - Verify the review card shows the user's photo as an `<img>`.
    - Verify the `<User>` icon is hidden.

21. **User icon fallback when review has no photo:**
    - Navigate to a product page with reviews that do NOT include `user_photo_url`.
    - Verify the `<User>` icon is displayed.
    - Verify no broken image is shown.

22. **Photo endpoint does not slow page rendering:**
    - Navigate to a product page with channel photo.
    - Verify that the page content (title, price, description) renders before the channel photo appears (non-blocking image load).
    - Verify the redirect response time is reasonable (< 500ms in normal conditions).

---

## Rollback and Safety Notes

- **All changes are additive.** No existing data is modified or deleted. Rolling back is a matter of ignoring the new columns and removing the new routes/tasks.
- **The `photo_file_id` column is nullable.** Existing channels without photos will have `None` and the current letter-avatar fallback will continue to display.
- **The `user_photo_url` column is nullable.** Existing reviews will have `None` and the current `<User>` icon will continue to display.
- **The photo fetch in ingestion is wrapped in try/except.** A failure in the Telegram API call will never block item creation.
- **The daily refresher runs as a non-critical background task.** If it crashes, the main listener (ingestion + notifications) continues to function.
- **The photo endpoint includes a `Cache-Control` header.** Even if the endpoint is slow on first hit, subsequent hits within an hour are served from the browser cache.
- **If the photo redirect endpoint needs to be disabled**, simply remove the router registration line in `main.py`. The frontend `onError` handlers will fall back to the letter-avatar gracefully.

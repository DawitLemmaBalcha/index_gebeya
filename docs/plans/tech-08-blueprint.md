# TECH-08 Implementation Blueprint — Channel/Group Bot Onboarding

**Goal:** Implement a complete bot onboarding flow for channel/group owners via `/addchannel` command and `my_chat_member` status change handler, with ownership tracking in the Channel model.

---

## Files to Modify

| File | Action | Summary |
|------|--------|---------|
| `backend/models.py` | Modify | Add `registered_by` column to `Channel` |
| `backend/schemas.py` | Modify | Add `ChannelUpsert` request schema |
| `backend/api/routes/channels.py` | Modify | Add `POST /` upsert endpoint (internal) |
| `listener/client.py` | Modify | Add `upsert_channel_api()` helper |
| `listener/bot_commands.py` | Modify | Add `handle_addchannel` function |
| `listener/chat_member_handler.py` | **Create** | New file: `handle_chat_member` function |
| `listener/main.py` | Modify | Register both new handlers |

---

## Strict Import Map

### 1. `backend/models.py` — new column

- **Column to add (line ~122, inside `Channel` class, before `created_at`):**
  ```python
  registered_by = Column(BigInteger, nullable=True)
  ```
- `BigInteger` is already imported at line 1 of `models.py`. No new import needed.

### 2. `backend/schemas.py` — new schema

- **New class `ChannelUpsert`** appended after `ChannelResponse` (around line 21):
  - Fields: `username: str`, `title: Optional[str] = None`, `registered_by: Optional[int] = None`, `telegram_id: Optional[int] = None`
  - Inherits from `BaseModel` (already imported)
  - Uses `Optional` from `typing` (already imported at line 1)

### 3. `backend/api/routes/channels.py` — new endpoint

- **New import** (lines 12-13, alongside existing model imports):
  ```python
  from schemas import ChannelResponse, ChannelUpsert
  ```
  (replace existing line 13 `from schemas import ChannelResponse` with `ChannelResponse, ChannelUpsert`)
- **New route function `upsert_channel`** appended before the final `@router.get("/{channel_id}/photo")` block.
- Uses existing imports: `Session`, `Channel`, `get_db`, `HTTPException` — all already available.

### 4. `listener/client.py` — new function

- **New function `upsert_channel_api`** appended after `ack_notification` (after line 103):
- Relies on existing imports: `httpx`, `API_BASE`, `logger`, `INTERNAL_HEADERS` — all already available.

### 5. `listener/bot_commands.py` — new command handler

- **New function `handle_addchannel`** appended after `handle_alert_callback` (after line 59):
- Relies on existing imports: `Update`, `ContextTypes` — already available.
- No new imports required.

### 6. `listener/chat_member_handler.py` — new file

- **Top-level imports:**
  ```python
  from telegram import ChatMemberUpdated, Update
  from telegram.ext import ContextTypes
  from config import logger
  from client import upsert_channel_api
  ```
- **Single exported function:** `handle_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None`

### 7. `listener/main.py` — register handlers

- **New import** (after existing handler imports, around line 9-11):
  ```python
  from bot_commands import handle_my_alerts, handle_alert_callback, handle_addchannel
  ```
  (replace line 11 with the expanded import)
- **New import** (after existing bot_commands import):
  ```python
  from chat_member_handler import handle_chat_member
  ```
- **New import** for `ChatMemberHandler` (add to line 4 existing `telegram.ext` import):
  ```python
  from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ChatMemberHandler, filters
  ```
- **Registration** of `/addchannel` command (after existing CommandHandler for `myalerts` at line 38):
  ```python
  application.add_handler(CommandHandler('addchannel', handle_addchannel))
  ```
- **Registration** of `my_chat_member` handler (after new addchannel line):
  ```python
  application.add_handler(ChatMemberHandler(handle_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
  ```

---

## Step-by-Step Execution

### Phase 1 — Database & Model

1. **Run ALTER TABLE** on the production database:
   - Connect to the PostgreSQL database using env vars (`DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` from `.env`).
   - Execute: `ALTER TABLE channels ADD COLUMN registered_by BIGINT;`
   - Verify: `\d channels` should show the new column as nullable with no default.

2. **Add `registered_by` column to `Channel` model** in `backend/models.py`:
   - Inside the `Channel` class, insert the line `registered_by = Column(BigInteger, nullable=True)` between `photo_file_id` (line 120) and `created_at` (line 122).

### Phase 2 — Backend API Endpoint

3. **Add `ChannelUpsert` schema** in `backend/schemas.py`:
   - Create a new Pydantic `BaseModel` class named `ChannelUpsert` with four fields:
     - `username: str` (required)
     - `title: Optional[str] = None`
     - `registered_by: Optional[int] = None`
     - `telegram_id: Optional[int] = None`
   - Place it between `ChannelResponse` and `ReviewCreate` classes.

4. **Add `POST /` upsert endpoint** in `backend/api/routes/channels.py`:
   - Replace the existing `from schemas import ChannelResponse` with `from schemas import ChannelResponse, ChannelUpsert`.
   - Add a new `@router.post("/", response_model=ChannelResponse)` function named `upsert_channel` that:
     - Accepts a `ChannelUpsert` body and a DB session.
     - Queries for an existing channel by `username`.
     - If it exists: set `channel.registered_by = body.registered_by` if provided, set `channel.title = body.title` if provided, set `channel.telegram_id = body.telegram_id` if provided. Commit and return the updated channel.
     - If it does not exist: create a new `Channel(username=body.username, title=body.title or body.username, registered_by=body.registered_by, telegram_id=body.telegram_id)` with a default `trust_score` of 2.5. Add, commit, refresh, and return the new channel.

### Phase 3 — Listener Client Helper

5. **Add `upsert_channel_api` to `listener/client.py`**:
   - Define an async function `upsert_channel_api(username: str, title: str, registered_by: int, telegram_id: int) -> bool`.
   - The function posts a JSON payload with `username`, `title`, `registered_by`, `telegram_id` to `{API_BASE}/channels/` using `INTERNAL_HEADERS`.
   - Use `httpx.AsyncClient(timeout=10.0)`.
   - Log success/failure. Return `True` on 200, `False` otherwise.

### Phase 4 — `/addchannel` Command Handler

6. **Add `handle_addchannel` to `listener/bot_commands.py`**:
   - Define an async function `handle_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE)`.
   - Send a reply using `update.message.reply_text()` with the exact instruction text from the behavior spec (Rule 1.1 in `docs/behaviors/bot-onboarding.md`), replacing `@SuqListenerDevBot` with the actual bot username (a constant extracted from env or hardcoded). Use `parse_mode="Markdown"`.
   - The instruction text must include the four numbered steps exactly as specified.

### Phase 5 — `my_chat_member` Handler (New File)

7. **Create `listener/chat_member_handler.py`** with one async function `handle_chat_member`:

   - **Extract data from the update:**
     - `chat = update.my_chat_member.chat` — the chat object.
     - `new_status = update.my_chat_member.new_chat_member.status` — one of: `administrator`, `member`, `kicked`, `left`, `restricted`.
     - `old_status = update.my_chat_member.old_chat_member.status` — previous status.
     - `inviter = update.my_chat_member.from_user` — the user who performed the action.
     - If `inviter` is None (bot joined a public group by invite link with no originating user), log a warning and return early — cannot DM anyone.

   - **Guard clause — ignore private chats:**
     - If `chat.type == "private"`, log info and return immediately. The bot being added to a private user DM is not a channel/group onboarding event.

   - **Guard clause — ignore non-target statuses:**
     - If `new_status` is `restricted` or any unrecognized value, log and return.

   - **Extract chat identifiers:**
     - `chat_username = chat.username or chat.title or "unknown"` (used for display in DMs)
     - `inviter_id = inviter.id`

   - **State 1 — Added as Administrator WITH public username:**

     *Condition:* `new_status == "administrator"` AND `chat.username is not None`
     *Action:*
     - Call `await upsert_channel_api(username=chat.username, title=chat.title, registered_by=inviter_id, telegram_id=chat.id)`.
     - Send DM to `inviter_id` via `context.bot.send_message(chat_id=inviter_id, text=f"✅ @{chat.username} is now live on Index Gebeya. Your listings will appear in the marketplace within a minute or two of posting.")`.
     - Log the successful registration.

   - **State 2 — Added as Administrator WITHOUT public username (REJECTED):**

     *Condition:* `new_status == "administrator"` AND `chat.username is None`
     *Action:*
     - Do NOT call the API.
     - Send DM to `inviter_id`: "This channel/group is private. We can only index public channels and groups that have a @username. Please add me to a public channel/group instead."
     - Log the rejection.

   - **State 3 — Added as Regular Member (NOT admin):**

     *Condition:* `new_status == "member"` (status is member, not administrator)
     *Action:*
     - Do NOT call the API.
     - Send DM to `inviter_id`: "To verify you own this channel/group, add me as admin. No permissions needed — you can turn them all off. Just remove me and re-add me as admin."
     - Log the event.

   - **State 4 — Demoted (admin → member):**

     *Condition:* `new_status == "member"` AND `old_status == "administrator"`
     *Action:*
     - Send DM to `inviter_id`: "I've lost admin status on @YourChannel. I'll stop indexing your listings. Add me back as admin to resume." where `@YourChannel` is replaced with the actual `@chat.username` if available, or `chat.title` if not.
     - Log the demotion.

   - **State 5 — Removed (kicked or left):**

     *Condition:* `new_status in ("kicked", "left")`
     *Action:*
     - Send DM to `inviter_id`: "I've been removed from @YourChannel. Your listings are no longer being updated. Add me back anytime to resume." where `@YourChannel` is replaced with the actual `@chat.username` if available, or `chat.title` if not.
     - Log the removal.

   - **Rate-limiting / error handling:**
     - Wrap every `context.bot.send_message(...)` call in a `try/except` block.
     - Catch `telegram.error.TelegramError` and log a warning if the DM fails (e.g., user has blocked the bot).
     - Never let an unhandled exception in one state transition prevent other transitions from being processed.

   - **Logging at every state:**
     - Use `logger.info(...)` in every branch to log the state transition, chat identity, and inviter ID.

### Phase 6 — Register Handlers in main.py

8. **Update `listener/main.py`:**
   - Expand the `from telegram.ext import ...` line to include `ChatMemberHandler`.
   - Expand the `from bot_commands import ...` line to include `handle_addchannel`.
   - Add a new import line: `from chat_member_handler import handle_chat_member`.
   - After the existing `application.add_handler(CommandHandler('myalerts', handle_my_alerts))` line (line 38), add:
     ```python
     application.add_handler(CommandHandler('addchannel', handle_addchannel))
     ```
   - After the new addchannel line, add:
     ```python
     application.add_handler(ChatMemberHandler(handle_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
     ```

---

## Testing Requirements

The `@build` agent must implement the following test verifications:

### Manual Verification Checklist

1. **`/addchannel` command test:**
   - Send `/addchannel` to the bot via a private DM.
   - Confirm the bot replies with the four-step instruction text including the mention of the correct bot username.

2. **Admin + public username test:**
   - Add the bot as admin to a public channel with a `@username`.
   - Confirm the bot sends a confirmation DM to the inviter: "✅ @YourChannel is now live on Index Gebeya..."
   - Confirm the `channels` table has a row for that username with `registered_by` set to the inviter's Telegram ID.

3. **Admin + private channel test:**
   - Add the bot as admin to a private channel (no public `@username`).
   - Confirm the bot sends a rejection DM: "This channel/group is private..."
   - Confirm no new channel row is created in the `channels` table for that entity.

4. **Regular member test:**
   - Add the bot as a regular member (not admin) to a public channel.
   - Confirm the bot sends: "To verify you own this channel/group, add me as admin..."
   - Confirm no channel registration occurs.

5. **Demotion test:**
   - After step 2 (bot is admin in a public channel), demote the bot to regular member.
   - Confirm the bot sends: "I've lost admin status on @YourChannel..."

6. **Removal test:**
   - After step 2, remove the bot entirely from the channel.
   - Confirm the bot sends: "I've been removed from @YourChannel..."

7. **Re-add test (fresh confirmation, no stale state):**
   - After step 6, re-add the bot as admin to the same channel.
   - Confirm the bot sends a fresh confirmation DM.
   - Confirm the `channels` row still exists with `registered_by` set correctly (not duplicated).

8. **Rate-limiting / error resilience test:**
   - Block the bot from sending you DMs, then add it as admin to a channel.
   - Confirm the handler logs a warning but does not crash the entire listener application.

### Automated Test (if feasible)

9. Write a unit test in `listener/tests/` (create directory if needed) for the `handle_chat_member` function that:
   - Mocks `Update` and `ContextTypes.DEFAULT_TYPE` with `my_chat_member` sub-objects.
   - Asserts each of the 5 state transitions produces the correct DM text and the correct API calls (or lack thereof).
   - Asserts that private chat events are silently ignored.
   - Asserts that missing inviter (in public link join) is handled gracefully.

---

## Edge Cases & Notes

- **DM not deliverable:** If the inviter has the bot blocked or hasn't started a conversation, `send_message` will raise a `Forbidden` error. The handler must catch this and log a warning — never crash.
- **Inviter is None:** When the bot joins via a public invite link, `from_user` on the `ChatMemberUpdated` object may be `None`. Log and return early — no DM can be sent.
- **Channel already registered:** The `upsert_channel_api` endpoint must handle the case where a channel already exists (e.g., was created by ingestion). It should update `registered_by` and `title` without creating a duplicate.
- **Bot username in `/addchannel` text:** The instruction text must reference the actual bot username. Consider reading `bot.username` from `context.bot.username` at runtime, or define a constant in `config.py`.
- **No `telegram.error` import breakage:** Ensure `from telegram import error as telegram_error` or use `import telegram` and catch `telegram.error.TelegramError` in the `chat_member_handler.py` try/except blocks.

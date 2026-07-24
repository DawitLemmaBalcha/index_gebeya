# Technical Backlog

> Generated from `docs/behaviors/pending-behaviors.md` gap tickets.
> Each TECH ticket maps to one or more NB behavioral tickets.

---

## TECH-08 — Channel/Group Bot Onboarding

**Parent:** NB-27
**Priority:** HIGH
**Affected Files:**
- `listener/bot_commands.py` — add `/addchannel` command handler
- `listener/main.py` — register `my_chat_member` handler
- `backend/models.py` — add `registered_by` column to Channel

**Description:**
Implement a complete bot onboarding flow for channel/group owners. The bot listens for status change events (`my_chat_member`), verifies admin status as proof of ownership, and sends appropriate DMs at every state transition. A `/addchannel` command provides onboarding instructions.

**Technical Work:**

1. **Model change:** Add `registered_by = Column(BigInteger, nullable=True)` to the `Channel` model. Run `ALTER TABLE channels ADD COLUMN registered_by BIGINT;` on the existing database.

2. **`/addchannel` command handler:** Register a `CommandHandler("addchannel", handle_addchannel)` that replies with the formatted instruction text.

3. **`my_chat_member` handler:** Register a handler for `ChatMemberHandler(handle_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)`. The handler must:

   - Extract `chat.type`, `chat.username`, `new_chat_member.status`, and the inviter's Telegram ID from the update.
   - **Admin + public username:** Update or create the Channel record with `username`, `registered_by = inviter_id`. Send DM: "✅ @YourChannel is now live on Index Gebeya..."
   - **Admin + no username (private):** Send DM: "This channel/group is private..."
   - **Member (not admin):** Send DM: "To verify you own this channel/group, add me as admin..."
   - **Demoted (admin→member):** If channel was previously registered, send DM: "I've lost admin status on @YourChannel..."
   - **Removed (kicked/left):** If channel was previously registered, send DM: "I've been removed from @YourChannel..."

4. **Edge cases:** The handler must handle groups without username, the bot being added to private chats (ignore), and rate limiting from Telegram's API.

**Acceptance Criteria:**
- [ ] `/addchannel` returns the full onboarding instruction text
- [ ] Adding bot as admin to public channel triggers confirmation DM
- [ ] Adding bot to private channel/group triggers rejection DM
- [ ] Adding bot as regular member triggers "please add as admin" DM
- [ ] Demoting bot from admin triggers warning DM
- [ ] Removing bot triggers removal DM
- [ ] Re-adding bot after removal triggers a fresh confirmation DM (no stale state)
- [ ] `registered_by` is populated on Channel record for onboarded channels

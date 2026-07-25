# Channel & Group Bot Onboarding

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

Channel and group owners can connect their Telegram presence to Index Gebeya by adding the bot as an admin. The bot uses admin status as proof of ownership — no actual permissions are needed or used. Once connected, all posts from that channel/group are ingested into the marketplace automatically.

---

## Behavioral Rules

### 1. Discovery — `/addchannel` Command

**Rule 1.1 — Instruction Delivery**
When any user sends `/addchannel` to the bot, the bot responds with step-by-step onboarding instructions:

> "To list your products on Index Gebeya, add me to your channel or group as an **admin**:
> 
> 1. Open your channel or group → **Info** → **Administrators**
> 2. Tap **Add Admin** and search for `@IndexGebeyaBot`
> 3. ⚠️ **Turn OFF all permissions.** I don't need to delete messages, ban users, or post. Admin is only needed so I can verify you own this channel/group.
> 4. Confirm.
> 
> Once added, post a product — it'll appear in the marketplace within a minute or two."

**Rule 1.2 — Bot Not Added Yet**
If the user types `/addchannel` without having added the bot to any channel/group, they only receive the instructions. No automatic action is taken. The bot does not scan their account for channels.

### 2. Auto-Detection — Status Change Events

The bot listens for Telegram's `my_chat_member` update, which fires whenever the bot's status changes in any chat. The handler processes each transition:

#### 2.1 Added as Admin — With Username (Successful Onboarding)

**Condition:** New status is `administrator`, and the chat has a public `username`.

**Action:**
- The channel/group is registered in the database with `registered_by` set to the Telegram ID of the user who added the bot.
- The bot sends a DM to the inviter:

> "✅ @YourChannel is now live on Index Gebeya. Your listings will appear in the marketplace within a minute or two of posting."

#### 2.2 Added as Admin — Private Channel/Group (Rejected)

**Condition:** New status is `administrator`, but the chat has **no** public username (private channel or group).

**Action:**
- The channel/group is NOT registered.
- The bot sends a DM to the inviter:

> "This channel/group is private. We can only index public channels and groups that have a @username. Please add me to a public channel/group instead."

#### 2.3 Added as Regular Member (Not Admin)

**Condition:** New status is `member` (not administrator). The user added the bot but did not grant admin.

**Action:**
- The channel/group is NOT registered.
- The bot sends a DM to the inviter:

> "To verify you own this channel/group, add me as admin. No permissions needed — you can turn them all off. Just remove me and re-add me as admin."

**Rationale:** The bot requires admin status purely as proof of channel ownership. It will never use any admin privileges.

#### 2.4 Demoted — Admin to Member

**Condition:** Bot's status changes from `administrator` to `member` within an already-registered channel/group.

**Action:**
- The channel/group's registration status is preserved but ingestion is paused.
- The bot sends a DM to the original inviter:

> "I've lost admin status on @YourChannel. I'll stop indexing your listings. Add me back as admin to resume."

#### 2.5 Removed — Kicked or Left

**Condition:** Bot is removed from the channel/group entirely (`kicked` or `left`).

**Action:**
- Ingestion for this channel/group stops.
- The bot sends a DM to the original inviter:

> "I've been removed from @YourChannel. Your listings are no longer being updated. Add me back anytime to resume."

**Consequence:** Previously ingested items remain in the catalog — they are not deleted. Only future posts from this channel/group are no longer captured.

### 3. State Transitions Are Idempotent

**Rule 3.1 — No Stale State**
Every status transition delivers exactly one DM to the inviter. If the inviter removes and re-adds the bot ten times, they receive ten distinct messages — one per transition. The system never requires the user to "fix" a stuck state or send a manual command.

**Rule 3.2 — Re-adding Works Immediately**
If a channel/group was previously registered, removed, and then re-added, ingestion resumes immediately upon the new admin-granted event. No delay, no manual resync.

### 4. Channel/Group Model Extension

**Rule 4.1 — Ownership Tracking**
A `registered_by` field (nullable, Telegram user ID) is added to the channel/group record. Channels/groups that were auto-discovered during ingestion (never onboarded) have `registered_by = NULL`. Onboarded channels/groups have the inviter's Telegram ID.

**Rule 4.2 — Ingestion Eligibility**
All channels/groups with a public username are eligible for ingestion regardless of `registered_by` status. The `registered_by` field is informational for ownership and DM routing — it does not gate ingestion.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| User adds bot as admin to a private channel/group | Rejected with a DM explaining the requirement |
| User adds bot as member (not admin) to a public channel | Rejected with a DM asking them to re-add as admin |
| Bot loses admin status | Ingestion pauses, DM sent to original inviter |
| Bot is removed entirely | Ingestion stops, DM sent to original inviter |
| Bot is re-added after removal | Ingestion resumes immediately |
| Telegram API is temporarily unavailable during status change | The DM is not sent. Ingestion continues based on last known state |
| User with no Telegram account triggers the flow | Cannot happen — Telegram requires an account to add a bot |

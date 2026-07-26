# Processing Notifications & Store Management

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

Channel owners who onboard via `/addchannel` receive Telegram DMs when their posts are being processed and indexed. They can pause/resume indexing from the Stores tab, and remove the bot from their channel entirely — with the bot auto-leaving.

---

## Behavioral Rules

### 1. Processing Notification DM

**Rule 1.1 — One Message, Edited**
When a post is captured from a channel that has `registered_by` set, the bot sends exactly one DM to the owner:
- **Initial:** "⏳ Processing your post from @YourChannel..."
- **On completion:** The same message is edited to "✅ Indexed: [Product Title] — [Price] ETB"

The owner sees one message that transforms from "processing" to "done." No second message, no notification spam.

**Rule 1.2 — Only for Registered Owners**
If the channel was auto-discovered (no `registered_by`), no processing DM is sent. The channel owner hasn't opted into notifications.

**Rule 1.3 — Failure Handling**
If AI extraction fails, the DM is edited to: "❌ Could not process your post from @YourChannel. The post may not contain a product or an image."

**Rule 1.4 — Price Display**
If the item has no price, the confirmation shows "Ask for Price" instead of a number.

### 2. Pause/Resume Indexing

**Rule 2.1 — Pause Confirmation**
When the owner taps "Pause" on a channel in the Stores tab, a confirmation modal appears: "Pause indexing for @YourChannel? Your products stay in the catalog but new posts won't appear. You can resume anytime."

**Rule 2.2 — Pause Effect**
On confirmation, an `indexing_paused` flag is set on the channel. The ingestion pipeline skips all posts from paused channels. Existing products remain indexed and searchable.

**Rule 2.3 — Pause DM**
The bot DMs the owner: "⏸️ @YourChannel is paused. Your products remain indexed but new posts won't appear. Tap Resume in Stores anytime."

**Rule 2.4 — Resume**
Tapping "Resume" clears the flag. The bot DMs: "▶️ @YourChannel is active again. New posts will appear in the marketplace."

**Rule 2.5 — No Double Confirmation for Resume**
Resume does not require confirmation — it's a safe, reversible action.

### 3. Remove / Auto-Leave

**Rule 3.1 — Remove Confirmation**
When the owner taps "Remove" on a channel, a confirmation modal appears: "Remove @YourChannel from Index Gebeya? The bot will leave your channel. Existing products stay in the catalog but new posts won't be indexed. You can add the bot back anytime."

**Rule 3.2 — Remove Action**
On confirmation:
1. The bot calls `getChat` to get the channel's numeric ID
2. The bot calls `leaveChat` to remove itself from the channel
3. The channel's record is marked as removed in the database
4. The bot DMs the owner: "👋 I've left @YourChannel. Your existing products stay indexed. Add me back anytime to resume."

**Rule 3.3 — Leave Failure Handling**
If `leaveChat` fails (e.g., the bot was already removed), the channel is still marked as removed in the database. The DM is sent regardless — the owner gets confirmation that we've stopped indexing.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Channel has no `registered_by` | No processing DMs are sent for that channel |
| AI extraction fails during processing | DM edited to failure message |
| `leaveChat` fails | Channel still marked as removed. DM sent confirming removal. |
| Owner taps Remove on a channel without admin status | Remove proceeds — `getChat` works for any channel the bot is in |
| Bot is already removed from channel (manual) | `leaveChat` fails silently. Channel marked as removed in DB. |

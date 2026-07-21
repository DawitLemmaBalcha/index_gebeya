# Notification Delivery

> **Status:** ⚠️ NOT YET FULLY IMPLEMENTED (see pending-behaviors.md for gaps)

---

## Overview

When the Alert Matching Engine confirms a match, a notification is created in the "mailbox." The Notification Poller delivers these to buyers via Telegram Direct Messages.

---

## Behavioral Rules

### 1. Notification Lifecycle

**Rule 1.1 — States**
A notification exists in one of three states:
- **PENDING:** Created but not yet delivered. Waiting to be picked up by the poller.
- **SENT:** Successfully delivered to the buyer's Telegram DM.
- **FAILED:** Delivery was attempted but failed (not currently tracked — see gaps).

**Rule 1.2 — Immutable After Sent**
Once a notification is marked SENT, its status cannot change. It will never be re-delivered.

### 2. The Poller (Mailman)

**Rule 2.1 — Polling Interval**
The Notification Poller checks for pending notifications every 5 seconds. Between checks, it is idle.

**Rule 2.2 — Batch Size**
Each polling cycle fetches up to 50 pending notifications at a time. If more than 50 are pending, the remainder wait for the next cycle.

**Rule 2.3 — Sequential Delivery Within a Batch**
Notifications within a single batch are delivered one at a time, in the order they were created.

### 3. Delivery Format

**Rule 3.1 — Tier Emoji**
- Bullseye matches display with a 🎯 emoji.
- Ring matches display with a ⭕ emoji.

**Rule 3.2 — Price Display**
- If the product has a listed price, it is shown formatted with comma separators (e.g., "50,000 ETB").
- If the product has no listed price, it displays "Call for Price."

**Rule 3.3 — Deep Link**
Each notification includes a "View Item" link that opens the product detail page inside the Mini App.

**Rule 3.4 — Stop Alert Button**
Every notification includes a "Found it / Stop Alert" button. When the buyer taps this button, the alert associated with that notification is immediately deactivated.

**Consequence:** The buyer does not need to type a command or navigate to a menu. One tap stops all future notifications for that alert.

### 4. Acknowledgment

**Rule 4.1 — Deliver-Then-Acknowledge**
The poller first attempts to send the Telegram message, then acknowledges it to the backend only if the send was successful.

**Rule 4.2 — Retry on Failed Delivery**
If delivery fails (e.g., the buyer has blocked the bot, or Telegram is temporarily unavailable), the notification remains PENDING and will be retried on the next polling cycle. There is no retry limit for notification delivery (contrast with ingestion retries).

**Rule 4.3 — Acknowledgment Records Timestamp**
When a notification is acknowledged, the exact time of delivery is recorded.

### 5. Buyer Actions on Notification

**Rule 5.1 — Stop Alert via Button**
When a buyer taps "Found it / Stop Alert" on a notification:
- The button is removed from the message (replaced with plain text).
- A confirmation message is displayed: "Alert stopped. You won't receive more notifications for this."
- The alert is permanently deactivated.

**Rule 5.2 — Stop Alert via /myalerts**
Buyers can also view and deactivate their alerts at any time using the /myalerts bot command, which lists all active alerts with individual deactivation buttons.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Buyer has blocked the bot | Delivery fails silently. Notification remains PENDING for retry. |
| Buyer's Telegram ID is invalid | Delivery fails. Notification remains PENDING. |
| Backend is unreachable during polling | The poller logs a warning and waits for the next cycle. No notifications are lost. |
| Notification references a deleted alert | The "Stop Alert" button may not appear (if alert_id is missing). Notification is still delivered. |

# Crowdsourced Sold Reports & Product Status

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

Any buyer can report a product as sold. When enough independent buyers report it, the product is automatically hidden from search. The channel owner receives transparent DMs about each status change. All thresholds are configurable in `constants.py`.

---

## Behavioral Rules

### 1. Item Status Lifecycle

**Rule 1.1 — Statuses**
Every item has a `status` column. Valid states: `active`, `sold`, `reported_sold`, `soft_deleted`, `removed`. Default is `active`.

**Rule 1.2 — Active items**
Visible in search, feed, alerts. Default state.

**Rule 1.3 — Sold items**
Owner-marked. Excluded from search and feed. Still visible on product page with "Sold" badge. Reversible by owner.

**Rule 1.4 — Reported Sold items**
Crowdsourced. Excluded from search and feed. Visible on product page with "⚠️ Reported Sold" badge and report count. Reversible by owner (clears all reports).

**Rule 1.5 — Soft-deleted items**
Dedup replacements. Excluded from everything. Auto-deleted after `SOFT_DELETED_RETENTION_DAYS`.

**Rule 1.6 — Removed items**
Owner removed via Stores tab. Excluded from everything. Preserved for history.

### 2. Reporting a Product as Sold

**Rule 2.1 — Any Buyer Can Report**
Any authenticated buyer can tap "Report as Sold" on any product page. The button is always visible — not gated by ownership.

**Rule 2.2 — One Report Per User Per Item**
A buyer cannot report the same item twice. Attempting to report again shows: "You already reported this as sold."

**Rule 2.3 — Report Creates SoldReport Record**
Each report creates a `SoldReport(user_id, item_id, created_at)` record. Reports are immutable — no undo, no delete. Only the owner can clear all reports via "Re-list."

**Rule 2.4 — Threshold Trigger**
When `SoldReport` count reaches `CROWDSOURCE_SOLD_THRESHOLD` (default: 3), the item status changes to `reported_sold`. A badge appears on the product card: "⚠️ Reported Sold."

**Rule 2.5 — Owner Re-list**
The owner can tap "Re-list" on their product to clear all reports and reset status to `active`. All `SoldReport` records for that item are deleted.

**Rule 2.6 — Owner Cannot Report Own Items**
The report button is hidden for items where the buyer is also the channel owner (via `registered_by`).

### 3. Transparent Owner DMs

**Rule 3.1 — Notify on Threshold Reached**
When status changes to `reported_sold`, the bot DMs the channel owner:
> "⚠️ Your listing '[Product Title]' on @YourChannel has been reported as sold by 3 buyers. It has been hidden from search. If this is incorrect, re-list it from your Stores tab."

**Rule 3.2 — Notify on Auto-Delete**
When a `reported_sold` item is auto-deleted after `REPORTED_SOLD_RETENTION_DAYS`:
> "🗑️ Your listing '[Product Title]' was removed after being reported sold and unaddressed for [X] days."

**Rule 3.3 — Notify on Owner Mark as Sold**
When owner marks their own product as sold:
> "✅ You marked '[Product Title]' as sold. It is no longer visible in search."

**Rule 3.4 — Only for Registered Owners**
DMs only fire for channels with `registered_by` set. Anonymous/discovered channels get no DMs.

### 4. Cleanup

**Rule 4.1 — Soft-Deleted Cleanup**
A background task runs daily: deletes items where `status = soft_deleted` AND `created_at < now() - SOFT_DELETED_RETENTION_DAYS`. Notifies owner via DM.

**Rule 4.2 — Stale Item Flagging**
A background task runs daily: flags items where `status = active` AND zero interactions (no UserInteraction records referencing this item_id) AND `created_at < now() - STALE_ITEM_DAYS`. Flagged items are NOT automatically removed — they show a "May be outdated" label.

**Rule 4.3 — Reported Sold Cleanup**
A background task runs daily: deletes items where `status = reported_sold` AND `created_at < now() - REPORTED_SOLD_RETENTION_DAYS`. Notifies owner via DM.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Buyer reports own item | Button hidden — cannot report own products |
| Buyer reports same item twice | "You already reported this as sold." |
| Owner re-lists item with zero reports | No-op — item was never reported |
| Background cleanup encounters deleted channel | Item deleted without DM (no registered_by to notify) |

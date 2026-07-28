# Alert Guardrails

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

Alert limits prevent buyer fatigue, notification spam, and system abuse. All limits are configurable via a shared constants module with environment variable overrides. No hardcoded numbers.

---

## Behavioral Rules

### 1. Configuration

**Rule 1.1 — Single Source of Truth**
All alert limits are defined in `backend/constants.py` with defaults and environment variable overrides. No limit is hardcoded in business logic.

| Constant | Default | Env Override | What It Does |
|----------|---------|-------------|--------------|
| `MAX_ALERTS_PER_USER` | 20 | `ALERT_MAX_PER_USER` | Maximum active alerts a user can have |
| `MAX_MATCHES_BEFORE_PAUSE` | 10 | `ALERT_MAX_MATCHES` | Auto-pause alert after this many total matches |
| `MAX_BULLSEYE_BEFORE_PAUSE` | 3 | `ALERT_MAX_BULLSEYE` | Auto-pause alert after this many bullseye matches |
| `NOTIFICATION_THROTTLE_SECONDS` | 3600 | `ALERT_THROTTLE_SECONDS` | Minimum seconds between notifications for the same alert |
| `ALERT_LIFESPAN_DAYS` | 14 | `ALERT_LIFESPAN_DAYS` | Days before an alert expires |
| `RING_TOLERANCE` | 0.05 | `ALERT_RING_TOLERANCE` | How far below high water mark a Ring match can be |
| `TIER_1_THRESHOLD` | 0.82 | `ALERT_BULLSEYE_THRESHOLD` | Minimum score for Bullseye tier |
| `TIER_2_THRESHOLD` | 0.55 | `ALERT_RING_THRESHOLD` | Minimum score for Ring tier |

**Rule 1.2 — Zero means disabled**
Setting any limit to 0 disables it. `MAX_ALERTS_PER_USER=0` means unlimited alerts. `NOTIFICATION_THROTTLE_SECONDS=0` means no throttling.

### 2. Max Alerts Per User

**Rule 2.1 — Creation Limit**
When a buyer tries to create an alert and already has `MAX_ALERTS_PER_USER` active alerts, the creation is rejected. The frontend shows: "You've reached the maximum of 20 active alerts. Pause or delete an existing alert to create a new one."

**Rule 2.2 — Counting Only Active**
Only `is_active = True` alerts count toward the limit. Paused and expired alerts don't count.

### 3. Auto-Pause After Matches

**Rule 3.1 — Total Match Count**
When an alert has generated `MAX_MATCHES_BEFORE_PAUSE` total notifications (both Bullseye and Ring), the alert is automatically paused (`is_active = False`). The buyer receives a DM: "🔕 Your alert for 'iPhone 13' has been paused after 10 matches. Resume it anytime in the Alerts tab."

**Rule 3.2 — Bullseye Count**
If an alert generates `MAX_BULLSEYE_BEFORE_PAUSE` Bullseye matches specifically, it's paused immediately regardless of the total count. The DM says: "🎯 Your alert for 'iPhone 13' found 3 exact matches and has been paused. You probably already found what you need."

**Rule 3.3 — Bullseye Takes Priority**
If both thresholds are reached on the same match, the Bullseye message is sent.

**Rule 3.4 — Match Counter Reset on Resume**
When a paused alert is resumed, its match counters reset to zero. The buyer gets a fresh start.

### 4. Notification Throttle

**Rule 4.1 — Per-Alert Cooldown**
After a notification is dispatched for an alert, no further notifications for that same alert are generated within `NOTIFICATION_THROTTLE_SECONDS`. Multiple items matching within the cooldown are silently skipped.

**Rule 4.2 — Throttle Only Affects Dispatch**
The alert matching pipeline still runs and computes scores. The throttle only prevents the notification from being created. The alert's `last_triggered_at` is used to determine the cooldown.

**Rule 4.3 — Bullseye Bypasses Throttle**
Bullseye matches always generate notifications regardless of the throttle. The throttle only applies to Ring matches.

### 5. Duplicate Suppression

**Rule 5.1 — Same Item, Same Alert**
An alert never generates more than one notification for the same item. If item #159 triggered alert #9 once, it will never trigger alert #9 again — even if the item is re-ingested, updated, or matched through a different path.

**Rule 5.2 — Implementation**
Before creating a notification, the system checks the `notifications` table for an existing record with the same `alert_id` and `item_id`. If one exists (any status: PENDING, SENT, FAILED), no new notification is created.

### 6. Expiry

**Rule 6.1 — Configurable Lifespan**
Alerts expire `ALERT_LIFESPAN_DAYS` after creation. On expiry, the buyer receives a DM: "⏰ Your alert for 'iPhone 13' has expired. Create a new one anytime."

**Rule 6.2 — Expiry Check Timing**
Expiry is checked at the beginning of alert matching (already implemented). A background task runs once per day to expire old alerts and notify buyers.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Alert limit reached | Creation rejected with clear message to buyer |
| All alerts auto-paused | Buyer can still browse — alerts tab shows paused alerts with "Resume" option |
| Environment variable is negative | Treated as 0 (disabled) |
| Environment variable is not a number | Falls back to default |

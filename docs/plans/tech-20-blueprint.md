# TECH-20 Blueprint — Alert Guardrails

**Goal:** Introduce configurable alert rate limits, auto-pause, notification throttle, duplicate suppression, and match-counter reset using a shared constants module with environment variable overrides.

---

## Files to Modify/Create

| Action | File Path | Purpose |
|--------|-----------|---------|
| **CREATE** | `backend/constants.py` | Single source of truth for all 8 alert limits with env-var overrides |
| **MODIFY** | `backend/models.py` | Add `total_matches`, `bullseye_matches` to Alert; make `Notification.item_id` nullable; add `Notification.message_text` |
| **MODIFY** | `backend/services/alerting.py` | Max-alert check, throttle, dedup, auto-pause with counters, expiry DM, read constants |
| **MODIFY** | `backend/api/routes/alerts.py` | Max-alert rejection on create, match-counter reset on resume, import constants |
| **MODIFY** | `backend/ai_engine/matcher.py` | Replace hardcoded thresholds with imports from `constants` |
| **MODIFY** | `backend/schemas.py` | Make `NotificationResponse.item` optional for system DMs |
| **MODIFY** | `listener/notifications.py` | Handle system notifications (null item) in the notification poller |
| **CREATE** | `backend/tests/test_tech20.py` | Integration tests for all guardrail behaviors |

---

## Strict Import Map

### 1. `backend/constants.py` — NEW FILE

Exports the following names consumed by downstream modules:

| Name | Type | Default | Env Var |
|------|------|---------|---------|
| `MAX_ALERTS_PER_USER` | `int` | 20 | `ALERT_MAX_PER_USER` |
| `MAX_MATCHES_BEFORE_PAUSE` | `int` | 10 | `ALERT_MAX_MATCHES` |
| `MAX_BULLSEYE_BEFORE_PAUSE` | `int` | 3 | `ALERT_MAX_BULLSEYE` |
| `NOTIFICATION_THROTTLE_SECONDS` | `int` | 3600 | `ALERT_THROTTLE_SECONDS` |
| `ALERT_LIFESPAN_DAYS` | `int` | 14 | `ALERT_LIFESPAN_DAYS` |
| `RING_TOLERANCE` | `float` | 0.05 | `ALERT_RING_TOLERANCE` |
| `TIER_1_THRESHOLD` | `float` | 0.82 | `ALERT_BULLSEYE_THRESHOLD` |
| `TIER_2_THRESHOLD` | `float` | 0.55 | `ALERT_RING_THRESHOLD` |

**Parsing rules:**
- Zero means disabled (unlimited alerts, no throttle, no pause, etc.).
- Negative env var values are treated as zero.
- Non-numeric env var values fall back to the default.
- Each constant is read once at module load time from `os.getenv()`.

**Consumed by:**
- `backend/services/alerting.py` → `MAX_ALERTS_PER_USER`, `MAX_MATCHES_BEFORE_PAUSE`, `MAX_BULLSEYE_BEFORE_PAUSE`, `NOTIFICATION_THROTTLE_SECONDS`, `ALERT_LIFESPAN_DAYS`, `RING_TOLERANCE`
- `backend/api/routes/alerts.py` → `MAX_ALERTS_PER_USER`
- `backend/ai_engine/matcher.py` → `TIER_1_THRESHOLD`, `TIER_2_THRESHOLD`

### 2. `backend/models.py` — ALERT MODEL EXTENSION

**Alert table — new columns:**

| Column | Type | Default | Constraint |
|--------|------|---------|------------|
| `total_matches` | `Integer` | `0` | `nullable=False` |
| `bullseye_matches` | `Integer` | `0` | `nullable=False` |

These columns count the number of notifications generated for this alert since its last resume. They are incremented inside `backend/services/alerting.py` after each dispatch and reset to zero when the alert is resumed via the PATCH endpoint.

**Notification table — modifications:**

- Change `item_id` column from `nullable=False` to `nullable=True`. System DMs (auto-pause, expiry) do not have an associated item.
- Add `message_text` column: `Column(Text, nullable=True)`. For system DMs this column carries the exact Telegram message text; for normal match notifications it is `None`.

### 3. `backend/services/alerting.py` — IMPORT ADDITIONS

Add at the top:
```python
from constants import (
    MAX_ALERTS_PER_USER,
    MAX_MATCHES_BEFORE_PAUSE,
    MAX_BULLSEYE_BEFORE_PAUSE,
    NOTIFICATION_THROTTLE_SECONDS,
    ALERT_LIFESPAN_DAYS,
    RING_TOLERANCE,
)
```

No functions or variables are removed from this file; five new behaviors are added (see Step-by-Step below).

### 4. `backend/api/routes/alerts.py` — IMPORT ADDITION

Add at the top:
```python
from constants import MAX_ALERTS_PER_USER
```

No other import changes.

### 5. `backend/ai_engine/matcher.py` — IMPORT ADDITION

Add at the top:
```python
from constants import TIER_1_THRESHOLD, TIER_2_THRESHOLD
```

Remove the two hardcoded module-level assignments:
```python
TIER_1_THRESHOLD = 0.82  # ← DELETE
TIER_2_THRESHOLD = 0.55  # ← DELETE
```

The names `TIER_1_THRESHOLD` and `TIER_2_THRESHOLD` remain in scope because they are now imported from constants. Downstream consumers of these names (the `evaluate_match` function's tier classification block at lines 93-95) require no changes.

### 6. `backend/schemas.py` — NOTIFICATION RESPONSE UPDATE

Change the `item` field in `NotificationResponse`:
```python
item: ItemResponse          # ← old (required)
item: Optional[ItemResponse] = None  # ← new (optional for system DMs)
```

### 7. `listener/notifications.py` — NOTIFICATION POLLER UPDATE

The `notification_poller` function at lines 59-104 must branch on whether `notif['item']` is present.

---

## Step-by-Step Execution

### Step 1 — Create `backend/constants.py`

Create a new file at `backend/constants.py` that defines all eight constants using a helper pattern:

1. Define a private helper function `_get_config(key: str, default: Any, cast: type)` that:
   - Reads `os.getenv(key)`.
   - If the value is `None`, returns `default`.
   - If `cast` is `int` or `float`, tries to parse the string.
   - If parsing fails, log a warning and return `default`.
   - If the parsed value is negative, return `0` (treated as disabled).
   - Returns the cast value.

2. Define eight module-level constants calling `_get_config` with the names, defaults, env-var keys, and types listed in the Import Map above.

3. Add a docstring at the top explaining the purpose of the module.

---

### Step 2 — Extend the Alert and Notification models in `backend/models.py`

**On the `Alert` class (after `best_opportunity_score` around line 75):**

Add two new columns:
- `total_matches = Column(Integer, default=0, nullable=False)` — running count of all notifications generated since last resume.
- `bullseye_matches = Column(Integer, default=0, nullable=False)` — running count of bullseye notifications since last resume.

**On the `Notification` class:**

- Change line 87: `item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=True)` (was `nullable=False`).
- Add after `status` column (around line 95): `message_text = Column(Text, nullable=True)`.

**Note to @build:** A manual database migration is required:
```sql
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS total_matches INTEGER NOT NULL DEFAULT 0;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS bullseye_matches INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notifications ALTER COLUMN item_id DROP NOT NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message_text TEXT;
```

---

### Step 3 — Modify `backend/services/alerting.py`

This is the largest change. Five new behaviors are woven into the existing `create_alert` and `process_new_item` functions plus a new helper.

#### 3a. Max alerts per user check in `create_alert`

**Location:** Inside `create_alert`, before `vector = vectorize_text(query_text)` (line 179).

Add a check:
1. If `MAX_ALERTS_PER_USER > 0` (not disabled), count the user's active alerts with `db.scalar(select(func.count()).select_from(Alert).where(Alert.user_id == user.id, Alert.is_active == True))`.
2. If the count is `>= MAX_ALERTS_PER_USER`, raise an `HTTPException` with status code `400` and detail message: `"You've reached the maximum of {MAX_ALERTS_PER_USER} active alerts. Pause or delete an existing alert to create a new one."`
3. The `create_alert` function signature gains no new parameters.

#### 3b. Replace hardcoded alert lifespan in `create_alert`

**Location:** Line 183.

Replace `timedelta(days=14)` with `timedelta(days=ALERT_LIFESPAN_DAYS)`.

#### 3c. Replace hardcoded ring tolerance in `process_new_item`

**Location:** Line 155.

Replace `tolerance = 0.05` with `tolerance = RING_TOLERANCE`.

#### 3d. Notification throttle for Ring matches

**Location:** Inside the `if should_notify:` block around line 164, before calling `_dispatch_notification`.

Insert throttle logic:
1. If `result.tier == MatchTier.RING` (bullseye bypasses throttle), check `alert.last_triggered_at`.
2. If `last_triggered_at` is not `None` and `NOTIFICATION_THROTTLE_SECONDS > 0` and `(now_utc - last_triggered_at).total_seconds() < NOTIFICATION_THROTTLE_SECONDS`, skip dispatch for this match. Log a message: `"⏱️ Throttled: Alert {alert.id} within cooldown window."` Set `should_notify = False`.
3. Bullseye matches skip this check entirely and are always dispatched.

#### 3e. Duplicate suppression in `_dispatch_notification` (or before calling it)

**Location:** Before calling `_dispatch_notification` in the `if should_notify:` block (around line 169).

Insert a duplicate check:
1. Execute: `existing = db.scalar(select(Notification).where(Notification.alert_id == alert.id, Notification.item_id == item.id).limit(1))`.
2. If `existing` is not `None`, skip dispatch. Log: `"🔁 Duplicate suppressed: Alert {alert.id} already notified for Item {item.id}."` Set `should_notify = False`.
3. This check applies to both Bullseye and Ring matches.

#### 3f. Match counter increment and auto-pause

**Location:** After the duplicate-suppression and throttle checks, immediately after `_dispatch_notification` succeeds (still inside the `if should_notify:` block after line 169).

After dispatching:
1. Increment `alert.total_matches += 1`.
2. If `result.tier == MatchTier.BULLSEYE`, increment `alert.bullseye_matches += 1`.

Then check auto-pause thresholds (Bullseye takes priority):
1. If `MAX_BULLSEYE_BEFORE_PAUSE > 0` and `alert.bullseye_matches >= MAX_BULLSEYE_BEFORE_PAUSE`:
   - Set `alert.is_active = False`.
   - Create a system notification using the new helper (see 3g) with message: `"🎯 Your alert for '{alert.query_text}' found {MAX_BULLSEYE_BEFORE_PAUSE} exact matches and has been paused. You probably already found what you need."` and tier `"system_pause"`.
   - Log: `"⏸️ Auto-paused Alert {alert.id} after {MAX_BULLSEYE_BEFORE_PAUSE} bullseye matches."`
2. Else if `MAX_MATCHES_BEFORE_PAUSE > 0` and `alert.total_matches >= MAX_MATCHES_BEFORE_PAUSE`:
   - Set `alert.is_active = False`.
   - Create a system notification with message: `"🔕 Your alert for '{alert.query_text}' has been paused after {MAX_MATCHES_BEFORE_PAUSE} matches. Resume it anytime in the Alerts tab."` and tier `"system_pause"`.
   - Log: `"⏸️ Auto-paused Alert {alert.id} after {MAX_MATCHES_BEFORE_PAUSE} total matches."`

#### 3g. Expiry DM check in `process_new_item`

**Location:** Inside the expiry pre-check block (lines 55-60), where expired alerts are currently skipped.

Modify the expired-alert branch:
1. Before `continue`, set `alert.is_active = False`.
2. Create a system notification with message: `"⏰ Your alert for '{alert.query_text}' has expired. Create a new one anytime."` and tier `"system_expiry"`.
3. Log: `"⌛ Expired Alert {alert.id}, DM sent."`
4. Then `continue` (skip matching).

#### 3h. New helper: `_create_system_notification`

Create a new private function inside `backend/services/alerting.py`:

```python
def _create_system_notification(db: Session, user_id: int, alert_id: int, message: str, tier: str) -> None:
    """
    Creates a Notification with no item for system DMs (auto-pause, expiry).
    The Listener's notification poller will detect message_text and format accordingly.
    """
    notification = Notification(
        user_id=user_id,
        item_id=None,
        alert_id=alert_id,
        match_tier=tier,
        match_score=0.0,
        status="PENDING",
        message_text=message,
    )
    db.add(notification)
    logger.info(f"📨 [SAVED] System DM for User {user_id} queued: {tier}")
```

This function is called from steps 3f (auto-pause) and 3g (expiry).

---

### Step 4 — Modify `backend/api/routes/alerts.py`

#### 4a. Max alerts check on creation

**Location:** Inside `create_new_alert` (around line 88-91), before calling `create_alert`.

Add a check:
1. If `MAX_ALERTS_PER_USER > 0`, query the count of active alerts for the user: `active_count = db.scalar(select(func.count()).select_from(Alert).where(Alert.user_id == user.id, Alert.is_active == True))`.
2. If `active_count >= MAX_ALERTS_PER_USER`, raise `HTTPException(status_code=400, detail="...")` with the formatted message.
3. Note: This duplicates the check in `create_alert` (step 3a). The route-level check is the primary gate; the service-level check in `create_alert` is a safety net. Both should exist.

#### 4b. Match counter reset on resume

**Location:** Inside `toggle_alert_pause` (lines 162-201), between the "Toggle" and "Analytics" sections.

Modify the toggle logic:
1. Before the toggle, capture the current state: `was_active = alert.is_active`.
2. Toggle: `alert.is_active = not alert.is_active`.
3. After toggling, if `was_active is False and alert.is_active is True` (resume):
   - Set `alert.total_matches = 0`.
   - Set `alert.bullseye_matches = 0`.
   - Log: `"🔄 Reset match counters for Alert {alert.id} on resume."`

The existing analytics and response logic remains unchanged.

---

### Step 5 — Modify `backend/ai_engine/matcher.py`

1. Add the import line: `from constants import TIER_1_THRESHOLD, TIER_2_THRESHOLD`.
2. Delete lines 18-19 (the hardcoded `TIER_1_THRESHOLD = 0.82` and `TIER_2_THRESHOLD = 0.55`).
3. No other changes. The `evaluate_match` function's tier classification at lines 93-95 continues to use these names, which are now resolved from the shared constants module.

---

### Step 6 — Modify `backend/schemas.py`

In `NotificationResponse` (lines 222-231), change:
```python
item: ItemResponse
```
to:
```python
item: Optional[ItemResponse] = None
```

This allows the `/notifications/pending` endpoint to return system notifications where the item is `None`.

---

### Step 7 — Modify `listener/notifications.py`

**Location:** Inside `notification_poller`, the per-notification loop (lines 59-103).

Add a branch before the current item-dependent formatting logic:

1. Check if `notif.get('message_text')` is not `None` (indicating a system DM).
2. If system DM:
   - Set `msg_text = notif['message_text']`.
   - Set `item_url = None`.
   - Set `notif_alert_id = notif.get('alert_id')`.
   - Call `await send_alert_dm(bot, notif['user_telegram_id'], msg_text, alert_id=notif_alert_id, item_url=None)`.
   - Continue to acknowledgment as normal.
3. If NOT a system DM (normal match notification), keep the existing item-dependent formatting logic unchanged (the `else` branch).

This ensures that when `notification_poller` receives a notification with `message_text` set, it delivers the exact message without trying to access `notif['item']['title']`.

---

### Step 8 — Create `backend/tests/test_tech20.py`

Create integration tests that exercise the guardrail behaviors against the running API. Follow the testing pattern established in `backend/tests/test_tech17.py` (httpx-based, skips if API unreachable).

**Test cases:**

| ID | Test | What It Verifies |
|----|------|-----------------|
| `T1` | Create alert when under limit | Alert creation succeeds when user has fewer than `MAX_ALERTS_PER_USER` active alerts. |
| `T2` | Reject alert at limit | Creating alert when user already has `MAX_ALERTS_PER_USER` active alerts returns HTTP 400 with the limit message. |
| `T3` | Paused alert doesn't count toward limit | Pausing an alert via PATCH, then creating a new one succeeds even though total alerts (including paused) exceeds the limit. |
| `T4` | Match counter increments | After a notification is dispatched for an alert, the alert's `total_matches` field is incremented in the DB. |
| `T5` | Match counter resets on resume | Pausing then resuming an alert resets both `total_matches` and `bullseye_matches` to zero. |
| `T6` | Duplicate suppression | Same alert+item pair does not generate a second notification when the item is re-ingested. |
| `T7` | Throttle window respected | A ring match within `NOTIFICATION_THROTTLE_SECONDS` of `last_triggered_at` does not create a new notification. |
| `T8` | Bullseye bypasses throttle | A bullseye match within the throttle window still generates a notification. |
| `T9` | Auto-pause after bullseye limit | After `MAX_BULLSEYE_BEFORE_PAUSE` bullseye notifications, the alert is deactivated and a system DM notification is created. |
| `T10` | Auto-pause after total match limit | After `MAX_MATCHES_BEFORE_PAUSE` total notifications, the alert is deactivated and a system DM is created. |
| `T11` | Expiry DM created | An alert that has expired generates a system DM notification with `message_text` set. |
| `T12` | Constants import via env var | Set `ALERT_MAX_PER_USER=5` environment variable, verify the API enforces the limit at 5 (not the default 20). |

**Important testing notes for @build:**
- Tests must use unique user IDs (varying `telegram_id`) to avoid collisions with existing data.
- Test alert creation uses the `init_data` parameter as a plain integer string with the `X-Internal-Service: index-listener` header.
- For T6 (duplicate suppression): submit an item twice and verify only one notification is created.
- For T7/T8: set `ALERT_THROTTLE_SECONDS` to a small value (like 10) for the test, trigger a notification, then immediately try again.
- For T11 (expiry): create an alert with a past `expires_at` (by direct DB manipulation or using a test-specific endpoint) and then trigger matching.
- Tests must clean up after themselves (delete created alerts/items).

---

## Database Migration Required

A manual migration must be applied before the new code runs:

```sql
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS total_matches INTEGER NOT NULL DEFAULT 0;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS bullseye_matches INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notifications ALTER COLUMN item_id DROP NOT NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message_text TEXT;
```

The `@build` agent should run this migration against the `db` container before testing.

---

## Behavioral Contract Summary

| Rule | Trigger | Action |
|------|---------|--------|
| Max alerts per user | POST /alerts/ | Reject if active count >= MAX_ALERTS_PER_USER |
| Auto-pause (bullseye) | bullseye counter >= MAX_BULLSEYE_BEFORE_PAUSE | is_active=False + DM |
| Auto-pause (total) | total counter >= MAX_MATCHES_BEFORE_PAUSE | is_active=False + DM |
| Throttle | Ring match within NOTIFICATION_THROTTLE_SECONDS | Skip notification (bullseye bypasses) |
| Dedup | Existing Notification with same alert_id+item_id | Skip notification |
| Match counter reset | Resume alert (PATCH, is_active: false→true) | total_matches=0, bullseye_matches=0 |
| Expiry DM | expires_at < now during matching | is_active=False + DM |
| Config zero=disabled | Any constant set to 0 | No limit/throttle/pause enforced |

# TECH-25 Blueprint: Alert & Notification Retention Lifecycle

**Date:** 2026-08-01
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture
**Authority:** `docs/adr/0001-alert-notification-retention.md` (accepted 2026-08-01); acceptance criteria in `docs/adr/tech-backlog.md` §TECH-25 (lines 33-50)

---

## 1. Architecture Context

### 1.1 The friction (measured, verbatim context)

- `suq_main_db`: **464 alerts, 100% inactive** (`is_active = false`); the `alerts` table is the largest in the database (2.7 MB / 464 rows — dominated by the 512-dim `query_vector`, ~2 KB/row).
- **Zero cleanup logic touches alerts or notifications.** Graphify confirms the `run_daily_cleanup()` node (community 68, `backend/services/cleanup.py` L27) has exactly four edges: `cleanup.py [contains]`, calls `send_owner_dm_sync()`, and is called by `run_cleanup_and_log()` only. No edge to `Alert` or `Notification` exists today.
- **sqladmin hard-delete of alerts is blocked** by `notifications_alert_id_fkey` (default RESTRICT, no `ON DELETE`). `backend/models.py` line 92: `alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)` — verified.
- **Soft deletes are load-bearing** (TECH-21 dedup, match history via `notifications.item_id` CASCADE at `models.py:91`, dedup-suppression guardrail joining Notification→Item). The fix is a **retention lifecycle**, not a delete-mechanism change. The deletion test fails for a hard-delete redesign; it passes for a retention slot added to the existing daily cleanup module.

### 1.2 Files involved (line anchors verified 2026-08-01)

| Action | File | Verified anchors |
|---|---|---|
| MODIFY | `backend/models.py` | `Alert` class lines 49-82; `Notification` class lines 85-107; `alert_id` FK at line 92; `DateTime` imported line 1 |
| MODIFY | `backend/constants.py` | 79 lines; `_get_config` lines 21-51; existing groups end at line 79 (`STALE_ITEM_DAYS`) |
| MODIFY | `backend/main.py` | `from sqlalchemy import text` at line 7; migration blocks lines 67-144 (TECH-19 at 70-80, TECH-21 at 82-90, TECH-21b at 92-100, TECH-22 at 102-124, TECH-23 at 126-144); cleanup scheduler lines 200-219 |
| MODIFY | `backend/api/routes/alerts.py` | `delete_alert` lines 82-111; `toggle_alert_pause` lines 117-166; constants import line 12; **no datetime import present** |
| MODIFY | `backend/services/cleanup.py` | 142 lines; imports lines 11-22; phases 1-3 lines 39-122; summary dict lines 126-130; `run_cleanup_and_log` lines 133-142 |
| CREATE | `backend/tests/test_tech25.py` | new module per §5 |

### 1.3 Dependency categories (skill vocabulary)

- **`run_daily_cleanup()` = Local-substitutable module.** Its only external dependencies are the SQLAlchemy Session (`SessionLocal()`, constructed at `cleanup.py:32`) and the in-process retention constants. The test stand-in is conftest's `db_session` fixture (same physical DB, `suq_test_db`); seeding through the fixture is observable by cleanup's own session because both hit one Postgres. **No new seam is created** — Phases 4 and 5 slot into the existing module interface; the summary dict is the interface's report channel.
- **Retention constants = in-process config.** `ALERT_RETENTION_DAYS` / `NOTIFICATION_RETENTION_DAYS` are read at module load in `constants.py` and bound as module-level names in `services.cleanup` (verified import style, `cleanup.py:18-22`). This makes the constants a patch point (`monkeypatch.setattr("services.cleanup.ALERT_RETENTION_DAYS", 1)`) — a hypothetical seam with one adapter today, sufficient for the test surface.
- **`delete_alert` route = interface-stable module.** The change is a write side-effect on an existing object; the route signature, auth flow, and response shape do not change.

---

## 2. The New Interfaces

### 2.1 `run_daily_cleanup()` — extended summary dict (5 keys)

The function keeps its signature and return type (dict). The summary dict gains exactly two keys, keeping the existing three unchanged:

```
soft_deleted_removed   (existing)
reported_sold_removed  (existing)
stale_flagged          (existing)
alerts_purged          (NEW — Phase 4)
notifications_purged   (NEW — Phase 5)
```

`run_cleanup_and_log()`'s log line (lines 137-141) must be extended to report the two new counts, in the existing emoji-prefixed style.

### 2.2 `delete_alert` side-effect

`DELETE /alerts/{alert_id}` (`alerts.py:82-111`) additionally sets `alert.deleted_at = datetime.now(timezone.utc)` **before the existing commit** (line 97), alongside the existing `alert.is_active = False` (line 96). No response-shape change.

**Verified:** `toggle_alert_pause` (lines 117-166) touches only `is_active` (line 140) and, on resume, resets match counters (lines 143-147). It does **not** touch `deleted_at` — no change required there; this is an invariant, not a fix.

### 2.3 New column

`Alert.deleted_at` — `DateTime(timezone=True)`, nullable, no default. Placed in the State Management group of the `Alert` class, immediately after `last_triggered_at` (line 72). Nullable and unset means "never user-deleted" — the purge predicate branches on NULL explicitly.

### 2.4 Migration statements (idempotent, repo style)

Two statements inside **one new try-block** in `main.py`, inserted after the TECH-23 block (line 144), before Phase 4 indexes, following the TECH-22 multi-statement precedent (`with engine.begin() as conn:` + `conn.execute(text(...))` + `logger.info("✅ TECH-25 schema migration verified (...)")`):

1. `ALTER TABLE alerts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ` — the repo's standard `ADD COLUMN IF NOT EXISTS` idiom (matches TECH-19/TECH-21 style; no DEFAULT because the column is nullable).
2. FK swap for `notifications_alert_id_fkey`:
   - First statement: a `DO $$ ... $$` block that queries `pg_constraint` for `conname = 'notifications_alert_id_fkey' AND conrelid = 'notifications'::regclass` and, **only if present**, executes `ALTER TABLE notifications DROP CONSTRAINT notifications_alert_id_fkey`.
   - Second statement: `ALTER TABLE notifications ADD CONSTRAINT notifications_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE`.
   - **Idempotency rationale (state this in a comment):** PostgreSQL has no `ADD CONSTRAINT IF NOT EXISTS`, so the drop-guard is the repo-consistent extension of the idempotency idiom. The sequence is safe across all three states: legacy DB (constraint exists, RESTRICT → dropped, re-added with CASCADE), a prior TECH-25 run (constraint exists, CASCADE → dropped, re-added identical — a no-op churn), and a fresh DB (constraint created by `create_all` with CASCADE from the model change → dropped, re-added — a no-op churn). No error path on any repeat.

### 2.5 The invariants (contract of the new behavior)

1. **Paused alerts are protected by construction.** A paused alert has `deleted_at IS NULL` and a future `expires_at`; it matches neither predicate branch. Same for active alerts. The purge predicate needs no `is_active` check — protection is structural, not a filter flag.
2. **Expiry remains absolute.** An alert that expired while paused is still dead per the domain rule (14-day lifespan); it purges N days after expiry. (Resume of an expired alert is already moot — the expiry gate in `process_new_item` deactivates it.)
3. **`<= 0` disables retention.** Both phases must be wrapped in a guard on their constant being `> 0`. Zero/negative means "retention disabled, no purge" — safe-by-default, mirroring the `MAX_*` constant semantics. `_get_config` (constants.py:21-51) already clamps negatives to 0; the constant defaults are 30 (alerts) and 90 (notifications).
4. **PENDING notifications are never purged.** Phase 5 selects by an explicit terminal-status list (`SENT`, `FAILED`, `REPLACED`), never by `!= 'PENDING'` alone. A PENDING row older than the cutoff survives. (`REPLACED` is a real terminal status: set by the dedup-suppression `update()` in `backend/api/routes/ingestion.py:187` — verified; `SENT` is set in `backend/api/routes/notifications.py:44`; `FAILED` has no in-repo writer but is part of the documented status vocabulary at `models.py:99` and must stay in the list per the ADR.)
5. **No backfill.** Legacy dead rows (`is_active = false`, `deleted_at NULL`) are **not** touched by any migration or phase — `is_active = false` cannot distinguish legacy paused from legacy deleted alerts. Legacy rows purge after their `expires_at` passes + retention. Current test data requires the one-time SQL in Appendix A.
6. **Alert purge is silent** — no owner DM (Phases 1-2 DM; Phases 4-5 must not).

### 2.6 What the implementation hides

- The FK mechanics: deleting an alert row cascades its notifications **at the database level** (`ON DELETE CASCADE`). No ORM relationship or `cascade=` change is needed — `Alert` has no relationship to `Notification` (verified, `models.py:81-82`), so SQLAlchemy never loads or nulls notification rows when an alert is deleted; the DB does the work. The `Notification.alert` relationship (line 107) is untouched.
- The session lifecycle: each phase keeps the existing per-phase `try/except → rollback → commit` pattern; the module still opens and closes its own `SessionLocal()`.
- The status-literal table for retention lives inside Phase 5's select, not in constants.

---

## 3. Strict Import Map

### 3.1 `backend/services/cleanup.py`

**Current (verified, lines 11-22):** `import logging`; `from datetime import datetime, timedelta, timezone`; `from sqlalchemy import select, func`; `from database import SessionLocal`; `from models import Item, Channel, UserInteraction`; `from services.owner_dm import send_owner_dm_sync`; `from constants import (SOFT_DELETED_RETENTION_DAYS, REPORTED_SOLD_RETENTION_DAYS, STALE_ITEM_DAYS)`.

**Changes (exactly three):**

| Line | Before | After |
|---|---|---|
| 13 | `from sqlalchemy import select, func` | `from sqlalchemy import select, func, or_` (Phase 4 needs the OR combinator; the existing comma-separated WHERE is AND-only) |
| 16 | `from models import Item, Channel, UserInteraction` | `from models import Item, Channel, UserInteraction, Alert, Notification` |
| 18-22 | three constants | append `ALERT_RETENTION_DAYS,` and `NOTIFICATION_RETENTION_DAYS,` inside the existing parenthesized import |

Everything else stays: `send_owner_dm_sync` remains (Phases 1-2), `logging`/`datetime`/`SessionLocal` unchanged. Module docstring (lines 2-9) updates "three cleanup phases" → five, listing Phases 4 and 5.

### 3.2 `backend/models.py`

- **No import changes** — `DateTime`, `ForeignKey` already imported at line 1.
- Line 92: `alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)` → `alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True)` (mirrors the `notifications.item_id` precedent at line 91).
- `Alert`: add `deleted_at = Column(DateTime(timezone=True), nullable=True)` after line 72 (`last_triggered_at`).

### 3.3 `backend/main.py`

- **No import changes** — `from sqlalchemy import text` verified at line 7.
- Add the one TECH-25 try-block (§2.4) after line 144. **No changes to the cleanup scheduler** (verified lines 200-219: `threading.Timer(60, ...)` first run, `threading.Timer(86400, ...)` reschedule — the daily cadence already exists; ADR contract: no new scheduler).

### 3.4 `backend/api/routes/alerts.py`

- **ADD** `from datetime import datetime, timezone` — **verified NOT currently imported** (module imports: fastapi, sqlalchemy.orm, sqlalchemy `select, func`, typing, `database.get_db`, `models`, `schemas`, `services.alerting`, `services.analytics`, `services.auth`, `constants.MAX_ALERTS_PER_USER`).
- **NO** change to the constants import — the retention constants are consumed by `services/cleanup.py` only, not by the route (confirmed).
- `delete_alert`: add the `deleted_at` assignment between line 96 (`alert.is_active = False`) and line 97 (`db.commit()`).

### 3.5 `backend/tests/test_tech25.py` (new module)

Top-level imports, repo convention (conftest puts `backend/` on `sys.path`; models/constants/services importable bare):

```python
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from models import Alert, Notification, Item, User, Channel
from services.cleanup import run_daily_cleanup
from constants import ALERT_RETENTION_DAYS, NOTIFICATION_RETENTION_DAYS
```

Plus, for the route test only: `from fastapi import BackgroundTasks` and `from api.routes.alerts import delete_alert` (house direct-call pattern, §5 test 8).

---

## 4. Execution Steps

1. **Branch.** Create `feat/tech-25-alert-retention-lifecycle` from current HEAD (repo convention `feat/tech-XX-<slug>`). Note: HEAD (`arch/alert-pipeline-deepening`) currently carries uncommitted docs — `docs/adr/0001-alert-notification-retention.md` (untracked) and edits to `docs/adr/tech-backlog.md`, `CONTEXT.md`. Commit these docs first (docs-only commit) so the feature branch is self-contained; never work on `main`.

2. **`backend/models.py`.** Add `deleted_at` to `Alert` (§3.2). Change `Notification.alert_id` FK to `ondelete="CASCADE"`. Touch nothing else — all existing columns, relationships, and imports are preserved in full.

3. **`backend/main.py`.** Insert the TECH-25 migration try-block after line 144 (§2.4): the `deleted_at` ADD COLUMN and the FK drop-guard + re-add, with the idempotency comment. Keep the existing log/except style.

4. **`backend/constants.py`.** Append a new group after line 79:

   ```
   # --- Retention (TECH-25) ---
   ALERT_RETENTION_DAYS: int = _get_config("ALERT_RETENTION_DAYS", 30, int)
   NOTIFICATION_RETENTION_DAYS: int = _get_config("NOTIFICATION_RETENTION_DAYS", 90, int)
   ```

   Do **not** touch the docstring's consumer list — `services/cleanup.py` already consumes TECH-22 constants and is not listed; consistency is preserved by making no change.

5. **`backend/api/routes/alerts.py`.** Add the datetime import (§3.4). In `delete_alert`, set `deleted_at` before the commit. Verify `toggle_alert_pause` untouched (it must remain so).

6. **`backend/services/cleanup.py`.** In order:
   - Update imports (§3.1).
   - Update the module docstring to five phases.
   - Initialize `alerts_purged = 0` and `notifications_purged = 0` alongside the existing counters (lines 35-37).
   - **Phase 4** (after the Phase 3 block, line 122, before `db.close()` at line 124): guarded by `ALERT_RETENTION_DAYS > 0`. Compute `cutoff = now_utc - timedelta(days=ALERT_RETENTION_DAYS)`. Select alerts matching the OR of two conjunctions: (`deleted_at IS NOT NULL` AND `deleted_at < cutoff`) OR (`expires_at IS NOT NULL` AND `expires_at < cutoff`). Delete each row, increment `alerts_purged` per row; the FK cascade removes the alert's notifications at the DB level. Per-phase `try/except → rollback → commit`, log `🧹 Cleanup: Purged {n} dead alerts` only when `n > 0` (existing guard idiom), warning `⚠️ Alert purge error: {e}` on exception. No owner DM.
   - **Phase 5** (after Phase 4): guarded by `NOTIFICATION_RETENTION_DAYS > 0`. Compute cutoff the same way. Select notifications where `status` is one of the three terminal literals `SENT`, `FAILED`, `REPLACED` (explicit `IN` list) AND `created_at < cutoff`. Delete each, increment `notifications_purged`. Same try/except/rollback/commit/log idiom.
   - Extend the return dict (lines 126-130) with `alerts_purged` and `notifications_purged`.
   - Extend `run_cleanup_and_log`'s log line (lines 137-141) with both new counts.

7. **`backend/tests/test_tech25.py`.** Implement per §5. Seed helpers mirror `test_item_status.py` (`_make_user`, `_make_alert`, `_make_notification`); patching uses `monkeypatch.setattr` (house pattern, `test_auth.py`/`test_item_status.py`), targeting `"services.cleanup.ALERT_RETENTION_DAYS"` / `"services.cleanup.NOTIFICATION_RETENTION_DAYS"` (works because cleanup reads them as module-global names at call time — verified import style).

8. **Regression.** From repo root: `pytest backend/tests/ -q` (conftest redirects to `suq_test_db` at `localhost:5433`). All existing tests must stay green; the new module must pass. If the test DB connection fails, verify the Docker port mapping (`db:5432` → host `5433`) before touching code.

9. **Verification greps (proof of state):**
   - `deleted_at` present in `backend/models.py` (column), `backend/api/routes/alerts.py` (assignment), `backend/main.py` (migration).
   - `ondelete="CASCADE"` on both `notifications.item_id` and `notifications.alert_id` in `backend/models.py`.
   - `notifications_alert_id_fkey` appears twice in `backend/main.py` (drop-guard + re-add).
   - `ALERT_RETENTION_DAYS` and `NOTIFICATION_RETENTION_DAYS` in `backend/constants.py` and `backend/services/cleanup.py`.
   - `alerts_purged` / `notifications_purged` in cleanup's counters, summary dict, and log line.
   - `REPLACED` literal: writer at `backend/api/routes/ingestion.py:187`; consumer in `cleanup.py` Phase 5.

10. **Graphify update.** Run `graphify update .` (AGENTS.md §6) so the AST graph reflects the new edges (cleanup → Alert/Notification).

11. **Atomic commit.** Await explicit `@qa` approval, then stage only the intended files and commit once:

    `feat: alert & notification retention lifecycle — cascade FK, deleted_at, daily purge (TECH-25)`

    Never push unless the human admin instructs it.

---

## 5. Testing Requirements (interface is the test surface)

All tests assert observable outcomes through the module interface `run_daily_cleanup()` (seeding via `db_session`, assertions re-query via `db_session` — cleanup's own `SessionLocal()` sees the same `suq_test_db`). Timestamps are passed explicitly as aware datetimes (`datetime.now(timezone.utc) ± timedelta`), overriding `server_default`.

| # | Test | Scenario | Assertion surface |
|---|---|---|---|
| 1 | `test_purge_skips_active_alerts` | active alert (`is_active=True`), `expires_at` future, `deleted_at` NULL; retention patched to 1 | alert still present after `run_daily_cleanup()` |
| 2 | `test_purge_protects_paused_alerts` | `is_active=False`, `deleted_at` NULL, `expires_at` future (paused) — **THE regression guard** | alert still present |
| 3 | `test_purge_removes_deleted_alerts_after_retention` | `deleted_at = now - 2d`, retention patched to 1; seed a Notification (`user_id`, `alert_id`, `match_tier`, `status="SENT"`) referencing it | alert gone **and** its notification gone (DB-level cascade) |
| 4 | `test_purge_removes_expired_alerts_after_retention` | `is_active=True`, `expires_at = now - 2d`, retention patched to 1 | alert gone |
| 5 | `test_retention_disabled_at_zero` | `ALERT_RETENTION_DAYS` patched to 0; deleted alert seeded | dead alert survives (guard works) |
| 6 | `test_pending_notifications_never_purged` | `NOTIFICATION_RETENTION_DAYS` patched to 1; seed PENDING (old) + SENT/FAILED/REPLACED (old) notifications | PENDING survives; the three terminal ones are gone |
| 7 | `test_notification_retention_disabled_at_zero` | `NOTIFICATION_RETENTION_DAYS` patched to 0; old SENT notification seeded | survives |
| 8 | `test_delete_alert_sets_deleted_at` | route-level, **direct function call** (chosen explicitly over HTTP TestClient/httpx — deterministic, no server, no startup events, no AI deps): seed `User(telegram_id=333)` + owned `Alert`; call `delete_alert(alert.id, "333", _FakeRequest, BackgroundTasks(), db_session, x_internal_service="index-listener")` where `_FakeRequest` is a minimal stub exposing `.headers.get("x-session-id")`; the internal-bypass auth path is proven in `test_auth.py` | `alert.deleted_at` not None after the call (and `is_active` False) |
| 9 | `test_summary_dict_keys` | call `run_daily_cleanup()` with empty tables | returned dict contains exactly the 5 keys: `soft_deleted_removed`, `reported_sold_removed`, `stale_flagged`, `alerts_purged`, `notifications_purged` |

Notes: Phases 1-3 are no-ops in these tests (no items seeded), so no DM side effects fire. Do not patch `constants.ALERT_RETENTION_DAYS` — patch the bound names in `services.cleanup` (module-level lookup at call time).

---

## Appendix A — One-time SQL test-data cleanup (admin-run, NOT a migration)

Run manually against `suq_main_db` after deploy. FK-safe order (children before parents) — safe both before and after the cascade migration:

```sql
-- Targeted: purge current test/dead alerts (all is_active = FALSE rows) + their notifications
DELETE FROM notifications WHERE alert_id IN (SELECT id FROM alerts WHERE is_active = FALSE);
DELETE FROM alerts WHERE is_active = FALSE;

-- Full wipe (if a clean slate is desired) — FK-safe order:
DELETE FROM notifications;
DELETE FROM user_interactions;
DELETE FROM alerts;
DELETE FROM sold_reports;
DELETE FROM item_edits;
DELETE FROM item_images;
DELETE FROM items;
DELETE FROM reviews;
DELETE FROM channels;
DELETE FROM users;
```

This is explicitly **not** a migration and must never run from tests. Legacy rows not covered here purge naturally via `expires_at` + `ALERT_RETENTION_DAYS`.

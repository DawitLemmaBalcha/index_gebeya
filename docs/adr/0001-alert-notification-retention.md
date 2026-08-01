# ADR-0001: Alert & Notification Retention Lifecycle

**Status:** Accepted
**Date:** 2026-08-01
**Decision makers:** @architect, with @build/@qa execution via TECH-25
**Related tickets:** TECH-24 (deepened alert pipeline), TECH-25 (this decision's execution)
**Skill vocabulary:** module, interface, seam, adapter, leverage, locality (LANGUAGE.md)

---

## Context

Alerts and notifications accumulate without bound. A database measurement (2026-08-01) on `suq_main_db` showed:

- **464 alerts, 100% inactive** (`is_active = false`) — every row is dead weight.
- The `alerts` table is the **largest table in the database** (2.7 MB for 464 rows), dominated by the `query_vector` 512-dimension embedding (~2 KB per row) — not text.
- **Zero cleanup logic touches alerts or notifications.** The daily cleanup service (`services/cleanup.py`) only handles items (soft-deleted after 30 days, reported-sold after 7 days, stale flagging).
- **sqladmin hard-delete is blocked** by `notifications_alert_id_fkey` (no `ON DELETE` action → RESTRICT), making test-data cleanup impossible via the admin panel.

Soft deletes themselves are **load-bearing and correct** (ADR acknowledges the prior design):
1. Dedup (TECH-21) soft-deletes the old item so the replacement's new `item_id` re-triggers alert matching.
2. `notifications.item_id` cascades — hard-deleting an item would destroy buyer match history.
3. The dedup-suppression guardrail joins `Notification → Item`; hard deletion would erase suppression evidence and re-notify buyers.

The clutter problem is therefore a **retention lifecycle gap**, not a delete-mechanism defect. Disk space is a symptom, not the disease: the genuine costs are (a) operational paralysis (admin delete blocked), (b) unbounded growth of 2 KB vector rows, (c) a per-ingestion alert scan that grows with alert creation.

## Decision

### 1. FK policy: `notifications.alert_id` gains `ON DELETE CASCADE`

Align with the existing `notifications.item_id` CASCADE precedent. Migration (idempotent, per the repo's `main.py` ALTER TABLE pattern): drop constraint `notifications_alert_id_fkey`, re-add with `ON DELETE CASCADE`. This permanently unblocks sqladmin hard-delete and makes alert purge atomic with its notification history.

### 2. `Alert.deleted_at` column

Add nullable `deleted_at` to `Alert`. The `DELETE /alerts/{alert_id}` endpoint sets `deleted_at = now` (in addition to today's `is_active = false`). Pause/resume never touches `deleted_at`.

### 3. Alert purge predicate

`run_daily_cleanup` gains Phase 4, purging alerts where:

```
(deleted_at IS NOT NULL AND deleted_at < cutoff)
OR (expires_at IS NOT NULL AND expires_at < cutoff)
where cutoff = now - ALERT_RETENTION_DAYS
```

- **User-deleted alerts:** purge clock starts at deletion (not expiry) — test data and abandoned alerts leave quickly.
- **Expired alerts:** purge N days after expiry, whether or not the matching engine ever touched them.
- **Paused alerts are protected:** `deleted_at` is NULL and `expires_at` is in the future → never matches the predicate. Pausing is a user action asserting liveness.
- **Expiry remains absolute:** an alert that expires while paused is still dead per the domain rule (14-day lifespan); it purges N days after expiry. Resume of an expired alert is already moot (the expiry gate in `process_new_item` deactivates it).
- `ALERT_RETENTION_DAYS` default **30**, env `ALERT_RETENTION_DAYS`, via the `_get_config` guardrail in `constants.py`. **`<= 0` disables retention** (no purge) — safe-by-default posture, mirroring the `MAX_*` constant semantics.
- **No backfill** of legacy dead rows: `is_active = false` cannot distinguish legacy *paused* from legacy *deleted* alerts, and purging paused alerts would be a regression. Legacy rows purge after their `expires_at` passes + retention. One-time cleanup of current test data is an explicit SQL operation (documented in the blueprint), not a migration.

### 4. Notification retention

`run_daily_cleanup` gains Phase 5, purging notifications with `status IN ('SENT', 'FAILED', 'REPLACED')` older than `NOTIFICATION_RETENTION_DAYS` (default **90**, env-configurable). **PENDING notifications are never purged** — they are undelivered mail. `<= 0` disables.

Match history (`get_alert_matches`, last 50) remains fully functional; retention only bounds history, which is the intended semantic.

## Consequences

- **Positive:** sqladmin delete works for alerts; dead vector rows self-purge; per-ingestion active-alert scan stays bounded; match history is bounded by design; paused alerts are provably safe.
- **Negative:** deleted alerts are gone after N days (their notification labels degrade to NULL in history — acceptable; `alert_id` cascade removes the rows anyway); legacy dead rows need either time or one-time SQL.
- **Contract:** alert purge is silent — no owner DM (buyer alerts already received their expiry system DM); the purge runs inside the existing daily cleanup scheduling in `main.py` (no new scheduler).

## Compliance

TECH-25 acceptance criteria: cascade migration idempotent; purge skips active + paused alerts; purge removes deleted/expired; PENDING notifications never purged; full suite regression green; atomic commit on QA approval.

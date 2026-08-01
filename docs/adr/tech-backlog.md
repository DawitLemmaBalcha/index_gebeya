# Technical Backlog

*TECH-01 through TECH-24 implemented.*

---

## TECH-24: Deepen the Alert Matching Pipeline

**Status:** IMPLEMENTED ✅ — commit: see `git log` on `arch/alert-pipeline-deepening` branch
**Blueprint:** `docs/plans/arch-deepening-alert-pipeline.md`
**Skill:** improve-codebase-architecture
**Date:** 2026-08-01
**QA:** APPROVED

**The Friction:**
1. Divergent duplicated Speed Pass semantics — `alerting.py::_normalize` byte-identical to `matcher.normalize_string`, Stage 1 uses `==` while `evaluate_match` uses containment `in`. Behavior doc mandates containment; today containment matches waste an LLM call and risk false rejection.
2. Dead alpha matcher `services/alerts.py` — references nonexistent `Alert.search_query`, zero callers.
3. Misplaced search config (`SEMANTIC_WEIGHT`, `LEXICAL_WEIGHT`, `DEFAULT_RESULT_LIMIT`) living in `matcher.py`, consumed by `search.py` through the wrong seam.
4. No explicit deterministic-match signal on `MatchResult` — callers parse the `reason` string.

**Acceptance Criteria (all met):**
- `MatchResult` gains optional `speed_pass: bool = False`; invariant: `speed_pass=True ⟹ tier == BULLSEYE and score == 1.0`.
- `process_new_item` and `create_alert` external seams unchanged; containment speed passes skip the LLM judge (behavior-doc Rule 3.1 alignment).
- `services/alerts.py` deleted; search constants relocated to `constants.py`; `search.py` imports from `constants`.
- Patch targets `services.alerting.evaluate_match`, `services.alerting.NOTIFICATION_THROTTLE_SECONDS`, `services.alerting.MAX_BULLSEYE_BEFORE_PAUSE`, `services.alerting.MAX_MATCHES_BEFORE_PAUSE` still resolve (test_tech20.py passes unchanged — 12 passed).
- New `backend/tests/test_alert_pipeline.py` — 7 tests: speed pass skips judge (spy raises if called), hybrid match invokes judge, containment/exact/short-query/hybrid-miss unit cases, MatchResult backward compat.
- Full backend suite: 116 passed, 2 pre-existing failures (verified identical on pristine main), 18 skipped.

**Known behavioral delta (QA-flagged, blueprint-sanctioned):** BULLSEYE speed passes now update `best_opportunity_score` to 1.0 (Rule 6.3 compliance), which can suppress future Ring-tier matches that the old Stage-1 path would have allowed. Intended — the old skip was a latent bug.

---

## TECH-25: Alert & Notification Retention Lifecycle

**Status:** PENDING — ADR: `docs/adr/0001-alert-notification-retention.md`
**Date:** 2026-08-01

**The Friction (measured):**
- `suq_main_db`: 464 alerts, 100% inactive — the largest table in the DB (2.7 MB, dominated by 512-dim `query_vector` rows). Zero cleanup logic touches alerts or notifications.
- sqladmin hard-delete of alerts blocked by `notifications_alert_id_fkey` (RESTRICT) — test-data cleanup impossible via admin.
- Clutter is a retention lifecycle gap, not a delete-mechanism defect (soft deletes are load-bearing for dedup + match history + suppression).

**Acceptance Criteria:**
- `notifications.alert_id` → `ON DELETE CASCADE` via idempotent migration (drops `notifications_alert_id_fkey`, re-adds with cascade). sqladmin alert delete works.
- New `Alert.deleted_at` column (nullable) + migration; `DELETE /alerts/{alert_id}` sets it; pause/resume never touches it.
- Cleanup Phase 4 — alert purge: `(deleted_at < now - ALERT_RETENTION_DAYS) OR (expires_at < now - ALERT_RETENTION_DAYS)`. Default 30 days, env-configurable via `_get_config`; `<=0` disables (no purge).
- **Paused alerts are provably protected** (deleted_at NULL + future expires_at → never matches predicate).
- Cleanup Phase 5 — notification retention: purge `status IN ('SENT','FAILED','REPLACED')` older than `NOTIFICATION_RETENTION_DAYS` (default 90); **PENDING never purged**.
- No backfill of legacy dead rows (can't distinguish legacy paused vs deleted); one-time SQL cleanup documented for current test data.
- Tests: purge skips active + paused, purges deleted/expired, cascade removes notifications, PENDING survives, retention disabled at 0, full suite regression green. Atomic commit on QA approval.

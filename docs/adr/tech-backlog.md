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

**Status:** IMPLEMENTED ✅ — commit `f774c2c` on `feat/tech-25-retention` branch
**ADR:** `docs/adr/0001-alert-notification-retention.md`
**Blueprint:** `docs/plans/tech-25-blueprint.md`
**Date:** 2026-08-01
**QA:** APPROVED (10/10 criteria)

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

---

## TECH-26..TECH-31: Monetization (NB-43..NB-47)

**Status:** IMPLEMENTED ✅ — commits `22c3ea1`..`cb68aab` on `feat/monetization` (QA APPROVED)
**QA:** APPROVED (full audit: behavior-doc compliance 8/8, blueprint+seam correctness 7/7, module depth, tests, 11 deviations all accepted)
**Behavior doc:** `docs/behaviors/monetization.md` (all 9 sections locked)
**Date:** 2026-08-04

Six phases, each with its own QA gate + atomic commit on `feat/monetization`:

- **TECH-26 (Phase 1):** monetization constants (`BOOST_PRICE_STARS` via new `_get_json_config`, durations, prices, `MONETIZATION_ENABLED` kill switch), models (`Alert.lapsed`, `Boost`, `Subscription`), idempotent migrations, `services/telegram_payments.py` (StarPaymentsAdapter port + httpx adapter), `services/boost.py` core (quote/order/fulfill/rotation/lifecycle), partial `services/subscriptions.py` (cap math, credit stub), `tests/test_boost.py` + `FakeStarPaymentsAdapter`.
- **TECH-27 (Phase 2):** Stars payment seam — `GET /items/{id}/boost-quote`, `POST /items/{id}/boost-order`, `POST /items/{id}/boost-credit`, internal `api/routes/payments.py` (fulfill-boost with `total_amount`), search pin layer (`exclude_item_ids` additive + rotation order + `is_boosted`), listener `payments.py` + client additions + handler registration order, DM boost button (path-param deep link), frontend `useBoost.js` + ProductEditPanel boost section + ItemCard badge + App.jsx `/stores/:channelId/:itemId` route.
- **TECH-28 (Phase 3):** subscriptions — `create_subscription_order` (native 30-day XTR, `subscription_period=2592000` hard-locked), `fulfill_subscription_payment` (idempotent, renewals update same row), `handle_subscription_state_update` (PTB 22.8 api_kwargs seam), lapse mechanism (`Alert.lapsed` distinct from user pause), alert-cap unification (both call sites → `get_effective_alert_cap`), lapsed-resume guard.
- **TECH-29 (Phase 4):** seller intelligence — `services/stats.py` (views/alert-matches/dispatched core; price-positioning/category-pulse/top-performers pro), `GET /channels/{id}/stats`, `SellerIntelligenceDashboard.jsx` + ChannelInventory tab.
- **TECH-30 (Phase 5):** frontend subscriptions UI — `useSubscription.js`, StoresPage subscription card + upgrade entry, credit-boost button, end-to-end manual pass (quote → invoice → paid → badge; subscription → cap raised; cancel → extras paused `lapsed=True`; renewal → reactivated).
- **TECH-31 (Phase 6):** reconciliation (`getStarTransactions` replay, daily timer, `MONETIZATION_ENABLED` guard), full regression (baseline 116 passed / 2 pre-existing failures / 18-22 skipped), frontend build.

---

## TECH-32..TECH-37: Platform Ops Console (NB-49..NB-54)

**Status:** IMPLEMENTED ✅ — commits `93fe8c6`..`29a7376` on `feat/ops-console` (QA APPROVED)
**Date:** 2026-08-06

Six phases, each with QA gate + atomic commit on `feat/ops-console`:

- **TECH-32 (NB-49):** Shell — `/ops` route, admin auth in separate session namespace from sqladmin, role-bearing seam, one audit wrapper (`audit_log` table), settings registry (`admin_settings` KV + registry), ten-section scaffolding with "Coming soon" stubs, shared component kit.
- **TECH-33 (NB-50):** Section 1 Overview — service/bot/worker health via `/ops/health`, `scheduler_runs` table written by cleanup/reconciliation/photo-refresher, listener heartbeat, star balance + pending-payment count, 30s polling with age labels.
- **TECH-34 (NB-51):** Section 6 Monetization — `boost_prices` table (category/subcategory → Stars), DB-first price reads with cache + invalidation, seed from constants, demand-context pricing UI with bulk actions, instant feature toggles, subscription settings, revenue dashboard, boost moderation (end-early), test tools.
- **TECH-35 (NB-52):** Sections 8+9 — Settings & Flags (full registry surface, effective-config view, env-vs-db labeling) + Audit (read-only filtered list).
- **TECH-36 (NB-53):** Section 7 Payments — Star ledger, balance, reconciliation run-now, refund action with confirm+audit.
- **TECH-37 (NB-54):** Section 10 Support Toolkit — TEST boost/subscription grants, payment-webhook simulator (drives the real fulfillment path), deep-link generator.

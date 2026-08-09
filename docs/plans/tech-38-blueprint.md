**Date:** 2026-08-08
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture

# TECH-38 — Registry-Driven Cap/Credit/Allowance Accounting

## 1. Architecture Context

### The friction (write-only knobs)

Three ops-editable registry keys (`max_alerts_per_user`, `alerts_subscription_extra_alerts`, `all_in_one_monthly_boost_credit`) are **write-only**: the ops console PUTs them into `admin_settings`, but every product-logic consumer reads the constants from `constants.py`. Ops admins set a value, see no effect — the same bug class the price-propagation fix (ffef58f) just closed for prices, now pinned as a QA condition in `docs/adr/tech-backlog.md` (TECH-38, L91-97). A fourth lie is frontend-presentation: `MonetizationHub.jsx` hardcodes "2 free boosts" in its Boost-tab cross-sell while the same page renders `credit_total` from the API.

### Files involved

| File | Role |
|---|---|
| `backend/services/subscriptions.py` (328 lines) | THE module: cap math, credit accounting, lapse mechanism, status payload. The single cap authority (D3). All 10 constant read-sites live here. |
| `backend/services/settings_registry.py` (197 lines) | The registry: `get_setting` fail-open DB→env→constant chain. All three keys already registered (L43-45, L85-87, L88-90). **No change.** |
| `frontend/src/pages/MonetizationHub.jsx` (439 lines) | Presentation adapter — L211 hardcoded literal inside `BoostTab` (which already receives `status`). |
| `backend/tests/test_subscriptions.py` (725 lines) | `TestRegistryDrivenPrices` (L679-725) — the pattern to mirror. |
| `backend/tests/test_ops_monetization.py` (557 lines) | `TestOpsPriceLoop` (L273-308) — the PUT→effect loop pattern to mirror. |
| `backend/tests/test_alert_cap_regression.py` (310 lines) | Behavior-pin tests — must stay green UNCHANGED. |
| `frontend/src/__tests__/MonetizationHub.test.jsx` (380 lines) | L363-367 pins `/2 free boosts/i` — must be updated to assert API-driven number. |

### The pattern being extended

The price-propagation fix (ffef58f, commented at subscriptions.py L38-42) introduced exactly this pattern: `create_subscription_order` (L152-156) and `get_subscription_status` (L306-307, L324-325) read `get_setting(db, "…_price_stars")`. TECH-38 extends the same seam to the cap/allowance/credit keys. Graphify confirms `subscriptions.py` is already the deep central node (community 41; edges to `alerting.py`, `api/routes/alerts.py`, `boost.py`, `api/routes/ops_tools.py`, `stats.py`) — **no file split; this is a localized consumer switch plus a frontend adapter fix.**

### Dependency categories (per skill taxonomy)

- **Local-substitutable:** the three registry reads inside `subscriptions.py`. `get_setting` is already imported (L42); the fail-open fallback chain IS the substitutability — with no DB row, the constant default is returned, so behavior is byte-identical.
- **Frontend presentation adapter:** `MonetizationHub.jsx` — a consumer of the API payload; the copy change is a presentation-layer alignment, no new API surface.

## 2. The New Interfaces

### 2.1 `get_effective_alert_cap(db, user) -> int` — registry-driven (NO signature change)

**Verified:** the function already takes `db: Session, user: User` (L68). No caller change needed. All call sites already pass a session:
- `backend/services/alerting.py:288`
- `backend/api/routes/alerts.py:34`
- internal: `subscriptions.py:304` (status free branch), `:322` (status subscribed branch)
- tests: `test_alert_cap_regression.py:103,163`; `test_subscriptions.py:88,93,100,108,113`

**New implementation (descriptive):**
- Read `free_cap = get_setting(db, "max_alerts_per_user")` once.
- If an active subscription exists, additionally read `extra = get_setting(db, "alerts_subscription_extra_alerts")` and return `free_cap + extra`; otherwise return `free_cap`.
- Invariant: with no DB rows both reads fail open to `MAX_ALERTS_PER_USER` (20) and `ALERTS_SUBSCRIPTION_EXTRA_ALERTS` (10) → byte-identical output.

### 2.2 `get_credit_boosts_remaining(db, user) -> int` — registry-driven (no signature change)

**New implementation:** replace `ALL_IN_ONE_MONTHLY_BOOST_CREDIT - used` (L92) with `get_setting(db, "all_in_one_monthly_boost_credit") - used`. The 0-without-all-in-one guard, the period-window count query (L84-91), and the `max(0, …)` clamp are untouched.

### 2.3 `lapse_benefits(db, user) -> None` — registry-driven free cap (L106)

**Verified read-site (the architect's "CHECK" — confirmed):** the slice `active_alerts[MAX_ALERTS_PER_USER:]` (L106) deactivates alerts beyond the **free** cap. If the cap grows via the registry but lapse still slices against the constant, lapse under-slices. **Switch** the slice bound to `free_cap = get_setting(db, "max_alerts_per_user")` (read once at the top of the function). Docstring L97-99 ("deactivate alerts BEYOND the free cap") stays true.

### 2.4 `reactivate_lapsed_alerts(db, user) -> None` — NO direct change

**Verified:** it does not reference any of the three constants; it caps via `get_effective_alert_cap(db, user)` (L117) and becomes registry-driven transitively through §2.1. Do not touch.

### 2.5 `get_subscription_status(db, user) -> dict` — all six payload reads registry-driven

Replace, in both branches:
- L300 (free branch) `alerts_extra_allowance` → `get_setting(db, "alerts_subscription_extra_alerts")`
- L303 (free branch) `free_cap` → `get_setting(db, "max_alerts_per_user")`
- L315 (subscribed branch) `extra_alerts` → `get_setting(db, "alerts_subscription_extra_alerts")`
- L316 (subscribed branch) `alerts_extra_allowance` → `get_setting(db, "alerts_subscription_extra_alerts")`
- L319 (subscribed branch) `credit_total` → `get_setting(db, "all_in_one_monthly_boost_credit") if sub.product == "all_in_one" else 0`
- L321 (subscribed branch) `free_cap` → `get_setting(db, "max_alerts_per_user")`

Prefer reading each key once per branch into a local and reusing it (two `get_setting` calls per function invocation at most, matching the existing price reads at L306-307).

### 2.6 The frontend copy (MonetizationHub.jsx L211) — API-driven

**Exact current text (L210-212):**
```jsx
{/* Cross-sell (Rule 10.2.7) */}
<p className="mt-4 text-xs text-gray-500">
  All-in-One includes 2 free boosts every period plus seller intelligence.
</p>
```
**Verified context:** this block is inside `BoostTab` (declared L64), which receives `status` as a prop. The page blocks on loading (L359-365) and renders the unavailable screen when `status` is null (L368-387), so `status.credit_total` is **always defined** when `BoostTab` renders — no fallback needed (the architect's conditional fallback concern does not apply).

**New copy:** `All-in-One includes {status.credit_total} free boosts every period plus seller intelligence.` — identical sentence structure, number now from the payload. This matches the AllInOneTab precedent at L271 (`{status.credit_total} free boosts every period`).

### 2.7 Invariants (behavior preservation)

1. No DB rows → `get_setting` fails open to the constants → every existing test passes unchanged, most critically `test_alert_cap_regression.py` (20/21/30/31 boundaries, route + service call sites) and the credit tests (`test_subscriptions.py` L277-320).
2. `get_subscription_status` payload keys are unchanged in name, type, and shape — only the value source changes.
3. No schema change, no migration, no new routes. Ops PUTs (`/ops/monetization/settings/{key}` for the two allowance/credit keys; `/ops/settings/{key}` for `max_alerts_per_user` — verified: `max_alerts_per_user` is NOT in the monetization settings surface, test_ops_monetization.py L255-258 pins exactly four keys) take effect on the next consumer read — `get_setting` is a live `db.get` per call, no cache.

## 3. Strict Import Map (per file)

### `backend/services/subscriptions.py`
- **Already present, keep:** `from services.settings_registry import get_setting` (L42 — added by the price fix; verified cycle-free: `settings_registry.py` imports only `models`, `constants`, `sqlalchemy` — its own docstring L11 and graph confirm no back-edge).
- **Remove (additive rule with justification):** the three names `ALL_IN_ONE_MONTHLY_BOOST_CREDIT`, `ALERTS_SUBSCRIPTION_EXTRA_ALERTS`, `MAX_ALERTS_PER_USER` from the `from constants import (...)` block (L23-26). Justification: after §2.1-2.5 every reference is gone; keeping them would be dead imports. **Keep** `SUBSCRIPTION_PERIOD_SECONDS` (used L165), `ALERT_CAP_BANNER_THRESHOLD` (used L305/323 — registry-keyed but out of TECH-38 scope), `BOOST_DURATION_DAYS` (used L309/327).
- No other imports change. No other module imports these constants from subscriptions.py (grep-verified: `alerting.py:14` and `api/routes/alerts.py:14` import `MAX_ALERTS_PER_USER` **from `constants`**, not from subscriptions — see Rollout Notes).
- `from services.boost_pricing import get_boost_floor` (L37) and `from services.telegram_payments import star_payments` (L43) untouched.

### `backend/services/settings_registry.py`
- **No change** (registry entries for all three keys already exist).

### `backend/services/alerting.py` / `backend/api/routes/alerts.py`
- **No change.** Both already call `get_effective_alert_cap(db, user)` with a session (alerting.py:288, alerts.py:34). Their unused `MAX_ALERTS_PER_USER` imports (alerting.py:14, alerts.py:14) are pre-existing dead imports — leave them (out of TECH-38 scope; see Rollout Notes).

### `frontend/src/pages/MonetizationHub.jsx`
- **No import changes.** `status` is already in `BoostTab`'s prop scope; `credit_total` is a payload field, no new dependency.

### `backend/tests/` and `frontend/src/__tests__/`
- Additive only. New tests import `set_setting` (local import inside tests, mirroring `TestRegistryDrivenPrices` L681: `from services.settings_registry import set_setting`) and the existing `_monetization_client`/`_web_client` helpers from `test_ops_monetization.py` (module-local, L280-287). Constants continue to be imported in tests for the no-row expectations.

## 4. Execution Steps

1. **Enumerate (verify, don't re-discover):** open `backend/services/subscriptions.py` and confirm the 10 read-sites at L71, L72, L92, L106, L300, L303, L315, L316, L319, L321 (complete list; three sites — 316, 319, 321 — were absent from the audit's 5-8). Grep the file for the three constant names; every hit must be a registry read or the import block.
2. **Switch `get_effective_alert_cap`** (L68-72): replace both constant reads per §2.1. Do not change the signature; do not change the subscription-active branch structure.
3. **Switch `get_credit_boosts_remaining`** (L92) per §2.2.
4. **Switch `lapse_benefits`** (L106) per §2.3 — read `max_alerts_per_user` once before the loop; slice bound uses the local.
5. **Leave `reactivate_lapsed_alerts`** (L112-133) untouched (§2.4).
6. **Switch `get_subscription_status`** (L300, L303, L315, L316, L319, L321) per §2.5 — both branches; payload key names/order unchanged.
7. **Trim the constants import block** in `subscriptions.py` per §3 (remove the three names, keep the rest).
8. **Frontend:** in `frontend/src/pages/MonetizationHub.jsx` replace the L211 literal with the `status.credit_total` interpolation per §2.6. Verify the sentence still reads naturally ("All-in-One includes N free boosts every period plus seller intelligence.").
9. **Backend tests — `backend/tests/test_subscriptions.py`:** add a new class `TestRegistryDrivenCapAndCredit` directly after `TestRegistryDrivenPrices` (L679-725), mirroring its style (module-level `set_setting` import inside the tests):
   - Free cap follows the row: `set_setting(db, "max_alerts_per_user", "30")` → `get_effective_alert_cap` == 30 with no subscription.
   - Subscribed cap follows both rows: `max_alerts_per_user=30`, `alerts_subscription_extra_alerts=15`, active sub → cap == 45.
   - Credit follows the row: `all_in_one_monthly_boost_credit=5` + active `all_in_one` sub → `get_credit_boosts_remaining` == 5; after one credit-source `Boost` row (reuse the `_make_channel_item` + Boost-insert pattern from L283-297) → 4.
   - Status payload reflects rows on the free branch (`free_cap`, `alerts_extra_allowance`) and the subscribed branch (`free_cap`, `extra_alerts`, `alerts_extra_allowance`, `credit_total`, `effective_cap`).
   - Lapse slices at the registry free cap: `max_alerts_per_user=3`, seed 6 active alerts → `lapse_benefits` leaves exactly 3 active, 3 lapsed (mirror `TestLapseBenefits.test_lapse_pauses_alerts_beyond_free_cap_oldest_first`).
   - Reactivation bound: `max_alerts_per_user=2`, `alerts_subscription_extra_alerts=2`, active sub → `reactivate_lapsed_alerts` fills to effective cap 4 (mirror `TestReactivateLapsedAlerts.test_renewal_reactivates_lapsed_oldest_first_up_to_cap`).
   - No-row regression is already pinned by every pre-existing test in the file — do not duplicate.
10. **Backend tests — `backend/tests/test_ops_monetization.py`:** extend `TestOpsPriceLoop` (or add `TestOpsCapCreditLoop` alongside, reusing its `_web_client` at L280-287) with the full PUT→effect loop:
    - PUT `/ops/monetization/settings/alerts_subscription_extra_alerts` = "15" → GET `/subscriptions/status` (with an active `alerts_only` sub for the user) → `extra_alerts` == 15 and `effective_cap` == 20+15.
    - PUT `/ops/monetization/settings/all_in_one_monthly_boost_credit` = "5" → status `credit_total` == 5 (active `all_in_one` sub).
    - PUT `/ops/settings/max_alerts_per_user` = "30" (Section 8 route — build a `_settings_client` from `api.routes.ops_settings` with the same override pattern) → status `free_cap` == 30, and service-level `get_effective_alert_cap(db, user)` == 30 immediately.
11. **Frontend tests — `frontend/src/__tests__/MonetizationHub.test.jsx`:** update the cross-sell test (L363-367): set `mockStatus = { ...defaultStatus, credit_total: 5 }`, render `/hub/boost`, assert the page shows "5 free boosts" (proving the number comes from the mocked payload, not a literal). Keep the AllInOneTab counter test (L314-320, asserts `/1\/2/`). The remaining tests are unaffected.
12. **Verification gate:** run the full backend suite — `backend/tests/test_alert_cap_regression.py` must pass **unchanged** (behavior-preservation gate), as must all of `test_subscriptions.py`, `test_ops_monetization.py`, `test_ops_settings.py`, `test_boost.py`, `test_alert_pipeline.py`. Run the frontend suite (`frontend` package manager test runner) — all MonetizationHub, StoresPage, and AlertsPage tests green.
13. **Atomic commit** (only after QA review, per AGENTS.md §3 — feature branch, no intermediate commits): `feat: registry-driven alert cap, allowance & boost credit (TECH-38)`.

## 5. Testing Strategy

- **Behavior-preservation gate (hard):** `backend/tests/test_alert_cap_regression.py` — 20/21/30/31 boundary tests at BOTH call sites (service L78-129, route L132-172) plus the lapsed-resume guard — must pass with zero modification. They create no registry rows, so fail-open guarantees constant defaults.
- **Registry-driven unit tests** (`test_subscriptions.py`): rows win at every consumer — cap math (free + subscribed), credit math (full, after use, zero for non-all-in-one), status payload fields on both branches, lapse slice, reactivation bound.
- **Ops-PUT loop tests** (`test_ops_monetization.py`): the write-only lie is dead — each PUT surfaces in the webapp-facing payload immediately (cap, allowance, credit), mirroring `TestOpsPriceLoop.test_ops_price_put_reaches_subscription_status_immediately`.
- **Frontend test:** the rendered boost count is asserted against a mocked `credit_total` ≠ 2, proving the literal is gone.
- Negative space: no registry row + env unset → constants (existing suite); corrupt row values → `get_setting` falls through to env/constant (covered by `test_settings_registry.py`, unchanged).

## 6. Rollout Notes

- **No schema change, no migration** — `admin_settings` and all three registry keys already exist (settings_registry.py L43-45, L85-90). Deploy is a pure code swap.
- **Instant effect:** `get_setting` performs a live `db.get` per read with no cache — an ops edit is visible on the next alert-creation cap check, credit redemption, or status fetch. No restart.
- **Out-of-scope observations (flag to architect, do NOT implement in this ticket):**
  - `ALERT_CAP_BANNER_THRESHOLD` is registry-keyed (`alert_cap_banner_threshold`) but still read from the constant at subscriptions.py L305/323 — the same write-only class, not among TECH-38's three keys.
  - Pre-existing dead imports of `MAX_ALERTS_PER_USER` in `services/alerting.py:14` and `api/routes/alerts.py:14` (unused; left alone).
  - `StoresPage.jsx:266` copy "All-in-One includes free boosts" carries no number — not a lie, no change.
  - `max_alerts_per_user` is edited from the Section 8 Settings route (`/ops/settings/{key}`), not the Section 6 monetization settings surface — tests must target the right route.

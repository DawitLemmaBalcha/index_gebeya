# Blueprint: Platform Ops Console (TECH-32..TECH-37 / NB-49..NB-54)

**Date:** 2026-08-06
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture
**Authority:** `docs/behaviors/ops-console.md` (locked 2026-08-06), `docs/behaviors/pending-behaviors.md` (NB-49..NB-54), `docs/adr/tech-backlog.md` (TECH-32..37), `docs/behaviors/monetization.md` (Rules 1.3/2.2/2.3 amended)
**Branch:** `feat/ops-console` (six atomic commits, one per phase, each QA-gated)

---

## 0. Verification & Drift Notes (read first — every claim below was verified against HEAD `95448ee` on `main`)

| # | Claimed in design | Verified current state | Drift / decision |
|---|---|---|---|
| D1 | sqladmin session uses its own key | `backend/admin.py:18-36` — `AdminAuth` sets `request.session["token"] = "authenticated"`. **Verified deeper:** sqladmin mounts a *separate Starlette sub-app* (`sqladmin/application.py:104-109` — `self.admin = Starlette(middleware=middlewares)`; mounted at `/admin`), so sqladmin's `SessionMiddleware` lives on the sub-app with cookie **`session`**, secret `ADMIN_SECRET_KEY`, session key `token`. The **parent FastAPI app has NO SessionMiddleware today** (`backend/main.py` — none added). | The ops console must add its **own `SessionMiddleware` to the parent app** with `session_cookie="ops_session"` and session key `"ops_admin"`. This is a cookie-level namespace separation — stronger than key-only, and the only workable one given sqladmin's sub-app isolation. |
| D2 | `/search` route reads `MONETIZATION_ENABLED` | **It does not.** `grep MONETIZATION_ENABLED` hits: `constants.py:139`, `main.py:431/436`, `api/routes/payments.py:18/32`, `api/routes/channels.py:20/30`, `api/routes/items.py:24/39`, `api/routes/subscriptions.py:12/30`, `services/boost.py:25/99/194`, `listener/payments.py:30/49/85`. `search.py` is absent. | Nothing to switch in `search.py` (paid placements remain visible after a kill — correct: existing paid boosts must not vanish). Phase 3 switches the six modules above, plus the `main.py:431-436` reconcile scheduler guard (read the registry *inside* the daily closure for instant effect). |
| D3 | `Boost.source` column constrained | `models.py:305` — `source = Column(String, nullable=False, default="paid")` — **free string, unconstrained**. `get_credit_boosts_remaining` counts only `source == "credit"` (`subscriptions.py:83`). Placement never filters on source. | `source='test'` works with zero schema change; test boosts never consume credit. |
| D4 | `refund_star_payment` exists in the adapter | **Not present.** Protocol (`telegram_payments.py:27-60`) has `create_invoice_link`, `edit_user_star_subscription`, `get_star_transactions`, `get_my_star_balance`. httpx impl (`:106-151`) matches. Fake (`tests/fake_telegram_payments.py`) matches. | **ADD** `refund_star_payment(*, telegram_payment_charge_id: str) -> bool` to the Protocol + `HttpxStarPaymentsAdapter` (POST `/bot{token}/refundStarPayment`) + `FakeStarPaymentsAdapter` (records call, returns True). |
| D5 | Reconcile function signature | `reconciliation.py:75` — `async def reconcile_star_payments(db: Session, *, limit: int = 100) -> dict` returning `{fetched, replayed_boost, replayed_subscription, skipped, errors}`. Async; `main.py:440` wraps in `asyncio.run()`. | Run-now uses `asyncio.run(reconcile_star_payments(db))` (same session from `get_db`). `SchedulerRun` gains an **additive `last_result` JSON column** so "run + result" is displayable. |
| D6 | Taxonomy source for seeding | `backend/ai_engine/prompts.py:4-59` — `TAXONOMY_STRUCTURE`, **18 top-level keys, 95 subcategory entries**, includes `"Other": ["Mixed", "Uncategorized"]`. Byte-identical structure to `frontend/src/constants/taxonomy.js`. `BOOST_PRICE_STARS` (`constants.py:115-134`) has exactly the same 18 keys. | Seed from **backend source** `ai_engine.prompts.TAXONOMY_STRUCTURE` (as directed). ~95 rows. |
| D7 | Caddy routing for `/ops` (design silent) | `deploy/Caddyfile` routes `/search*`, `/items*`, `/reviews*`, `/alerts*`, `/notifications*`, `/activity*`, `/feed*`, `/parse-telegram-post*`, `/media*`, `/admin*`, `/channels*`, `/subscriptions*` → API; **everything else → SPA**. `/ops*` currently lands on the SPA. Header: host copy at `/home/ubuntu/caddy/Caddyfile` must be kept in sync. | **Add explicit Caddy handles** for each ops API prefix (see Phase 1 step 12). The `/ops` page itself continues through the SPA catch-all. Endpoint paths stay exactly as locked in the design. |
| D8 | `/ops` route in the React app | `App.jsx:102-104` — non-Telegram visitors get `<LandingPage />` unconditionally, *before* the Router is mounted. | `/ops` needs a `window.location.pathname` guard **before** the Telegram gate (Phase 1 step 13). |
| D9 | Listener writes `scheduler_runs` for photo refresher | The listener has **no DB access** (HTTP-only; `listener/config.py:17` `API_BASE`). | photo_refresher's last-run/last-success/last-error ride the **new heartbeat payload** (listener `stats.py` module state → `POST /internal/heartbeat`); `/ops/health` derives the `photo_refresher` scheduler row from it, source-labeled. |
| D10 | Registry env names | Verified exact constants: `ALERT_MAX_PER_USER` 20, `ALERT_MAX_MATCHES` 10, `ALERT_MAX_BULLSEYE` 3, `ALERT_THROTTLE_SECONDS` 3600, `ALERT_LIFESPAN_DAYS` 14, `ALERT_RETENTION_DAYS` 30, `NOTIFICATION_RETENTION_DAYS` 90, `SOFT_DELETED_RETENTION_DAYS` 30, `REPORTED_SOLD_RETENTION_DAYS` 7, `STALE_ITEM_DAYS` 14, `BOOST_ROTATION_MINUTES` 30, `BOOST_DURATION_DAYS` 7, `ALERTS_ONLY_PRICE_STARS` 30, `ALL_IN_ONE_PRICE_STARS` 100, `ALERTS_SUBSCRIPTION_EXTRA_ALERTS` 10, `ALL_IN_ONE_MONTHLY_BOOST_CREDIT` 2, `ALERT_CAP_BANNER_THRESHOLD` 2, `MONETIZATION_ENABLED` 1. | Registry table in §2.3 maps every knob to its exact constant. |
| D11 | Existing kill-switch tests | `test_boost.py:241` (`services.boost.MONETIZATION_ENABLED`), `test_boost.py:1001` (`api.routes.channels.MONETIZATION_ENABLED`), `test_payments_flow.py:156` (`api.routes.payments.MONETIZATION_ENABLED`), `test_payments_flow.py:250` (`api.routes.items.MONETIZATION_ENABLED`) monkeypatch module-level constants. | **Phase 3 must migrate these 4 monkeypatch sites** to registry control (set a DB row / monkeypatch `settings_registry.get_setting`). `TestGetBoostPrice` (`test_boost.py:146-158`) stays green — constant fallback for unseeded rows is preserved. |
| D12 | Subscription floor mirrors boost price | `subscriptions.py:281-286` — `boost_floor = BOOST_PRICE_STARS.get("Other", ...)` — must never import `services.boost` (cycle: `boost.py:28` imports `services.subscriptions`). | New module `services/boost_pricing.py` (imports `models` + `constants` only) hosts the DB-first price table + cache + floor; `boost.py` re-exports `get_boost_price` (import surface unchanged for `items.py:17`); `subscriptions.py` imports the floor from `boost_pricing`. Cycle-free. |
| D13 | Frontend API base | `frontend/src/config.js` — `API_BASE_URL = ""` (same-origin relative). Production: Caddy. | Ops fetches are same-origin → cookies flow; CORS `allow_credentials=False` (`main.py:39-45`) is irrelevant. |
| D14 | `get_boost_price` callers | `items.py:333` (quote), `boost.py:103` (order). `fulfill_boost` uses `total_amount` at fulfillment (`boost.py:177`) — invoice fixed at creation, in-flight stability holds by construction. | Change transparent to all callers. |

---

## 1. Architecture Context

**The friction.** Every platform operation today is: env var → restart container → raw sqladmin row-edit. Monetization prices require `BOOST_PRICE_STARS` env edits; feature kill switches require `MONETIZATION_ENABLED` env edits across *two* containers (api + listener); health questions require log archaeology; test data requires sqladmin row-inserts. The console converts all of this into one audited, session-authenticated, action-oriented surface.

**The shell-first principle.** The shell (TECH-32) is the product: one `/ops` page, left-rail nav with all ten sections, ten stubs, a shared component kit, one audit wrapper, one settings model, one auth seam. Sections slot into the shell; the shell never changes shape. Build order is locked: Shell → Overview → Monetization → Settings+Audit → Payments → Support Toolkit. Sections 2–5 (Catalog, Trust & Moderation, Users, Alerts & Notifications) remain stubs — action centers only, never row-editing (Rule 2.1).

**Dependency categories (skill vocabulary).**
- *Local-substitutable:* every new backend table (`audit_log`, `admin_settings`, `boost_prices`, `scheduler_runs`, `listener_heartbeat`) and the services over them — tested against the existing isolated `suq_test_db` via the house `db_session` fixture (`tests/conftest.py:58-68`). No ports needed; the DB is the stand-in.
- *Remote-but-owned / True external (existing real seam):* `services.telegram_payments.StarPaymentsAdapter` already has **two adapters** (`HttpxStarPaymentsAdapter` production, `FakeStarPaymentsAdapter` tests) — a real seam. The console **reuses** it for balance/ledger/refund (adding `refund_star_payment` to port + both adapters). The ops modules never import PTB or touch Telegram directly.
- *Remote-but-owned (new seam):* the **listener heartbeat** — a port at the listener→backend seam: JSON payload over the existing `INTERNAL_HEADERS` wire (`listener/client.py:5`), one internal endpoint, one table. Production adapter = httpx function in `client.py`; test = the endpoint itself via `TestClient`.
- *Frontend presentation adapters:* each `Ops*` section is a thin fetch adapter over the ops API; tested with vitest + testing-library and mocked fetch. No shared store, no router sub-routes (tabs are state-based) — locality kept in one shell component.

**Deletion test applied to the planned modules:** `record_audit` — delete it and the audit discipline reappears across 12 mutation routes; it earns its keep. `settings_registry` — delete it and env-vs-DB precedence logic reappears in every route; it earns its keep. `boost_pricing` — delete it and the cache/fallback logic reappears in `boost.py` + `subscriptions.py`; it earns its keep. `scheduler_runs` — delete it and the last-run/error state reappears in three jobs' logs; it earns its keep.

---

## 2. The New Interfaces

### 2.1 Table additions — `backend/models.py` (all following the house Column style; `from sqlalchemy import JSON` added to the line-1 import)

| Table | Columns | Invariants |
|---|---|---|
| `AuditLog` (`audit_log`) | `id` (Integer PK, index), `admin_user` (String, NOT NULL), `action` (String, NOT NULL), `section` (String, NOT NULL), `entity_type` (String, NOT NULL), `entity_id` (String, nullable), `before` (JSON, nullable), `after` (JSON, nullable), `created_at` (DateTime tz, server_default func.now()) | **Rows are never deleted.** No delete route exists anywhere. |
| `AdminSetting` (`admin_settings`) | `key` (String PK), `value` (String, nullable), `type` (String: `int\|float\|str\|bool\|json`), `source` (String: `'db'\|'env'`), `description` (String) | One row per key; row presence ⇒ source `'db'`. |
| `BoostPrice` (`boost_prices`) | `category` (String, PK part), `subcategory` (String, PK part), `price_stars` (Integer, NOT NULL), `updated_at` (DateTime tz, server_default func.now(), onupdate func.now()), `updated_by` (String, nullable) | Composite PK `(category, subcategory)`; price ≥ 1 (route-validated). |
| `SchedulerRun` (`scheduler_runs`) | `id` (Integer PK), `scheduler` (String, UNIQUE, index), `last_run_at` (DateTime tz, nullable), `last_success_at` (DateTime tz, nullable), `last_error` (String, nullable), `last_result` (JSON, nullable — **additive, D5**) | One row per scheduler name, upserted. |
| `ListenerHeartbeat` (`listener_heartbeat`) | `id` (Integer PK, fixed 1), `last_seen_at` (DateTime tz, NOT NULL), `payload` (JSON, nullable) | Single row, id=1, upserted. |

### 2.2 `backend/services/audit.py` — the single mutation path

```
record_audit(db, *, admin_user: str, action: str, section: str,
             entity_type: str, entity_id: str | None = None,
             before: dict | None = None, after: dict | None = None) -> AuditLog
```
- Adds one `AuditLog` row and **commits** (independent of the mutation's own transaction — a failed mutation produces no audit row; an applied one always does).
- The `admin_user` argument is populated by ops routes from the session (`session["ops_admin"]["user"]`).
- Invariant: **every console mutation route calls this helper; no console route writes a row in any table without it.** Errors: none raised (defensive try/except logs and continues? **No** — raise; audit failure must fail the mutation so the console never mutates silently. Spec: let DB errors propagate).

### 2.3 `backend/services/settings_registry.py` — the settings model

```
get_setting(db, key, *, env_default=None, cast=None) -> value
set_setting(db, key, value, *, cast=None) -> AdminSetting        # upsert, source='db', no audit (routes audit)
list_settings() -> list[dict]                                     # [{key, type, value: live, source, description}]
```
- **The registry table** (key, env var, type, live default — all verified, D10):

| key | env var | type | default |
|---|---|---|---|
| `monetization_enabled` | `MONETIZATION_ENABLED` | bool | `True` (env int 1) |
| `boost_purchases_enabled` | — | bool | `True` |
| `subscription_purchases_enabled` | — | bool | `True` |
| `credit_boosts_enabled` | — | bool | `True` |
| `max_alerts_per_user` | `ALERT_MAX_PER_USER` | int | 20 |
| `alert_cap_banner_threshold` | `ALERT_CAP_BANNER_THRESHOLD` | int | 2 |
| `alert_max_matches` | `ALERT_MAX_MATCHES` | int | 10 |
| `alert_max_bullseye` | `ALERT_MAX_BULLSEYE` | int | 3 |
| `notification_throttle_seconds` | `ALERT_THROTTLE_SECONDS` | int | 3600 |
| `alert_lifespan_days` | `ALERT_LIFESPAN_DAYS` | int | 14 |
| `boost_rotation_minutes` | `BOOST_ROTATION_MINUTES` | int | 30 |
| `alert_retention_days` | `ALERT_RETENTION_DAYS` | int | 30 |
| `notification_retention_days` | `NOTIFICATION_RETENTION_DAYS` | int | 90 |
| `soft_deleted_retention_days` | `SOFT_DELETED_RETENTION_DAYS` | int | 30 |
| `reported_sold_retention_days` | `REPORTED_SOLD_RETENTION_DAYS` | int | 7 |
| `stale_item_days` | `STALE_ITEM_DAYS` | int | 14 |
| `alerts_only_price_stars` | `ALERTS_ONLY_PRICE_STARS` | int | 30 |
| `all_in_one_price_stars` | `ALL_IN_ONE_PRICE_STARS` | int | 100 |
| `alerts_subscription_extra_alerts` | `ALERTS_SUBSCRIPTION_EXTRA_ALERTS` | int | 10 |
| `all_in_one_monthly_boost_credit` | `ALL_IN_ONE_MONTHLY_BOOST_CREDIT` | int | 2 |

- Resolution: DB row value if present (source `'db'`, cast per `type`) → else env var if set (source `'env'`) → else the constant default. `cast`/`env_default` params are the escape hatch for ad-hoc keys; registered keys resolve them from the table.
- Reads are **fail-open**: if the table is missing (migration failure), catch the SQL error and return the env default — the platform never crashes on a console regression (see §6).
- `set_setting` stores the raw string in `value`; casts validate before write (ValueError → HTTPException 400 at the route).

### 2.4 `backend/services/boost_pricing.py` — DB-first prices (new, cycle-free)

```
get_boost_price(db, item) -> int                      # the interface boost.py re-exports
get_boost_price_by_key(db, category, subcategory) -> int
get_boost_floor(db) -> int                            # 'Other' row, else constant floor 25 — subscriptions.py's new source
set_boost_price(db, *, category, subcategory, price_stars, updated_by) -> BoostPrice
set_boost_price_bulk(db, *, category, subcategory, price_stars, updated_by) -> None   # used by bulk ops
invalidate_boost_price_cache() -> None
seed_boost_prices(db) -> int                          # idempotent startup seed, returns inserted count
```
- **Fallback chain (Rule 4.1.2):** DB row `(item.category, item.subcategory)` → DB row `(item.category, "")`-style category row (spec: a row with `subcategory` equal to the category name is *not* created; the category fallback is the **category row stored under `subcategory='*'`? No** — simplest honest model: seed one row per (category, subcategory) from taxonomy, plus the lookup falls back `(category, subcategory)` → first row where `category` matches **and** subcategory is the item's `None`/empty OR the item's subcategory missing → then constant chain `BOOST_PRICE_STARS[category]` → `BOOST_PRICE_STARS["Other"]` → 25. Exact spec: `(category, subcategory)` → `(category, None)` row if the item has no subcategory → `("Other", sub)`/constant `Other` floor → 25. Implement as: DB row `(category, subcategory)`; if item.subcategory falsy, DB row `(category, "")` seeded for every category with `price_stars = BOOST_PRICE_STARS[category]`; else the **constant fallback** `BOOST_PRICE_STARS.get(category, floor)` for unseeded rows (defensive, D12) → constant floor.
  - **Concrete seeded rows:** for each `(category, subs)` in `TAXONOMY_STRUCTURE`: one row per sub with `price_stars = BOOST_PRICE_STARS.get(category, 25)`; plus one `(category, "")` row per category (the category-level fallback) with the same price. 95 + 18 = 113 rows, all `INSERT ... ON CONFLICT DO NOTHING`.
- **Cache:** module-level dict `{(category, subcategory): int}` + per-entry timestamp; reads younger than **60s TTL** are served from cache; `set_boost_price`/bulk deletes the touched keys (bulk clears all); TTL covers multi-worker drift.
- `seed_boost_prices` is called from `main.py` startup (new Phase 5.7 block) — idempotent on existing DBs.

### 2.5 `backend/services/scheduler_runs.py`

```
record_scheduler_run(db, *, scheduler: str, success: bool, error: str | None = None,
                     result: dict | None = None) -> None
```
- Upsert on `scheduler`; sets `last_run_at` (always), `last_success_at` (on success), `last_error` (on failure), `last_result` (JSON, when provided). Commits.

### 2.6 `backend/api/routes/ops_auth.py` — the auth seam (Phase 1)

- `POST /ops/auth/login` `{username, password}` — compares against `os.getenv("ADMIN_USERNAME", "admin")` / `os.getenv("ADMIN_PASSWORD", "indexgebeya")` (same env source as sqladmin, `admin.py:23-24`). On match: `request.session["ops_admin"] = {"user": username, "role": "admin"}` → 200 `{user, role}`. Wrong creds → 401 `{"detail": "Invalid credentials"}`.
- `POST /ops/auth/logout` — `request.session.pop("ops_admin", None)` (never `clear()` — must not wipe any other key) → 200.
- `GET /ops/auth/me` — 200 `{user, role}` when authenticated, else 401.
- `has_role(request, role: str) -> bool` — reads `request.session.get("ops_admin", {}).get("role") == role`. The permission check of the future: roles are data, not code.
- `require_ops_admin` — FastAPI dependency: `has_role(request, "admin")` else 401 `{"detail": "Not authenticated"}`.
- **Namespace invariant (D1):** this cookie (`ops_session`, key `ops_admin`) is never written by sqladmin and vice versa; a console login can never open `/admin` and a sqladmin login can never open `/ops/*`.

### 2.7 Listener heartbeat seam (Phase 2)

- **Listener side.** New `listener/stats.py`: module-level `stats = {"started_at": ts, "items_processed_total": 0, "last_update_at": None, "photo_refresher": {"last_run_at": None, "last_success_at": None, "last_error": None}}`. `listener/worker.py` increments `items_processed_total` and sets `last_update_at` after each successful ingest (`worker.py` result `success` branch). `listener/photo_refresher.py` sets the `photo_refresher` sub-keys at cycle end / on error. New `send_heartbeat(queue)` in `listener/client.py`: every 30s `POST {API_BASE}/internal/heartbeat` with `INTERNAL_HEADERS` and body `{"queue_depth": queue.qsize(), "items_processed_total": ..., "last_update_at": iso|None, "started_at": iso, "photo_refresher": {...}}`; failures logged, never fatal. `listener/main.py` `post_init` spawns `asyncio.create_task(send_heartbeat(job_queue))`.
- **Backend side.** New `backend/api/routes/internal.py`: `POST /internal/heartbeat` — requires `X-Internal-Service: index-listener` (else 403); upserts `ListenerHeartbeat(id=1, last_seen_at=now, payload=body)`; returns 200. Registered with no prefix.
- No fake data: the heartbeat is the only listener signal; its absence = "down/unknown".

### 2.8 `backend/api/routes/ops_health.py` — Section 1 Overview (Phase 2, all ops-admin protected)

`GET /ops/health` → 200 always (per-signal statuses inside). Shape and honest per-signal sources:

| Signal | Source (verified) | Honest state |
|---|---|---|
| `services.api` | the endpoint itself responding | `up` |
| `services.db` | `SELECT 1` via `database.engine` | `up`/`down` |
| `services.frontend` | HTTP GET probe `http://frontend:5173/` (env `FRONTEND_PROBE_URL`, default as shown; 2.5s timeout) | `up`/`down`/`unavailable` |
| `services.listener` | `listener_heartbeat.last_seen_at` age | `< 90s up`, else `down`, no row `unknown` |
| `bot.connection` | heartbeat freshness (polling loop alive = connected) | derived from heartbeat; else `unknown` |
| `bot.update_lag_seconds` | `now - payload.last_update_at` | number / `null` |
| `bot.handler_error_rate` | **no data source** | `unavailable` |
| `ingestion.queue_depth` | `payload.queue_depth` | number / `null` |
| `ingestion.items_per_hour` | `items_processed_total / hours since started_at` (rate since start, labeled) | number / `null` |
| `ingestion.rate_limit_headroom` | **no data source** | `unavailable` |
| `ingestion.ai_providers` | **no health endpoint for groq/gemini** (`ai_engine/groq_client.py`, `gemini_client.py` are raw HTTP, no status tracking; NB-20 is the future surface) | `unavailable` with reason |
| `schedulers.cleanup` / `schedulers.reconciliation` | `scheduler_runs` rows | row / `never run` |
| `schedulers.photo_refresher` | `payload.photo_refresher` (D9) | row / `never run` |
| `money.star_balance` | `star_payments.get_my_star_balance()` (verified `telegram_payments.py:58,150`, fake `:53`) | number / `error` with message |
| `money.pending_payments` | **queryable honestly:** `get_star_transactions(limit=100)` → count of `source.transaction_type == "invoice_payment"` whose `id` is not in `boosts.telegram_payment_charge_id` nor `subscriptions.telegram_payment_charge_id` (reconciliation gap) | `{count, source: "star_transactions_vs_fulfillment"}` / `unavailable` |

Every signal object carries `{status, value?, source, note?}` and the response carries `generated_at` for the frontend's age labeling. Failures are per-signal; the endpoint never fabricates and never 500s the whole page.

### 2.9 `backend/api/routes/ops_monetization.py` — Section 6 (Phase 3, ops-admin protected)

- `GET /ops/monetization/prices` → `{generated_at, categories: [{category, rows: [{subcategory, price_stars, source, active_boosts, boosts_this_week}]}]}`. Demand context: `Boost` JOIN `Item`, grouped by `(Item.category, Item.subcategory)`: `active_boosts` = `ends_at > now`; `boosts_this_week` = `created_at >= now - 7d`. (Columns verified: `Boost.created_at/ends_at/item_id`, `Item.category/subcategory`.)
- `PUT /ops/monetization/prices/{category}/{subcategory}` `{price_stars}` → validate int 1..10000 → `set_boost_price` (cache invalidation inside) → audit (`section='monetization'`, `action='update_boost_price'`, `entity_type='boost_price'`, `entity_id=f"{category}/{subcategory}"`, `before={'price_stars': old}`, `after={'price_stars': new}`) → new row.
- `POST /ops/monetization/prices/bulk` `{action: "set_category"|"percent"|"reset", category, subcategory?, price_stars?, percent?}`:
  - `set_category`: every `(category, sub)` row → `price_stars` (clamp ≥ 1).
  - `percent`: every `(category, sub)` row × `(100 + percent)/100`, int-clamped ≥ 1.
  - `reset`: every `(category, sub)` row back to `BOOST_PRICE_STARS.get(category, 25)` ("reset to floor").
  - One audit row per category: `entity_id=category`, `before`/`after` = `{sub: price}` JSON maps. `subcategory` optional — when present, the action targets that one row (single-row bulk convenience).
- `GET /ops/monetization/toggles` → `[{key, value, description}]` for `monetization_enabled`, `boost_purchases_enabled`, `subscription_purchases_enabled`, `credit_boosts_enabled`.
- `PUT /ops/monetization/toggles/{key}` `{value}` → key must be in the toggle set (else 404) → `set_setting` + audit (`action='set_toggle'`, `entity_type='admin_setting'`).
- `GET /ops/monetization/settings` → `[{key, value, source, description}]` for the four subscription knobs (§2.3 rows 17–20).
- `PUT /ops/monetization/settings/{key}` `{value}` → registered subscription key only → `set_setting` + audit.
- `GET /ops/monetization/revenue` → `{stars_earned_last_30d (sum of `amount` over `get_star_transactions` where `source.transaction_type == "invoice_payment"`), active_subscriptions (status='active' AND current_period_end > now), active_boosts (ends_at > now), expiring_soon (boosts with ends_at within 24h, joined to items: `[{boost_id, item_id, title, ends_at}]`), sources: {...}}` — all real data.
- `GET /ops/monetization/boosts` → active boosts (`ends_at > now`) JOIN `Item` JOIN `Channel`: `[{id, item_id, title, channel_username, source, price_paid_stars, starts_at, ends_at, created_at}]`.
- `POST /ops/monetization/boosts/{id}/end` → fetch boost; not active (`ends_at <= now` or item dead) → 409; else `end_boost_for_item(db, boost.item_id)` (verified `boost.py:311` — sets `ends_at=now` on the active row; **no refunds**, Rule 6.1) + audit (`action='end_boost_early'`, before/after ends_at) → 200.

### 2.10 `backend/api/routes/ops_settings.py` + `ops_audit.py` — Sections 8+9 (Phase 4, ops-admin protected)

- `GET /ops/settings` → `list_settings()` (live value + source per key — the effective-config view).
- `PUT /ops/settings/{key}` `{value}` → DB-sourced knobs (i.e., all registered keys) → `set_setting` + audit. **Env-sourced-only keys** (a key present in the registry but with no DB row yet is still editable — the edit CREATES the DB row, flipping source to `'db'`; that is the intended override mechanism). Reject (409, `{"detail": "Setting is env-sourced; edit via deploy"}`) only for keys **not registered** in the registry — the console never silently accepts an unknown knob.
- `GET /ops/audit?section=&admin=&limit=50&offset=0` → `audit_log` rows filtered (exact `section`, exact `admin_user`), ordered `created_at DESC`. Read-only; no edit/delete/export endpoints.

### 2.11 `backend/api/routes/ops_payments.py` — Section 7 (Phase 5, ops-admin protected)

- `GET /ops/payments/ledger` → `star_payments.get_star_transactions(limit=100)` flattened: `[{id, date, amount, transaction_type, payload_prefix, user_id}]` (errors → 502 with message).
- `GET /ops/payments/balance` → `star_payments.get_my_star_balance()` → `{balance_stars}`.
- `GET /ops/payments/reconciliation` → `scheduler_runs` row for `'reconciliation'` (`last_run_at/last_success_at/last_error/last_result`) or `{status: "never run"}`.
- `POST /ops/payments/reconciliation/run` → `asyncio.run(reconcile_star_payments(db))` (D5) → `record_scheduler_run('reconciliation', success, error, summary)` → audit (`section='payments'`, `action='run_reconciliation'`, `entity_type='scheduler'`) → 200 summary.
- `POST /ops/payments/refund` `{telegram_payment_charge_id}` → **adapter method (D4, added in Phase 1)** `star_payments.refund_star_payment(telegram_payment_charge_id=...)` → audit (`action='refund_star_payment'`, `entity_type='payment'`, `entity_id=charge_id`, after=`{result}`) → 200. Frontend shows the warning confirm; backend never refunds without the audited call.

### 2.12 `backend/api/routes/ops_tools.py` — Section 10 (Phase 6, ops-admin protected)

- `POST /ops/tools/test-boost` `{item_id}` → item exists (404 else); `get_boost_eligibility` non-ownership check (409 when an active boost exists); resolve owner user via `item.channel.registered_by` (get-or-create like `fulfill_boost`); insert `Boost(item_id, channel_id, user_id, source='test', price_paid_stars=None, telegram_payment_charge_id=None, starts_at=now, ends_at=now + BOOST_DURATION_DAYS)` (D3: free-string source) → commit → audit (`section='tools'`, `action='grant_test_boost'`, `entity_type='boost'`, `entity_id=id`, `after={item_id, source, ends_at}`) → 200 summary. **No schema additions.**
- `POST /ops/tools/test-subscription` `{user_id, product}` → `user_id` is the Telegram id; user must exist (404 else); `product ∈ {alerts_only, all_in_one}`; insert `Subscription(user_id, product, status='active', telegram_payment_charge_id=None, invoice_payload=f"s:{user.id}:{product}:test:{token_hex(4)}", current_period_start=now, current_period_end=now + SUBSCRIPTION_PERIOD_SECONDS, is_recurring=False)` → commit → `reactivate_lapsed_alerts(db, user)` (mirrors real fulfillment) → audit.
- `POST /ops/tools/test-subscription/{id}/revoke` → set `status='canceled'` on the row → `lapse_benefits(db, user)` → audit (`action='revoke_test_subscription'`). (ops-console.md §8.1 explicitly lists grant *and revoke*.)
- `POST /ops/tools/simulate-payment` `{telegram_payment_charge_id, invoice_payload, total_amount, subscription_expiration_date?, is_recurring?, is_first_recurring?}` — **the primary UAT tool; drives the exact fulfillment path the listener calls, without Telegram:**
  - Gate: `get_setting(db, "monetization_enabled")` false → **503** (identical to the internal routes' kill switch, `payments.py:30-33`).
  - Payload prefix `b:` → parse `item_id` from payload → resolve owner telegram id from `item.channel.registered_by` → resolve `User` → `fulfill_boost(db, telegram_user_id=owner.telegram_id, telegram_payment_charge_id, invoice_payload, total_amount)`. Prefix `s:` → parse `user_id` from payload (`parts[1]`) → `User` → `fulfill_subscription_payment(db, telegram_user_id=user.telegram_id, ..., subscription_expiration_date, is_recurring, is_first_recurring)`. Unknown prefix → 400.
  - **Idempotent by charge id** (both fulfill functions return the existing row on replay — verified `boost.py:136-140`, `subscriptions.py:176-181`).
  - Audit (`action='simulate_payment'`, `entity_type='payment'`, `entity_id=charge_id`, `after={boost_id|subscription_id}`).
- `GET /ops/tools/deep-links?item_id=&channel_id=` → `{stores_url: f"{WEB_APP_URL}/stores/{channel_id}/{item_id}", item_url: f"{WEB_APP_URL}/item/{item_id}"}` (patterns verified: `worker.py:110`, `App.jsx:51`). New constant `WEB_APP_URL = os.getenv("WEB_APP_URL", "https://indexgebeya.cfd")` added to `constants.py`. If `channel_id` omitted but `item_id` given, derive from the item.

### 2.13 Frontend modules

- **`frontend/src/pages/OpsConsole.jsx`** — the shell: full standalone page (no `BottomNav`, no Telegram embed), left-rail nav with all ten sections from the §2 map of ops-console.md, "Coming soon" stubs for Catalog / Trust & Moderation / Users / Alerts & Notifications, shared kit usage everywhere. Handles login state via `useOpsAuth`; unmounted sections render `OpsEmptyState`-based stubs. Tabs are state-based (no router sub-routes).
- **`frontend/src/sections/`** — `OpsOverview.jsx` (polls `/ops/health` every ≤30s, age-labeled per signal via `generated_at`; stale > 90s labeled "stale"; "unavailable" rendered verbatim — never fabricated), `OpsMonetization.jsx` (pricing accordion grouped by category with demand-context columns + inline edit + bulk action modal; toggles panel; subscription settings panel; revenue cards; moderation table with end-early confirm), `OpsSettings.jsx` (registry table: description, live value, source badge db/env; DB-sourced editable with confirm; env-sourced rows labeled "requires deploy to change" and non-editable), `OpsAudit.jsx` (filterable read-only table: admin, section, action, entity, before/after, timestamp), `OpsPayments.jsx` (ledger, balance, last reconciliation + run-now button, refund form with warning dialog), `OpsTools.jsx` (test-boost form, test-subscription grant/revoke, simulator form, deep-link generator).
- **`frontend/src/components/ops/`** — `OpsTable.jsx` (columns/data/loading/empty slot), `OpsEmptyState.jsx`, `OpsConfirmDialog.jsx`, `OpsToast.jsx`, `OpsInlineEdit.jsx`. Shared across all sections — no per-section bespoke patterns (Rule 1.2).
- **`frontend/src/hooks/useOpsAuth.js`** — `{user, role, loading, login(u,p), logout()}`; on mount calls `/ops/auth/me`; 401 → login form state.
- **`frontend/src/utils/opsApi.js`** — `opsFetch(path, opts)` wrapper: JSON in/out, non-2xx → thrown error with detail; 401 → triggers logout state. Used by every section.

---

## 3. Strict Import Map (additive only — nothing removed)

### Backend — `backend/models.py` (edit)
- Add to line-1 import: `JSON` → `from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, BigInteger, Boolean, UniqueConstraint, JSON`
- New classes appended after `Subscription` (line 331): `AuditLog`, `AdminSetting`, `BoostPrice`, `SchedulerRun`, `ListenerHeartbeat` — no new imports beyond `JSON`.

### Backend — new services
- `backend/services/audit.py`:
  - `from database import ...` — none needed; takes `db` from callers: `from sqlalchemy.orm import Session`; `from models import AuditLog`.
- `backend/services/settings_registry.py`:
  - `from sqlalchemy.orm import Session`; `from sqlalchemy import select`; `from models import AdminSetting`; `import constants as C` (for env-default values via `C.<CONSTANT_NAME>`).
  - Public: `get_setting`, `set_setting`, `list_settings`. No imports from other services.
- `backend/services/boost_pricing.py`:
  - `from sqlalchemy.orm import Session`; `from sqlalchemy import select`; `from models import BoostPrice, Item`; `from constants import BOOST_PRICE_STARS`; `from ai_engine.prompts import TAXONOMY_STRUCTURE` (seed only).
  - Public: `get_boost_price`, `get_boost_price_by_key`, `get_boost_floor`, `set_boost_price`, `set_boost_price_bulk`, `invalidate_boost_price_cache`, `seed_boost_prices`. **Imports no other service** — cycle-free by construction.
- `backend/services/scheduler_runs.py`:
  - `from sqlalchemy.orm import Session`; `from sqlalchemy import select`; `from models import SchedulerRun`.

### Backend — edited services
- `backend/services/boost.py` (edit):
  - Replace import block at lines 21-29: keep `BOOST_DURATION_DAYS`, `BOOST_ROTATION_MINUTES`; drop `BOOST_PRICE_STARS` and `MONETIZATION_ENABLED` from the constants import if no longer referenced; add `from services.boost_pricing import get_boost_price` (re-export — `items.py` and `test_boost.py` keep `from services.boost import get_boost_price`, unchanged); add `from services.settings_registry import get_setting`.
  - Replace lines 99 and 194 (`if not MONETIZATION_ENABLED`) with `if not get_setting(db, "monetization_enabled"):` (db is in scope in both functions).
  - Delete the local `get_boost_price` definition (lines 44-50) — now the re-export. `_OTHER_FLOOR` (line 33) moves to `boost_pricing.py`.
- `backend/services/subscriptions.py` (edit):
  - Drop `BOOST_PRICE_STARS` from the constants import (line 36); add `from services.boost_pricing import get_boost_floor`; replace the floor computation (lines 286) with `boost_floor = get_boost_floor(db)`.
- `backend/services/cleanup.py` (edit):
  - Add `from services.scheduler_runs import record_scheduler_run`; instrument `run_cleanup_and_log` (lines 202-213): `db = SessionLocal()` at entry → `record_scheduler_run(db, scheduler="cleanup", success=False, error="started")` before running → after success `record_scheduler_run(db, scheduler="cleanup", success=True, result=summary)`; `except Exception` → `record_scheduler_run(db, scheduler="cleanup", success=False, error=str(e))`; `finally: db.close()`.
- `backend/services/reconciliation.py` (edit): no import changes — the instrumentation lives in `main.py`'s scheduler closure (which already imports the function and `SessionLocal`).
- `backend/services/telegram_payments.py` (edit):
  - Protocol (after `get_my_star_balance`, line 60): `async def refund_star_payment(self, *, telegram_payment_charge_id: str) -> bool: """POST /bot{TOKEN}/refundStarPayment.""" ...`
  - `HttpxStarPaymentsAdapter` (after line 151): implement via `self._post("refundStarPayment", {"telegram_payment_charge_id": telegram_payment_charge_id})` → return True.
- `backend/constants.py` (edit): add `WEB_APP_URL: str = os.getenv("WEB_APP_URL", "https://indexgebeya.cfd")` in the monetization group.

### Backend — new routes (each imports `from services.auth`? No — ops routes use `require_ops_admin` from `ops_auth`)
- `backend/api/routes/ops_auth.py`: `from fastapi import APIRouter, Depends, Request, HTTPException`; `from starlette.requests import Request`; `import os`.
- `backend/api/routes/ops_health.py`: `from fastapi import APIRouter, Depends`; `from sqlalchemy.orm import Session`; `from database import get_db, engine`; `from models import ListenerHeartbeat, SchedulerRun, Boost, Subscription, Item`; `from services.telegram_payments import star_payments`; `from sqlalchemy import select`; `import httpx` (frontend probe); `from .ops_auth import require_ops_admin`; `from datetime import datetime, timezone, timedelta`.
- `backend/api/routes/ops_monetization.py`: `from fastapi import APIRouter, Depends, HTTPException`; `from sqlalchemy.orm import Session`; `from sqlalchemy import select, func`; `from database import get_db`; `from models import Boost, Item, Channel, Subscription, BoostPrice, AdminSetting`; `from services.boost_pricing import get_boost_price_by_key, set_boost_price, set_boost_price_bulk, invalidate_boost_price_cache`; `from services.boost import end_boost_for_item, get_boost_eligibility`; `from services.settings_registry import get_setting, set_setting`; `from services.audit import record_audit`; `from services.telegram_payments import star_payments`; `from .ops_auth import require_ops_admin`; `from schemas import OpsLoginRequest?` (no — schemas: `OpsPriceUpdateRequest`, `OpsPriceBulkRequest`, `OpsToggleUpdateRequest`, `OpsSettingUpdateRequest` — new, added to `schemas.py`).
- `backend/api/routes/ops_settings.py`: `from fastapi import APIRouter, Depends, HTTPException`; `from sqlalchemy.orm import Session`; `from database import get_db`; `from services.settings_registry import list_settings, set_setting`; `from services.audit import record_audit`; `from .ops_auth import require_ops_admin`.
- `backend/api/routes/ops_audit.py`: `from fastapi import APIRouter, Depends, Query`; `from sqlalchemy.orm import Session`; `from sqlalchemy import select`; `from database import get_db`; `from models import AuditLog`; `from .ops_auth import require_ops_admin`.
- `backend/api/routes/ops_payments.py`: `from fastapi import APIRouter, Depends, HTTPException`; `from sqlalchemy.orm import Session`; `from database import get_db`; `from services.telegram_payments import star_payments`; `from services.reconciliation import reconcile_star_payments`; `from services.scheduler_runs import record_scheduler_run`; `from services.audit import record_audit`; `from models import SchedulerRun`; `from .ops_auth import require_ops_admin`; `import asyncio`.
- `backend/api/routes/ops_tools.py`: `from fastapi import APIRouter, Depends, HTTPException`; `from sqlalchemy.orm import Session`; `from sqlalchemy import select`; `from database import get_db`; `from models import Boost, Subscription, User, Item, Channel`; `from services.boost import fulfill_boost, get_boost_eligibility`; `from services.subscriptions import fulfill_subscription_payment, reactivate_lapsed_alerts, lapse_benefits`; `from services.audit import record_audit`; `from services.settings_registry import get_setting`; `from constants import BOOST_DURATION_DAYS, SUBSCRIPTION_PERIOD_SECONDS, WEB_APP_URL`; `from .ops_auth import require_ops_admin`; `import secrets`.
- `backend/api/routes/internal.py`: `from fastapi import APIRouter, Header, HTTPException`; `from sqlalchemy.orm import Session`; `from database import get_db`; `from models import ListenerHeartbeat`; `from datetime import datetime, timezone`.
- **Edited routes (Phase 3):**
  - `backend/api/routes/items.py`: add `from services.settings_registry import get_setting`; change `_monetization_enabled_or_503` (lines 37-40) to take `db: Session` and check `get_setting(db, "monetization_enabled") and get_setting(db, "boost_purchases_enabled")` (quote/order) and `... and get_setting(db, "credit_boosts_enabled")` (credit); update the 5 call sites (lines 326, 349, 362, plus `_monetization_enabled_or_503(db)`).
  - `backend/api/routes/payments.py`: same helper change (lines 30-33) → `get_setting(db, "monetization_enabled")`; 3 call sites (45, 74, 107).
  - `backend/api/routes/subscriptions.py`: same (lines 27-31) → `monetization_enabled and subscription_purchases_enabled`; 2 call sites (41, 52).
  - `backend/api/routes/channels.py`: same (lines 28-31) → `monetization_enabled`; 1 call site.
- `backend/schemas.py` (edit — additive): `OpsLoginRequest {username, password}`, `OpsPriceUpdateRequest {price_stars: int}`, `OpsPriceBulkRequest {action: Literal["set_category","percent","reset"], category: str, subcategory: str|None, price_stars: int|None, percent: int|None}`, `OpsToggleUpdateRequest {value: bool}`, `OpsSettingUpdateRequest {value}`, `OpsRefundRequest {telegram_payment_charge_id: str}`, `TestBoostRequest {item_id: int}`, `TestSubscriptionRequest {user_id: int, product: str}`, `TestSubscriptionRevokeRequest` (id path param only — none), `SimulatePaymentRequest {telegram_payment_charge_id: str, invoice_payload: str, total_amount: int, subscription_expiration_date: datetime|None = None, is_recurring: bool = False, is_first_recurring: bool = False}`.
- `backend/tests/fake_telegram_payments.py` (edit): add `async def refund_star_payment(self, *, telegram_payment_charge_id): self.calls.append({"method": "refund_star_payment", "telegram_payment_charge_id": telegram_payment_charge_id}); return True`.

### Backend — `backend/main.py` (edit)
- Add: `from starlette.middleware.sessions import SessionMiddleware`; `from api.routes import ingestion, search, items, reviews, alerts, notifications, analytics, feed, channels, payments, subscriptions, ops_auth, ops_health, ops_monetization, ops_settings, ops_audit, ops_payments, ops_tools, internal as internal_routes` (line 13 extended).
- After the CORS middleware (line 45): `app.add_middleware(SessionMiddleware, secret_key=os.getenv("ADMIN_SECRET_KEY", "change-me-in-production"), session_cookie="ops_session", max_age=604800, same_site="lax")`.
- Startup: new migration block (TECH-32) with `CREATE TABLE IF NOT EXISTS audit_log/admin_settings`; TECH-33 block for `scheduler_runs` + `listener_heartbeat`; TECH-34 block for `boost_prices`; new Phase 5.7 block calling `seed_boost_prices` via `SessionLocal`; instrumentation of the `_schedule_cleanup` and `_schedule_reconcile` closures (scheduler_runs writes; the reconcile guard switches from `MONETIZATION_ENABLED` to `get_setting(db, "monetization_enabled")` read inside the closure).
- Router registration (after line 477): `app.include_router(internal_routes.router)` and the seven ops routers with prefixes `/ops/auth`, `/ops/health`, `/ops/monetization`, `/ops/settings`, `/ops/audit`, `/ops/payments`, `/ops/tools`.

### Listener
- `listener/stats.py` (new): stdlib only.
- `listener/client.py` (edit): add `async def send_heartbeat(queue) -> None` (uses `INTERNAL_HEADERS`, `API_BASE`, `logger`; imports `from stats import stats`).
- `listener/main.py` (edit): `from stats import stats`-backed task import — `from client import send_heartbeat`; in `post_init`: `asyncio.create_task(send_heartbeat(job_queue))`.
- `listener/worker.py` (edit): `from stats import stats`; after the `result.get('success')` branch (line 66 break) — `stats["items_processed_total"] += 1; stats["last_update_at"] = now`.
- `listener/photo_refresher.py` (edit): `from stats import stats`; set `stats["photo_refresher"]` sub-keys at cycle completion (line 87) and in the exception handler (line 90).

### Deploy
- `deploy/Caddyfile` (edit): insert before the SPA catch-all (line ~36), the blocks in D7: `/ops/auth*`, `/ops/health*`, `/ops/monetization*`, `/ops/settings*`, `/ops/audit*`, `/ops/payments*`, `/ops/tools*`, `/ops/internal*` → `reverse_proxy index_api:8000`. The exact `/ops` page and any other `/ops/*` path continue through the catch-all to the SPA.

### Frontend
- `frontend/src/App.jsx` (edit): at the top of the `App` component body (before the `isTelegramWebView()` gate at line 102): `if (window.location.pathname.startsWith('/ops')) return <OpsConsole />;` + `import OpsConsole from './pages/OpsConsole';`.
- New files: `pages/OpsConsole.jsx`, `sections/OpsOverview.jsx`, `sections/OpsMonetization.jsx`, `sections/OpsSettings.jsx`, `sections/OpsAudit.jsx`, `sections/OpsPayments.jsx`, `sections/OpsTools.jsx`, `components/ops/OpsTable.jsx`, `components/ops/OpsEmptyState.jsx`, `components/ops/OpsConfirmDialog.jsx`, `components/ops/OpsToast.jsx`, `components/ops/OpsInlineEdit.jsx`, `hooks/useOpsAuth.js`, `utils/opsApi.js`, `__tests__/OpsConsole.test.jsx`.

---

## 4. Execution Steps

All steps are atomic and additive. **Do not commit until QA approves the phase.** Suggested commit messages: `feat(ops): phase N — <title> (NB-XX)`.

### Phase 1 — Shell, Auth & Scaffolding (TECH-32 / NB-49)

1. `backend/models.py`: add `AuditLog`, `AdminSetting` classes per §2.1; extend the line-1 import with `JSON`.
2. `backend/main.py`: add `SessionMiddleware` (cookie `ops_session`); add the TECH-32 migration block (`audit_log`, `admin_settings` via `CREATE TABLE IF NOT EXISTS`, house pattern from the TECH-26 block at lines 291-348).
3. `backend/services/audit.py`: implement `record_audit` per §2.2.
4. `backend/services/settings_registry.py`: implement the registry per §2.3 with the full 20-key table.
5. `backend/api/routes/ops_auth.py`: login/logout/me + `has_role` + `require_ops_admin` per §2.6.
6. `backend/api/routes/internal.py`: `POST /internal/heartbeat` per §2.7 (backend half — write `ListenerHeartbeat`).
7. `backend/models.py`: also add `ListenerHeartbeat` + `SchedulerRun` + `BoostPrice` now (one schema pass per phase is wasteful; the tables are needed by phases 2-3, and `create_all` + migrations are idempotent). Spec: add **all five** new tables in Phase 1 (migration blocks for all five in the same commit).
8. `backend/services/telegram_payments.py`: add `refund_star_payment` to Protocol + httpx impl; `tests/fake_telegram_payments.py` fake gains it (D4 — needed by Phase 5, built now for adapter-method presence tests).
9. `backend/schemas.py`: add the ops request schemas per §3.
10. `backend/main.py`: register `internal_routes` + the seven ops routers; add the `seed_boost_prices` Phase 5.7 block (calls the Phase-3 module — create `backend/services/boost_pricing.py` now with `seed_boost_prices` + `get_boost_price`/fallback/cache per §2.4 so the seed runs from Phase 1; the DB-first read switchover is Phase 3).
11. `deploy/Caddyfile`: add the eight `/ops/*` API handles (D7). Sync note: the host copy `/home/ubuntu/caddy/Caddyfile` must be updated at deploy time (rollout step).
12. `frontend/src/App.jsx`: `/ops` guard before the Telegram gate (D8).
13. Frontend shell: `components/ops/*` kit, `hooks/useOpsAuth.js`, `utils/opsApi.js`, `pages/OpsConsole.jsx` with the ten-section rail and four stubs.
14. Tests: `backend/tests/test_ops_auth.py`, `test_audit.py`, `test_settings_registry.py` per §5.
15. Verify: `python -m pytest backend/tests/test_ops_auth.py backend/tests/test_audit.py backend/tests/test_settings_registry.py backend/tests/test_admin.py -q`; `cd frontend && npm test && npm run build`.
16. Commit `feat(ops): phase 1 — shell, auth & scaffolding (NB-49)`.

### Phase 2 — Overview (TECH-33 / NB-50)

1. `backend/services/scheduler_runs.py`: implement `record_scheduler_run` (§2.5).
2. Instrument `services/cleanup.py` `run_cleanup_and_log` (§3) and the `main.py` `_schedule_reconcile` closure (`record_scheduler_run("reconciliation", ...)` around `asyncio.run(...)`).
3. Listener heartbeat: `listener/stats.py`, `worker.py` counters, `photo_refresher.py` state, `client.py` `send_heartbeat`, `main.py` task — per §2.7/§3.
4. `backend/api/routes/ops_health.py`: implement `/ops/health` with the exact per-signal sources of §2.8 (probe function `_probe_frontend()` factored so tests can monkeypatch it; `get_my_star_balance` wrapped in try/except → signal-level `error`).
5. `frontend/src/sections/OpsOverview.jsx`: 30s poll, age labels (stale > 90s), verbatim `unavailable` rendering.
6. Tests: `backend/tests/test_ops_health.py` (shape + auth gate + per-signal honesty: monkeypatched probe failures → `error`, no heartbeat row → listener `unknown`; `scheduler_runs` writes from cleanup + reconcile; heartbeat write + read round-trip).
7. Verify: full backend suite `python -m pytest backend/tests -q` (baseline 116 passed / 2 pre-existing / 18-22 skipped must hold); `cd frontend && npm test && npm run build`.
8. Commit `feat(ops): phase 2 — overview & health (NB-50)`.

### Phase 3 — Monetization (TECH-34 / NB-51) — THE CORE

1. `backend/services/boost_pricing.py`: full §2.4 (fallback chain, TTL cache, invalidation, seed over `TAXONOMY_STRUCTURE`; seed now also re-verifies idempotency — run twice in a test).
2. `backend/services/boost.py`: re-export `get_boost_price` from `boost_pricing`; delete the local definition; switch lines 99/194 to `get_setting(db, "monetization_enabled")`.
3. `backend/services/subscriptions.py`: floor via `get_boost_floor(db)` (D12).
4. Switch the four route modules (`items.py`, `payments.py`, `subscriptions.py`, `channels.py`) to registry reads (§3); `main.py` reconcile guard reads the registry inside the closure.
5. **Migrate the four stale monkeypatch sites** (D11): `test_boost.py:241/1001`, `test_payments_flow.py:156/250` → control via `monkeypatch.setattr("services.settings_registry.get_setting", lambda db, key, **kw: False)` (or write `AdminSetting` rows). The 503 assertions themselves stay identical.
6. `backend/api/routes/ops_monetization.py`: all endpoints per §2.9 (prices/demand, PUT price, bulk, toggles, settings, revenue, moderation).
7. `frontend/src/sections/OpsMonetization.jsx`: pricing accordion + inline edit + bulk modal + toggles + settings + revenue cards + moderation table with confirm.
8. Tests: `backend/tests/test_ops_monetization.py` + `test_boost_pricing.py` per §5.
9. Verify: full backend suite; `cd frontend && npm test && npm run build`.
10. Commit `feat(ops): phase 3 — monetization section (NB-51)`.

### Phase 4 — Settings & Audit (TECH-35 / NB-52)

1. `backend/api/routes/ops_settings.py` + `ops_audit.py` per §2.10.
2. `frontend/src/sections/OpsSettings.jsx` + `OpsAudit.jsx` per §2.13.
3. Tests: `test_ops_settings.py`, `test_ops_audit.py` per §5.
4. Verify; commit `feat(ops): phase 4 — settings & audit sections (NB-52)`.

### Phase 5 — Payments (TECH-36 / NB-53)

1. `backend/api/routes/ops_payments.py` per §2.11 (run-now via `asyncio.run`; `record_scheduler_run("reconciliation", ...)` with the summary in `last_result`).
2. `frontend/src/sections/OpsPayments.jsx` per §2.13 (refund warning dialog).
3. Tests: `test_ops_payments.py` per §5.
4. Verify; commit `feat(ops): phase 5 — payments section (NB-53)`.

### Phase 6 — Support Toolkit (TECH-37 / NB-54)

1. `backend/constants.py`: `WEB_APP_URL`.
2. `backend/api/routes/ops_tools.py` per §2.12 (test-boost with `source='test'`; test-subscription grant/revoke; simulator driving the real fulfill path with charge-id idempotency; deep-links).
3. `frontend/src/sections/OpsTools.jsx` per §2.13.
4. Tests: `test_ops_tools.py` per §5 (simulator idempotency is the centerpiece).
5. Verify; commit `feat(ops): phase 6 — support toolkit (NB-54)`.

**Docs ride-along:** the working tree already carries edits to `CONTEXT.md`, `docs/adr/tech-backlog.md`, `docs/behaviors/monetization.md`, `docs/behaviors/pending-behaviors.md`, and the untracked `docs/behaviors/ops-console.md`. The architect decides between a docs-first commit or riding them in the final commit; the blueprint requires they land **before** QA sign-off of Phase 6, and that `docs/plans/ops-console-blueprint.md` (this file) is committed with Phase 1.

---

## 5. Testing Strategy

Per-phase modules with observable outcomes (interface is the test surface; no internal-state assertions):

**Phase 1**
- `test_ops_auth.py` — (a) login success sets `ops_session` cookie, `me` returns `{user, role}`; wrong password → 401; logout → me 401. (b) **Auth separation, both directions** (the locked acceptance): build `app = FastAPI(); app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session"); setup_admin(app); app.include_router(ops_auth.router, prefix="/ops/auth")` + a protected probe route. One `TestClient` across both: login to `/ops/auth/login` → `GET /admin/` → **302 to `/admin/login`** (sqladmin locked); then a second client: form-POST `/admin/login` with the env credentials → `GET /ops/auth/me` → **401** (console locked). (c) route gating: all six protected routes 401 unauthenticated.
- `test_audit.py` — `record_audit` writes a row with all fields; `before`/`after` JSON round-trips; rows persist (no delete path exists).
- `test_settings_registry.py` — DB row overrides env default (`get_setting` returns the DB value, `list_settings` labels `source='db'`); no DB row → env value, `source='env'`; cast validation (bool/int/float/str); `set_setting` upsert (same key twice → one row); missing-table fail-open (drop the table in a test session → env default returned, no raise).

**Phase 2**
- `test_ops_health.py` — 401 without session; shape has `generated_at` + all §2.8 signals; listener up when heartbeat row fresh, `down` when stale (>90s), `unknown` when absent; frontend probe monkeypatched to fail → `down`; `get_my_star_balance` raising → money signal `error` but endpoint 200; pending-payment count matches seeded unfulfilled transaction; scheduler rows: `cleanup` and `reconciliation` written by their instrumented paths (call `run_cleanup_and_log`, run the scheduler closure), photo_refresher derived from a seeded heartbeat payload.
- Frontend (where feasible): age-labeling unit test — given a fixed `generated_at`, signals older than 90s render "stale".

**Phase 3**
- `test_boost_pricing.py` — seed idempotency (two calls, same count); fallback chain (subcategory row wins; category `""` row wins; unseeded → constant; unknown → floor 25); cache: `get_boost_price` then `set_boost_price` → next read returns the new price immediately (invalidation); TTL path.
- `test_ops_monetization.py` — PUT price updates row + cache + audit row (`before`/`after` correct); bulk set_category/percent/reset over a category; toggles: PUT then `get_setting` reflects instantly; **503 path preserved**: `monetization_enabled` DB row `false` → `/items/{id}/boost-quote`, `/internal/payments/fulfill-boost`, `/subscriptions/order` all still 503 (regression via the migrated monkeypatch sites); demand context counts (active + this-week per category/subcategory); end-early: `POST /ops/monetization/boosts/{id}/end` ends the boost (ends_at == now) + audit + the item leaves the pinned block; in-flight stability: quote price P, change DB price to P', fulfill the old invoice → `price_paid_stars == P`.

**Phase 4**
- `test_ops_settings.py` — registry surface (all 20 keys with live value + source); env-vs-db precedence; **read-only enforcement**: PUT to an unregistered key → 409 with the clear error.
- `test_ops_audit.py` — list ordered desc; `section=` and `admin=` filters; read-only (no mutation endpoints exist).

**Phase 5**
- `test_ops_payments.py` — ledger renders the fake adapter's seeded transactions; balance from the fake; run-now invokes `reconcile_star_payments` (fake ledger → replayed rows) + writes `scheduler_runs` + audit; refund calls the adapter (`fake.calls` contains `refund_star_payment`) + audit row; **adapter-method presence**: `refund_star_payment` on Protocol/httpx/fake (Phase 1 test).

**Phase 6**
- `test_ops_tools.py` — **simulator drives the real fulfillment path**: simulate a `b:` payload → `boosts` row appears with `source='paid'`, `price_paid_stars == total_amount`; **replay the same charge id → same boost id, no duplicate**; simulate `s:` payload → subscription row + lapsed alerts reactivated; simulator 503 when monetization disabled; unknown prefix → 400; test-boost creates `source='test'` row + audit, 409 on double-grant; test-subscription grant/revoke + audit + cap effects (grant raises effective cap, revoke lapses extras); deep-links URL shape.

**Regression gate (every phase):** full backend suite baseline 116 passed / 2 pre-existing failures / 18–22 skipped (verified on pristine main per tech-backlog TECH-24/31); `cd frontend && npm test && npm run build` green.

---

## 6. Rollout Notes

- **Kill-switch interplay.** `MONETIZATION_ENABLED` env stays the seed; the DB flag overrides from Phase 3 on. Backend 503 behavior is preserved exactly (routes read the registry per-request → instant effect, no restart). The **listener keeps its own env copy** (`listener/payments.py:30`) — when the DB flag flips off while the listener env is still `1`, the listener calls the backend, gets a 503, and its existing client functions log-and-drop (`client.py` non-200 branch → returns False) — graceful, exactly the current kill-switch semantics. No listener code change is needed for the flag; the heartbeat's *response* could carry the flag in a future phase (documented, not built). Reconciliation scheduler guard switches to the registry (read inside the daily closure) so a flip stops the replay pass without a restart.
- **Seed idempotency on existing DBs.** `seed_boost_prices` uses `INSERT ... ON CONFLICT DO NOTHING`; existing deployments get 113 rows on first boot after Phase 1, zero rows thereafter. Operator price edits are never overwritten by later seeds.
- **Cache invalidation correctness.** Single api process (uvicorn, one worker) → the module cache is coherent; the ops edit path invalidates the touched keys immediately, so `get_boost_price` reflects edits on the next quote/order. The 60s TTL is the safety net if the app is ever run multi-worker; worst case a price edit propagates within 60s, never a stale price forever.
- **Migration failure.** House pattern: each migration block is `try/except`-logged and the app boots anyway. Console tables missing → `get_setting` fails open to env defaults and `/ops/health` signals degrade to `unavailable` — the marketplace never crashes because the console's schema failed. `Base.metadata.create_all` (main.py Phase 2) creates the new tables on fresh DBs; the `CREATE TABLE IF NOT EXISTS` blocks cover existing DBs.
- **Caddy sync.** `deploy/Caddyfile` is a versioned copy; the live `/home/ubuntu/caddy/Caddyfile` must receive the same eight handles during deployment, or the ops API returns the SPA's `index.html` instead of JSON (symptom: login returns HTML).
- **Session notes.** `ops_session` cookie is `same_site=lax`, 7-day max age, https in production via Caddy. sqladmin's logout (`session.clear()`) cannot touch `ops_session` (different cookie) and vice versa — the console's logout pops only its own key.
- **Operator discipline (documented in the UI):** test grants and simulated payments are real rows in production tables — audit rows make them identifiable (`source='test'`, payload suffix `:test:...`); refunds are irreversible in Telegram; `end boost early` grants no refunds (Rule 6.1).

---

## Blueprint section list

1. Architecture Context · 2. The New Interfaces (tables, audit, registry, boost pricing, scheduler runs, auth, heartbeat, health, monetization, settings/audit, payments, tools, frontend) · 3. Strict Import Map · 4. Execution Steps (Phases 1–6 + docs ride-along) · 5. Testing Strategy · 6. Rollout Notes · §0 Verification & Drift Notes.

## Drift summary (locked design vs verified file state)

- sqladmin's session is on a **mounted sub-app with its own `session` cookie** — the ops console needs its own parent-level `SessionMiddleware` (`ops_session` cookie + `ops_admin` key), not just a distinct key (D1).
- `search.py` does **not** read `MONETIZATION_ENABLED`; the real read sites are `items.py`, `payments.py`, `subscriptions.py`, `channels.py`, `services/boost.py`, `main.py` scheduler, `listener/payments.py` (D2).
- `Boost.source` is a free string — `'test'` works with no schema change (D3).
- `refund_star_payment` does **not exist** — must be added to Protocol + httpx + fake (D4).
- `reconcile_star_payments` is `async (db, *, limit=100) -> dict`; `SchedulerRun` needs an additive `last_result` JSON column for run-now results (D5).
- Taxonomy seed source confirmed: `ai_engine/prompts.py` `TAXONOMY_STRUCTURE` (18 keys, 95 subcategories; mirrors `taxonomy.js`) (D6).
- **Caddyfile currently routes all `/ops*` to the SPA** — eight API handles must be added (D7).
- **`App.jsx` renders `LandingPage` for all non-Telegram visitors before the Router** — the `/ops` guard must precede it (D8).
- The listener is HTTP-only — photo-refresher scheduler stats ride the heartbeat payload (D9).
- Registry env names verified against `constants.py` (D10).
- Four existing kill-switch monkeypatch sites must migrate to registry control in Phase 3 (D11).
- Subscription floor + cycle rule → new `services/boost_pricing.py` module shared by `boost.py` and `subscriptions.py` (D12).

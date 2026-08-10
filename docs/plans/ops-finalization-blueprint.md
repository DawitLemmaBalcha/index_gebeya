# OPS FINALIZATION BLUEPRINT — NB-55..NB-60 / TECH-40..45

**Date:** 2026-08-09
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture
**Target branch:** `feat/ops-finalization` (created from main @ f22d140 before step 1)
**Authority:** `docs/behaviors/ops-finalization.md` (10 sections, locked 2026-08-08) > `docs/behaviors/pending-behaviors.md` NB-55..NB-60 > `docs/adr/tech-backlog.md` TECH-40..45 > `docs/behaviors/ops-console.md` (shell contracts). Deviation from any of these requires a new architect lock.

---

## 1. Architecture Context

**The reframe (diagnose-and-act).** sqladmin edits rows; the ops console computes, diagnoses, and makes the engine act. The four stubs (Catalog, Trust & Moderation, Users, Alerts & Notifications) become real action centers; the seller-side owner quality loop is added at the ingest DM. Every new surface ends in at least one verb; nothing reduces to row-editing.

**Dependency categories.** All six packages are **Local-substitutable** — they add pure query/compute services (`ban.py`, `radar.py`, `trace.py`) and one thin ops router (`ops_finalize.py`) over existing models and services. Nothing new reaches out of the process except:
- the listener's two new HTTP calls (`get_item_api`, `mark_notification_failed`) against the existing backend seam — the listener is HTTP-only by design (D9, NB-50);
- the judge-counters read for the radar — **process-local module state** (`alerting.JUDGE_ERROR_COUNT` / `JUDGE_ERROR_LAST_TS`, alerting.py L27–28), already surfaced by ops_health.py L190–195; the radar reads the same module, reset-on-restart semantics documented;
- one instrumentation gap closure (the FAILED notification status — see §6), NB-50-precedent (scheduler_runs).

**Friction mapped (verified):** `worker.py` DM branch (L89–131) carries only title+price from the ingest response; `item_status.update_item` (L246–281) re-triggers only on price/specs; no `User.banned` flag exists; five item-query seams (search raw SQL, catalog ORM, five feed sub-queries, the pinned-boost layer) are filter-blind to seller state; the alert engine's decisions are computed and unobservable; nothing records notification delivery failure; the four stubs render "Coming soon" (OpsConsole.jsx L170–188).

**The one non-negotiable invariant:** `channels.registered_by` is a **plain BigInteger storing the owner's TELEGRAM ID — not a users.id FK** (models.py L135; main.py L283–284 documents "plain BigInteger, NOT an FK — intentionally untouched"; usage proof: item_status.py L47 and ops_tools.py L71 both resolve `User.telegram_id == channel.registered_by`). Every ban-enforcement join resolves through `users.telegram_id`, and every exclusion predicate must be NULL-safe so ownerless channels (`registered_by IS NULL`, Rule 1.4) stay visible.

---

## 2. The New Interfaces

### Package 1 — TECH-40 / NB-55: Owner Quality Loop

**1.1 Internal item fetch (new adapter at the existing internal seam).**
`backend/api/routes/internal.py` gains `GET /internal/items/{item_id}` — gated by header `X-Internal-Service == "index-listener"` (exactly the heartbeat pattern, internal.py L21–28). Loads the Item row and its ItemImage gallery. Returns `{id, title, price, currency, description, specs, category, subcategory, image_path, images: [paths...]}`. 404 when the item row is missing. No auth beyond the internal header.

`listener/client.py` gains `get_item_api(item_id) -> dict | None` — `GET {API_BASE}/internal/items/{item_id}` with `INTERNAL_HEADERS`. On any failure: log a warning, return None, never raise (mirrors `get_channel_info`, client.py L179–199).

**1.2 The Indexed/Updated DM (worker.py success branch, both is_replaced variants, L91–123).**
After the existing `edit_text` computation, fetch `item_details = await get_item_api(result['item_id'])`. When details are present, build the rich DM:
- Body: the existing title + formatted price line, then the description when present and not "No description", then a spec summary of the top 3–4 relevant spec values (skip keys `location`, `condition`, `contact_phone`, `phone_number` — the exact skip-set pattern from listener/notifications.py L113–126).
- Image: Telegram cannot edit text into a photo. When a media path exists (first of `images` or `image_path`), send a NEW photo message (`send_photo`, photo = `{WEB_APP_URL}/media/{path}`, caption = the full body above) and best-effort delete the processing DM (`dm_message.delete()` inside try/except — deletion failure is a warning, not fatal). When no media path exists, fall back to the existing `edit_text`.
- Buttons (one row, two buttons): **"✏️ Edit product"** and **"🚀 Boost this product"**, both `WebAppInfo` deep-links to `{WEB_APP_URL}/stores/{channel_id}/{item_id}` where `channel_id = channel_info.get('id')` — the exact NB-45 button infrastructure (worker.py L110–120), the Edit label added beside it. Both are doors into the existing web app (App.jsx L129 `/stores/:channelId/:itemId` verified).
- Error modes: fetch failure or send failure → fall back to today's text DM + the existing boost button. The DM never breaks.

**1.3 Category re-trigger (item_status.py L262–268).** Set `needs_reprocess = True` in the `category` change block AND in the `subcategory` change block (currently only price L260 and specs L281 set it). The `process_new_item(db, item.id)` call at L289 is unchanged. No separate catalog-placement hook exists or is needed — browse reads live rows (catalog.py L19–43), so the item moves in the catalog the moment the row updates; the re-trigger re-evaluates matching.

**1.4 Quality Events (new router `backend/api/routes/ops_finalize.py`).**
- `GET /ops/quality/events?limit=&offset=` (`require_ops_admin`): latest ItemEdit rows (order `timestamp DESC, id DESC`), each joined to the item title and the editor username. Response shape per row: `{id, item_id, title, field, old_value, new_value, edited_by, edited_by_username, timestamp}`. The existing `ItemEditResponse` (schemas.py L308–319) is the base — additive `title` + `edited_by_username` fields.
- `POST /ops/quality/events/{id}/revert` (`require_ops_admin`): load the ItemEdit row (404 if missing). Apply `old_value` back onto the item's column for the allowed fields `title, description, price, category, subcategory, specs` (any other field value → 400 "field not revertible"). Type coercion: `price` → float (parse failure → 400), `specs` → parse the stored JSON string and re-serialize canonically, all others → verbatim string; `old_value is None` → restore the column to NULL verbatim (all six columns are nullable — honest restore of "was empty"). Then record a NEW ItemEdit row for the same field with `old_value` = the just-restored-from current value and `new_value` = the restored value (revert is itself an edit event, Rule 2.1 visibility). When the reverted field is price/specs/category/subcategory, re-run `process_new_item(db, item.id)` (Rule 1.3 consistency). Audit via `record_audit(action="revert_item_edit", section="quality", entity_type="item_edit", entity_id=str(event_id), before/after)`. The `edited_by` FK is `users.id NOT NULL` — reverts use a **reserved console-admin User row, `telegram_id = -1`**, username = the current admin's username (resolve-or-create, one row, reused across reverts; documented in code as the console-admin sentinel). The Radar watchlist flagging of repeat offenders is a derived detection over ItemEdit history, documented in §6 as future radar input, not a v1 table.

### Package 2 — TECH-41 / NB-56: Ban Primitive

**2.1 Model + migration.** `backend/models.py` User gains `banned = Column(Boolean, default=False, nullable=False)` (Boolean already imported, models.py L1). `backend/main.py` gains an idempotent startup migration block in the established style (main.py L136–150): `ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN DEFAULT FALSE`.

**2.2 `backend/services/ban.py` (new — pure, no audit, no HTTPException at service level except the alert seam).**
- `is_banned(db, user) -> bool` — reads `user.banned`.
- `ban_user(db, user_id) -> User` — set True, commit, return; 404 when the row is missing.
- `unban_user(db, user_id) -> User` — set False, commit, return; 404 when missing.
- `is_channel_banned(db, channel) -> bool` — `channel.registered_by is not None` AND a User row exists with `telegram_id == channel.registered_by AND banned`.
- `owner_banned_pred()` — a SQLAlchemy `exists()` predicate: exists a User where `User.telegram_id == Channel.registered_by AND User.banned is True`. **NULL-safe by construction** (an ownerless channel matches no row → not excluded; Rule 1.4 preserved). Used negated (`~owner_banned_pred()`) at ORM query seams.

**2.3 The five enforcement seams (plus the pinned layer — six call sites total).**
1. **Alert creation** — `services/alerting.py::create_alert` (L304): first statement — banned → `HTTPException(403, "Account banned")`. HTTPException moves to a top-level import (currently imported inside the cap branch, L315). This covers the route and every caller.
2. **Review submission** — `api/routes/reviews.py::create_review`: immediately after user resolution (L37) — banned → 403 "Account banned".
3. **Sold-report submission** — `api/routes/items.py::report_item_as_sold`: immediately after `authenticate` (L236) — banned → 403.
4. **Ingestion channel-level** — `api/routes/ingestion.py::parse_telegram_post`: immediately after channel resolution (L93–99), before the photo fetch — when `channel.registered_by is not None` and `is_channel_banned(db, channel)` → `HTTPException(403, "Channel owner banned")`. Channel is resolved before item creation (verified: creation at L205), so the early reject is clean.
5. **Item queries** —
   - `services/search.py::_execute_search_sql`: add to the raw WHERE clause (L76–85 area) `AND NOT EXISTS (SELECT 1 FROM users u WHERE u.telegram_id = c.registered_by AND u.banned = TRUE)`. The `channels c` alias already exists (L75).
   - `services/catalog.py::browse_category`: extend the conditions tuple (L28–32) with `~owner_banned_pred()`.
   - `services/recommendation.py`: each of the five sub-queries that filter `Item.status == "active"` — `get_recent_items` (L32–43), `get_trending_items` (L71–77), `get_session_feed` (L116–124), `get_discovery_feed` (L177–186), `get_wildcard_feed` (L235–241) — gains `~owner_banned_pred()` in `.where(...)`.
   - `services/boost.py::get_pinned_boosted_items` (L214–258): the Boost+Item select (L227–235) gains `~owner_banned_pred()` — **verified drift:** the pinned layer queries items itself, so without this seam a banned seller's boosted item would still surface above the organic results even though the organic lists are filtered.
   - **Unban restores everything** — no cache, no derived state: the flag flips and every query seam re-reads it (Rule 3.5).

**2.4 Ops endpoints (ops_finalize.py).**
- `GET /ops/users/{telegram_id}/status` — `{telegram_id, username, banned, footprint: {reviews, alerts_active, alerts_total, subscriptions_active, boosts, sold_reports}}`. 404 when no User row.
- `POST /ops/users/{telegram_id}/ban` — `ban_user`; 404 when missing; audit (`action="ban_user", section="users", entity_type="user"`).
- `POST /ops/users/{telegram_id}/unban` — `unban_user`; audit. Instant restoration, no side jobs.

### Package 3 — TECH-42 / NB-57: Anomaly Radar

**3.1 Constants (constants.py, plain `_get_config`, documented, not registry-keyed in v1):** `RADAR_SCAM_CHANNEL_MAX_TRUST` (2.0), `RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X` (3.0), `RADAR_SCAM_CHANNEL_MIN_REPORTS` (2), `RADAR_PRICE_ANOMALY_MAX_X_MEDIAN` (10.0), `RADAR_DEAD_CHAT_SEVERITY_MEDIUM` (1), `RADAR_DEAD_CHAT_SEVERITY_HIGH` (3).

**3.2 `backend/services/radar.py` (new) — the five detections, each a pure query over `db`, each returning anomaly records `{type, severity, entity_id, summary, actions: [{verb, endpoint, method}]}`:**
1. `detect_dead_chat_buyers` — notifications with `status == "FAILED"` (honest rows — see 3.4 instrumentation), joined to User for the telegram_id. One anomaly per user, severity by FAILED count (≥ HIGH threshold → high, else medium), entity_id = user telegram_id, summary lists failing notification ids. Actions: retry (per notification, `POST /ops/actions/notifications/{id}/retry`), dismiss (`POST /ops/radar/resolve`).
2. `detect_judge_error_spikes` — reads `services.alerting.JUDGE_ERROR_COUNT` and `JUDGE_ERROR_LAST_TS`; when count > 0, one anomaly: summary "N judge errors since API restart (last at TS)", severity medium. **Action: dismiss only** — verified: no pause-matching kill switch exists (only `MONETIZATION_ENABLED`); locked decision, documented in the UI copy.
3. `detect_report_spikes` — active items (`status == "active"`) with sold-report count ≥ `CROWDSOURCE_SOLD_THRESHOLD − 1` (count via the sold_reports group-by, item_status.py L72–75 pattern). At-threshold → high, near → medium. Actions: clear reports (`POST /ops/radar/items/{id}/clear-reports`), view item (frontend link to `/item/{id}`), dismiss.
4. `detect_scam_pattern_channels` — channels where `trust_score <= RADAR_SCAM_CHANNEL_MAX_TRUST` AND at least one active item whose price ≥ `RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X` × the item's category median AND channel-level report count ≥ `RADAR_SCAM_CHANNEL_MIN_REPORTS`. Category medians via `func.percentile_cont(0.5).within_group(Item.price)` — the verified stats.py L154–155 pattern — computed over active, priced items per category. One anomaly per channel, severity high, entity_id = channel id. Actions: pause indexing (`POST /ops/radar/channels/{id}/pause`), ban owner (`POST /ops/users/{owner_tg}/ban` — the Package-2 endpoint), dismiss.
5. `detect_price_anomalies` — items with `price == 0` (medium) or `price >= RADAR_PRICE_ANOMALY_MAX_X_MEDIAN` × category median (high; median across the category's active priced items; items with no computable median are skipped). entity_id = item id. Actions: hide item (`POST /ops/radar/items/{id}/hide`), dismiss.
- `get_radar(db) -> {generated_at, anomalies: [...]}` — runs all five, drops dismissed (type, entity_id) pairs, returns the merged list.
- `is_dismissed(db, type, entity_id) -> bool` and `dismiss(db, type, entity_id)` over the `radar_dismissals` table.

**3.3 `RadarDismissal` model + migration.** `radar_dismissals` — `id` PK, `type VARCHAR NOT NULL`, `entity_id VARCHAR NOT NULL`, `dismissed_by VARCHAR`, `created_at`, `UNIQUE (type, entity_id)`. Migration in main.py in the TECH-32 style (CREATE TABLE IF NOT EXISTS + unique constraint inline). Dismissals are ops state — a tiny honest table, not an audit row (audit records the dismissal action; the table records the state).

**3.4 Notification FAILED instrumentation (honest gap closure — verified prerequisite).** Nothing in the codebase writes `status="FAILED"` today: models.py L108 documents the status; cleanup.py L176 purges it; the poller (listener/notifications.py L49–156) logs failures and retries PENDING forever. Without this closure the dead-chat detection would read an always-empty table — fabricated honesty. Close it:
- `backend/api/routes/notifications.py` gains `POST /{notification_id}/fail`: 404 when missing; when status is PENDING → set FAILED, commit, return `{status: "failed"}`; when already SENT/REPLACED/FAILED → 409. Unauthenticated, mirroring `/ack` (the poller is the machine caller).
- `listener/notifications.py`: process-local consecutive-failure counter `{notification_id: int}`; on delivery failure increment, on success clear; when a notification reaches `NOTIFICATION_FAILURE_LIMIT` (listener/config.py new constant, env `NOTIFICATION_FAILURE_LIMIT`, default 3) → call the new `mark_notification_failed(notification_id)` and clear the counter. Behavior preserved for transient failures (retry from PENDING); genuinely dead chats land as FAILED rows within ~15s. `listener/client.py` gains `mark_notification_failed(notification_id)` mirroring `ack_notification` (L144–153).

**3.5 Radar action endpoints (ops_finalize.py, all `require_ops_admin` + audit):**
- `POST /ops/radar/resolve` — body `{type, entity_id}` → dismiss row + audit.
- `POST /ops/radar/items/{id}/clear-reports` — **directly deletes SoldReport rows** for the item + audit. Verified drift: `item_status.clear_reports` is owner-gated (L186–191); the admin verb is an enforcement action, not the owner flow — it bypasses the service and is documented as such.
- `POST /ops/radar/channels/{id}/pause` — sets `channel.indexing_paused = True` + audit. Verified: the worker gate (worker.py L37–41) honors this flag; the channels route's toggle is owner-authorized, so the admin action sets the flag directly.
- `POST /ops/radar/items/{id}/hide` — sets `item.status = "removed"` AND `item.is_active = False` + audit. Verified: search filters `status == 'active'` (search.py L85), catalog filters both (catalog.py L28–32), feed filters `status == 'active'`; the "removed" status is already in the model's lifecycle vocabulary (models.py L229).
- Retry and ban reference the shared endpoints in §5.2 and §2.4 — one endpoint per verb, never duplicated.

### Package 4 — TECH-43 / NB-58: Engine Diagnostics

**4.1 `backend/services/trace.py` (new) — side-effect-free pipeline replay (locked: duplication of the per-alert stages is the chosen honesty; instrumenting `process_new_item` with a trace mode is rejected as riskier).**
`build_item_trace(db, item_id, now=None) -> dict`:
- Loads the item (404 when missing), its vector (`image_vector` → list, alerting.py L58–64 conversion), and all active alerts (`Alert.is_active == True`, alerting.py L67).
- For each alert, replays the pipeline stages as pure logic — **no `_dispatch_notification`, no `_create_system_notification`, no `_apply_auto_pause`, no `best_opportunity_score` mutation, no judge counter increment**:
  1. Expiry check (same comparison as alerting.py L172–184, read-only) → outcome `expired`.
  2. Price gate (alerting.py L190–201) → outcome `price_gate`.
  3. `evaluate_match` (same call + vector conversion as alerting.py L80–96) → tier MISS → outcome `threshold_miss`; else record score/tier.
  4. Judge stage (only when not `speed_pass`): `verify_match_with_llm(item.title, alert.query_text, preferences)` → `judge_rejected` | `judge_errored` | `unknown_verdict` (the defensive fail-closed branch, alerting.py L128–132) | continue on approved. **The LLM call is the only external side effect — identical to the real pipeline's call; acceptable.**
  5. Dispatch decision: BULLSEYE → candidate; RING → compare score against the STORED `best_opportunity_score` (pure read) → `high_water_suppressed` or candidate.
  6. Throttle (read `last_triggered_at` + `NOTIFICATION_THROTTLE_SECONDS`) → `throttled`.
  7. Dedup/duplicate suppression — the same read-only Notification existence queries as alerting.py L243–269 → `dedup_suppressed`.
  8. Else → `dispatched`. Speed-pass matches (MatchResult.speed_pass) record outcome `speed_pass` with score 1.0 / tier BULLSEYE, reason noting the judge skip.
- Stage record: `{alert_id, query_text, outcome, score, tier, reason}`. Response: `{item_id, generated_at, alerts_evaluated, stages: [...]}`. The outcome enum is the locked nine plus `expired` and `unknown_verdict` (additive — the trace reflects the real pipeline; omitting them would fabricate). Error modes: unknown item → 404; the whole trace never mutates the DB session (no commit).
- Imports it needs: `evaluate_match`, `MatchTier`, `verify_match_with_llm`, `JudgeVerdict`, `RING_TOLERANCE`, `NOTIFICATION_THROTTLE_SECONDS`, `Alert`, `Item`, `Notification`, `select`, `timedelta`.

**4.2 Endpoint.** `GET /ops/diagnostics/items/{item_id}/trace` (`require_ops_admin`) → `build_item_trace`.

### Package 5 — TECH-44 / NB-59: Engine Actions

**5.1 Endpoints (ops_finalize.py, every action: `require_ops_admin`, confirm in the UI, audit row, result feedback):**
- `POST /ops/actions/items/{item_id}/reprocess` — `process_new_item(db, item_id)` + audit. Idempotent: the pipeline's duplicate suppression (alerting.py L243–269) and throttle guard re-dispatch; documented.
- `POST /ops/actions/notifications/{id}/retry` — when status is FAILED → set PENDING + audit (the poller picks it up via `/pending`); when PENDING → 409 "already pending"; when SENT/REPLACED → 409 "terminal". Shared by the radar.
- `POST /ops/actions/reconcile` — `asyncio.run(reconcile_star_payments(db))` + `record_scheduler_run(db, scheduler="reconciliation", ...)` + audit — the exact ops_payments.py L84–113 run-now pattern, consolidated here.
- **Dropped from v1 (documented, not implemented):** re-process ingestion post — the listener queue is in-memory (`asyncio.Queue`, worker.py L9); no persisted TelegramPost payload exists in the DB, so there is nothing to re-process; UI copy states this. Trigger photo-refresh — the refresher runs inside the listener (listener/photo_refresher.py; heartbeat payload client.py L29); the only backend→listener signal is the one-way heartbeat row; no command seam exists; v1 UI copy tells the operator to restart the listener; a command table is a future package.

**5.2 Shared verb registry.** Radar actions reference the §5.1 endpoints where the verb is the same (retry) — one endpoint per verb, never duplicated.

### Package 6 — TECH-45 / NB-60: Users & Items Analytics

**6.1 `GET /ops/users/{telegram_id}/footprint`** — `{user: {telegram_id, username, banned}, reviews: {total, rating_distribution: {"1".."5": n}, recent: [{channel_id, channel_username, rating, comment, created_at}]}, alerts: {active, total}, subscriptions: {active, product}, boosts: {total, active}, interactions: {counts_by_type: {...}, recent_50: [...]}}`. All joins verified queryable by `user.id` (Review/Alert/Subscription/Boost/UserInteraction all carry users FKs).

**6.2 `GET /ops/items/analytics`** — three blocks:
- `views_over_time`: last 14 days, two series — aggregate daily views and per-item daily views for the top-20 items by total views; views = `user_interactions` with `interaction_type IN ("view_item", "view_item_card")` (the verified `VIEW_INTERACTION_TYPES`, stats.py L24–25), grouped by `created_at::date`.
- `price_distribution`: per category, histogram buckets over active priced items (bucket edges: 0–1k, 1k–5k, 5k–20k, 20k–100k, 100k+; bucket constants documented in the route).
- `per_channel`: per active channel — item count, view count, sold-report count.
**6.3 No per-item trace reuse, no reclassification workbench (rejected by §8 of the behavior doc).**

---

## 3. Strict Import Map (additive-only; every moved/created symbol listed with its exact absolute import)

**`backend/services/ban.py` (new)** — imports: `from models import User, Channel`; `from sqlalchemy import exists, select`; `from fastapi import HTTPException`. Exports: `is_banned`, `ban_user`, `unban_user`, `is_channel_banned`, `owner_banned_pred`.

**`backend/services/radar.py` (new)** — imports: `from sqlalchemy import select, func, exists`; `from sqlalchemy.orm import Session`; `from models import Notification, User, Item, Channel, SoldReport, RadarDismissal`; `from constants import CROWDSOURCE_SOLD_THRESHOLD, RADAR_SCAM_CHANNEL_MAX_TRUST, RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X, RADAR_SCAM_CHANNEL_MIN_REPORTS, RADAR_PRICE_ANOMALY_MAX_X_MEDIAN, RADAR_DEAD_CHAT_SEVERITY_MEDIUM, RADAR_DEAD_CHAT_SEVERITY_HIGH`; `from services import alerting` (module attribute reads); `from datetime import datetime, timezone, timedelta`. Exports: `get_radar`, `is_dismissed`, `dismiss`, `detect_dead_chat_buyers`, `detect_judge_error_spikes`, `detect_report_spikes`, `detect_scam_pattern_channels`, `detect_price_anomalies`.

**`backend/services/trace.py` (new)** — imports: `from datetime import datetime, timezone, timedelta`; `from sqlalchemy.orm import Session`; `from sqlalchemy import select`; `from models import Alert, Item, Notification`; `from ai_engine.matcher import evaluate_match, MatchTier`; `from ai_engine.llm_client import verify_match_with_llm, JudgeVerdict`; `from constants import RING_TOLERANCE, NOTIFICATION_THROTTLE_SECONDS`; `import json`. Exports: `build_item_trace`.

**`backend/api/routes/ops_finalize.py` (new)** — imports: `import asyncio, json, logging`; `from datetime import datetime, timezone`; `from fastapi import APIRouter, Depends, HTTPException, Request`; `from sqlalchemy.orm import Session`; `from sqlalchemy import select, func, delete`; `from database import get_db`; `from models import Item, ItemEdit, User, Channel, Notification, SoldReport, Review, Alert, Subscription, Boost, UserInteraction`; `from schemas import ItemEditResponse`; `from services.audit import record_audit`; `from services.ban import is_banned, ban_user, unban_user, is_channel_banned`; `from services.radar import get_radar, dismiss`; `from services.trace import build_item_trace`; `from services.alerting import process_new_item`; `from services.reconciliation import reconcile_star_payments`; `from services.scheduler_runs import record_scheduler_run`; `from constants import CROWDSOURCE_SOLD_THRESHOLD, WEB_APP_URL`; `from .ops_auth import require_ops_admin`.

**`backend/api/routes/internal.py` (additive)** — add `Item, ItemImage` to `from models import ListenerHeartbeat` (→ `from models import Item, ItemImage, ListenerHeartbeat`). Header import already present.

**`backend/api/routes/notifications.py` (additive)** — no new imports (the fail endpoint uses existing `select`, `HTTPException`, `Session`).

**`backend/models.py` (additive)** — `banned = Column(Boolean, default=False, nullable=False)` on User; new `RadarDismissal` class (Boolean, Integer, String, DateTime, func all already imported at L1–3).

**`backend/main.py` (additive)** — extend line 16's import: add `ops_finalize` to the ops router tuple; register `app.include_router(ops_finalize.router, prefix="/ops", tags=["Ops"])` after line 637; two new migration blocks (users.banned; radar_dismissals).

**`backend/services/alerting.py` (additive)** — top-level `from fastapi import HTTPException` (replace the in-branch import at L315 — the cap-branch import can stay or move to top; move it top-level, one import site); `from services.ban import is_banned`.

**`backend/api/routes/reviews.py` (additive)** — `from services.ban import is_banned`.

**`backend/api/routes/items.py` (additive)** — `from services.ban import is_banned`.

**`backend/api/routes/ingestion.py` (additive)** — `from services.ban import is_channel_banned`.

**`backend/services/catalog.py` (additive)** — `from services.ban import owner_banned_pred`. (Locality note: this is the first cross-service import into the deliberately Local-substitutable module — accepted and documented; the deletion test passes: without it, banned sellers' items surface in browse.)

**`backend/services/recommendation.py` (additive)** — `from services.ban import owner_banned_pred`; `from sqlalchemy import exists` NOT needed (predicate arrives ready-made).

**`backend/services/search.py` (additive)** — none (raw SQL inline clause).

**`backend/services/boost.py` (additive)** — `from services.ban import owner_banned_pred`.

**`backend/services/item_status.py` (additive)** — none (flag extension only).

**`backend/constants.py` (additive)** — the six radar constants via the existing `_get_config` helper.

**`listener/config.py` (additive)** — `NOTIFICATION_FAILURE_LIMIT: int = int(os.getenv("NOTIFICATION_FAILURE_LIMIT", "3"))`.

**`listener/client.py` (additive)** — `get_item_api` and `mark_notification_failed`; imports already present (httpx, API_BASE, INTERNAL_HEADERS).

**`listener/notifications.py` (additive)** — extend line 6's client import: `from client import get_pending_notifications, ack_notification, mark_notification_failed`; `from config import ..., NOTIFICATION_FAILURE_LIMIT`.

**`listener/worker.py` (additive)** — extend line 4: `from client import send_to_api, get_channel_info, get_item_api`.

**Frontend** — `frontend/src/pages/OpsConsole.jsx` (additive): imports for OpsQuality, OpsRadar, OpsUsers, OpsAlertsEngine; renderSection cases for `catalog`, `trust`, `users`, `alerts`. New sections import `import { opsFetch } from '../utils/opsApi';` and the kit: `OpsTable`, `OpsEmptyState`, `OpsConfirmDialog` from `../components/ops/`; toasts via the `setToast` prop (OpsConsole L154). New files: `frontend/src/sections/OpsQuality.jsx`, `OpsRadar.jsx`, `OpsUsers.jsx`, `OpsAlertsEngine.jsx` (+ internal sub-view files `OpsDiagnostics.jsx`, `OpsActions.jsx`, `OpsItems.jsx` or sub-components inside the section files — architect's call: separate files per sub-view, consistent with the sections/ directory convention).

---

## 4. Execution Steps (six atomic commits; each with its QA gate, per tech-backlog.md)

**Commit 1 — `feat: owner quality loop — edit DM, category re-trigger, quality events (NB-55)`**
1. Add `GET /internal/items/{item_id}` to internal.py (internal-header gate, shape §1.1).
2. Add `get_item_api` to listener/client.py; extend worker.py success branch per §1.2 (rich body, photo-message replacement, Edit + Boost buttons, fetch-failure fallback).
3. Extend `update_item` category/subcategory blocks to set `needs_reprocess` (§1.3).
4. Create ops_finalize.py with `GET /ops/quality/events` and `POST /ops/quality/events/{id}/revert` (§1.4, including the console-admin sentinel User and the revert re-trigger).
5. Register ops_finalize in main.py; create OpsQuality.jsx; wire `case 'catalog'` in OpsConsole.jsx (label "Catalog" unchanged).
6. Tests: see §5.1.

**Commit 2 — `feat: ban primitive — five enforcement seams (NB-56)`**
1. User.banned model + main.py migration.
2. Create ban.py (§2.2).
3. Apply the six call sites (§2.3).
4. Users status/ban/unban endpoints (§2.4); create OpsUsers.jsx (lookup + footprint counts + ban/unban); wire `case 'users'`.
5. Tests: §5.2.

**Commit 3 — `feat: anomaly radar — computed problems with action chaining (NB-57)`**
1. Radar constants; RadarDismissal model + migration.
2. FAILED instrumentation: fail endpoint (notifications.py), listener counter + mark_notification_failed (client.py, notifications.py, config.py).
3. Create radar.py (§3.2); radar endpoints + action endpoints (§3.5).
4. Create OpsRadar.jsx; wire `case 'trust'` (label "Trust & Moderation" unchanged).
5. Tests: §5.3.

**Commit 4 — `feat: engine diagnostics — per-item decision traces (NB-58)`**
1. Create trace.py (§4.1); `GET /ops/diagnostics/items/{item_id}/trace`.
2. Create OpsAlertsEngine.jsx with the Diagnostics sub-view (item input + trace table + drill-down); wire `case 'alerts'` (label "Alerts & Notifications" unchanged).
3. Tests: §5.4.

**Commit 5 — `feat: engine actions — re-run, retry, trigger (NB-59)`**
1. The three action endpoints (§5.1) with confirm/audit/feedback; dropped-verb copy documented in the UI.
2. Add the Actions sub-view to OpsAlertsEngine.jsx.
3. Tests: §5.5.

**Commit 6 — `feat: users & items analytics tabs (NB-60)`**
1. Footprint + items-analytics endpoints (§6.1–6.2).
2. Complete OpsUsers.jsx (footprint + rating-distribution chart + counts grid); add OpsItems.jsx as the "Analytics" sub-tab inside OpsQuality.jsx (two-tab layout: Events | Analytics).
3. Tests: §5.6.

---

## 5. Testing Strategy

**5.1 NB-55.** `backend/tests/test_quality_events.py` — events list shape (fields per §1.4, joined title/username, ordering); revert restores each field type (price float, specs JSON, category, NULL old_value), writes a second ItemEdit, writes the audit row, and re-triggers matching (notification appears for a seeded alert — the test_tech23.py L710 retrigger pattern). `backend/tests/test_worker_dm.py` — new file: prepend `listener/` to sys.path, stub the `telegram` module (InlineKeyboardButton/InlineKeyboardMarkup/WebAppInfo minimal classes), monkeypatch `client.get_item_api` and the bot; assert: Edit + Boost buttons present in reply_markup with the exact `/stores/{channelId}/{itemId}` URL, body contains description + spec summary, both is_replaced variants; fetch-failure falls back to text + boost button; photo path taken when image present.

**5.2 NB-56.** `backend/tests/test_ban.py` — create_alert 403 for banned / 200 after unban; review submission 403; report-as-sold 403; ingestion 403 for banned-owner channel and 200 for ownerless/clean channels; banned seller's items absent from search SQL, browse, all five feed paths, and the pinned-boost layer; unban → all reappear; ownerless channels' items remain visible; ban/unban endpoints + audit rows (ops-client pattern, test_ops_tools.py L25–43).

**5.3 NB-57.** `backend/tests/test_radar.py` — each detection fires on seeded data (FAILED notifications; monkeypatched `alerting.JUDGE_ERROR_COUNT`/`LAST_TS`; near-threshold reports; low-trust+outlier+report channel with seeded median; 0-price and ≥10×-median items); each action executes (retry flips FAILED→PENDING; clear-reports deletes rows without the owner gate; pause sets indexing_paused; hide sets status removed + is_active False; ban owner via §2.4); dismiss persists across `get_radar` calls; the fail endpoint 200-on-PENDING/409-on-terminal; listener poller marks FAILED after NOTIFICATION_FAILURE_LIMIT consecutive failures (monkeypatched client) and retries below the limit.

**5.4 NB-58.** `backend/tests/test_trace.py` — seeded item + alerts yield the expected per-stage outcomes (price_gate, expired, threshold_miss, judge_rejected/judge_errored with monkeypatched `verify_match_with_llm`, high_water_suppressed, throttled with patched NOTIFICATION_THROTTLE_SECONDS, dedup_suppressed, dispatched, speed_pass); side-effect-free assertions: zero Notification rows created, JUDGE_ERROR_COUNT unchanged, `best_opportunity_score` unchanged, no alert rows mutated; 404 for unknown item.

**5.5 NB-59.** `backend/tests/test_ops_actions.py` — reprocess invokes `process_new_item` (spy) and runs twice safely; retry flips FAILED→PENDING with audit, 409 on PENDING/SENT; reconcile invokes `reconcile_star_payments` and records the scheduler run; audit rows written for every action.

**5.6 NB-60.** `backend/tests/test_ops_footprint_analytics.py` — footprint shape from a seeded user (ratings 1–5 distribution, alert/subscription/boost counts, interaction counts + recent 50); analytics shapes from seeded items/interactions/reports (14-day series, per-category buckets, per-channel aggregation).

**Frontend regression:** extend `frontend/src/__tests__/OpsConsole.test.jsx` to assert the four sections render their real components; per-section tests assert verbs call opsFetch (pattern per existing OpsOverview/OpsPayments tests).

---

## 6. Rollout Notes

- **Migration order (main.py, both idempotent):** `users.banned` (ALTER TABLE ADD COLUMN IF NOT EXISTS) and `radar_dismissals` (CREATE TABLE IF NOT EXISTS with UNIQUE(type, entity_id)). Startup is safe on fresh and existing DBs.
- **ItemEdit revert semantics:** revert writes a new ItemEdit row (revert is an event, Rule 2.1); `edited_by` = the reserved console-admin User sentinel (telegram_id −1, username = current admin), documented in code; reverts re-trigger matching on price/specs/category/subcategory.
- **Honest-v1 decisions (locked, documented in the UI copy):** photo-refresh trigger dropped (listener-bound, no backend→listener command seam); re-process-stuck-post dropped (in-memory queue, no persisted payload); judge-error-spike resolution is dismiss-only (no pause-matching kill switch exists); dead-chat detection required closing the FAILED-status instrumentation gap (poller marks terminal after 3 consecutive failures — retry preserved).
- **Enforcement-vs-owner drift (documented):** the radar's clear-reports verb deletes SoldReport rows directly (the service is owner-gated); the radar's pause-indexing verb sets the flag directly (the route is owner-gated); hide = status "removed" + is_active False (search/feed filter on status, browse on both).
- **Banned-seller semantics:** one flag, zero derived state — unban restores instantly (queries re-read the flag); banned sellers keep their rows and can still manage their own listings' evidence state (owner edit/relist/clear are NOT enforcement seams in v1 — documented); existing reviews stay visible (historical evidence). Banned BUYER alerts still match other sellers' items; the ban blocks the buyer from CREATING new alerts — existing alerts continue to fire (the behavior doc Rule 3.2 says "existing active alerts pause" — v1 implementation: alert creation blocked; alert DISPATCH for banned buyers is NOT a specified seam, documented as a future seam if the operator demands it — the five locked seams are the contract).
- **Section-label mapping (final, shell shape unchanged — ops-console.md Rule 1.6):** "Catalog" → OpsQuality (Events + Analytics sub-tabs, P1 + P6); "Trust & Moderation" → OpsRadar (P3); "Users" → OpsUsers (ban lever + footprint, P2 + P6); "Alerts & Notifications" → OpsAlertsEngine (Diagnostics + Actions sub-views, P4 + P5). Labels stay; content changes once.
- **Registry keys:** the radar constants are plain env-overridable constants in v1 (architect's call) — a settings-registry pass is a future package if the operator wants live radar tuning.

---

## Section list (this blueprint)

1. Architecture Context · 2. The New Interfaces (six packages) · 3. Strict Import Map · 4. Execution Steps (six atomic commits) · 5. Testing Strategy · 6. Rollout Notes.

## Drift found (verified against main @ f22d140)

1. **ItemEdit columns** — `id, item_id, field, old_value, new_value, edited_by (FK users.id NOT NULL), timestamp` (models.py L270–285). The timestamp column is **`timestamp`**, not `created_at` as the locked design assumed; `edited_by` is NOT NULL, forcing the console-admin sentinel-user solution for reverts. `ItemEditResponse` schema already exists (schemas.py L308).
2. **IngestionResponse shape** — `{status, item_id, extracted_data: Dict, error, replaced}` (schemas.py L133–138); `extracted_data` has no image and no normalized item record; the worker's `send_to_api` returns only success/item_id/title/price/replaced. The DM image/specs/description **require a new internal item fetch** — no internal item endpoint exists (internal.py has only the heartbeat). New `GET /internal/items/{item_id}` specified.
3. **Channel.registered_by type** — plain `BigInteger` storing the owner's **Telegram id**, not an FK (models.py L135; main.py L283–284). The join must be `users.telegram_id = channels.registered_by`; the architect's proposed `u.id = channels.registered_by` join would be wrong. NOT EXISTS / `exists()` predicates are NULL-safe (ownerless channels stay visible, Rule 1.4). Extra seam found: the **pinned-boost layer** (`get_pinned_boosted_items`) queries items independently and would re-surface banned sellers — added as the sixth call site.
4. **Notification failure recording** — **nothing writes FAILED** today (models comment only; cleanup purges it; the poller retries PENDING forever). The dead-chat detection required closing this gap: a `POST /notifications/{id}/fail` endpoint + poller-side consecutive-failure marking after `NOTIFICATION_FAILURE_LIMIT` (default 3).
5. **OpsConsole section registry** — SECTIONS ids/labels: `catalog`/Catalog, `trust`/Trust & Moderation, `users`/Users, `alerts`/Alerts & Notifications (OpsConsole.jsx L17–28); stub switch at L170–188. Mapping per the locked design; the shell has **no Items stub** — items analytics lands as a sub-tab in the Catalog section (OpsQuality).
6. **update_item re-trigger condition** — `needs_reprocess` is set only by price (L260) and specs (L281); category (L262–264) and subcategory (L266–268) log ItemEdit but don't re-trigger. Extension confirmed; `process_new_item` call at L289.
7. **Photo-refresh / re-process feasibility** — **not feasible honestly in v1**: photo refresher runs in the listener (one-way heartbeat is the only signal); ingestion posts aren't persisted. Both dropped with documented UI copy.
8. **Side-effect-free replay feasibility** — **feasible**: the pipeline's stages are separable pure checks (verified against alerting.py L47–352); only the LLM judge call is external (identical to the real path). `services/trace.py` mirrors the stages as data with no mutations; the outcome enum gains two additive outcomes (`expired`, `unknown_verdict`) beyond the locked nine.
9. **Secondary drifts discovered** — radar "clear reports"/"pause indexing" verbs are blocked by owner-gated services and must act directly with audit (documented); "hide item" must set `status='removed'` + `is_active=False` (search/feed filter on status alone); the report-spike and scam-channel detections reuse the verified `percentile_cont` median pattern (stats.py L154–155) and `CROWDSOURCE_SOLD_THRESHOLD` (constants.py L103); `VIEW_INTERACTION_TYPES` exists (stats.py L24–25) for the analytics package.

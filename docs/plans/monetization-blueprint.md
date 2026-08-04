# Monetization Blueprint — Boost, Subscriptions & Seller Intelligence (NB-43..NB-47)

**Date:** 2026-08-04
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture
**Authority:** `docs/behaviors/monetization.md` (all 9 sections, locked); tickets NB-43..NB-47 in `docs/behaviors/pending-behaviors.md`; cross-refs `alert-guardrails.md`, `dedup-redesign.md`, `processing-store-management.md`, `inventory-management.md`.

---

## 0. Verified State & Drift (line-anchored, verified 2026-08-04)

Every anchor below was read directly from the working tree. Where the locked architecture decisions differ from the current file state, the resolution is stated and LOCKED here — @build must not re-litigate.

| # | Area | Verified fact | Line anchor |
|---|------|---------------|-------------|
| D1 | **PTB version drift** | `listener/requirements.txt` is UNPINNED (`python-telegram-bot`). Installed in `index_listener` container: **python-telegram-bot 22.8 = Bot API 10.0**. Locked decision assumed `Update.subscription` (Bot API 10.2) — **it does not exist in 22.8**. Verified: `Update.de_json` captures unknown `subscription` key into `update.api_kwargs['subscription']`; `filters.StatusUpdate` has NO subscription member; `filters.StatusUpdate.REFUNDED_PAYMENT` exists; `PreCheckoutQueryHandler`, `filters.SuccessfulPayment`, `create_invoice_link` (with `subscription_period` int-seconds param), `answer_pre_checkout_query`, `get_star_transactions`, `get_my_star_balance`, `edit_user_star_subscription` (added 21.8) ALL exist. `Update.ALL_TYPES` has no `SUBSCRIPTION`. | `listener/requirements.txt:1`; runtime check `docker exec index_listener pip show python-telegram-bot` → 22.8 |
| D2 | **Subscription-update seam** | RESOLUTION (locked): do NOT upgrade PTB in this build. Handle `BotSubscriptionUpdated` via a catch-all `TypeHandler(Update, ...)` registered LAST in `listener/main.py`, reading `update.api_kwargs.get('subscription')` (a dict with keys `user`, `invoice_payload`, `state`). Verify payload at runtime; guard with `if not isinstance(...) or 'state' not in ...: return`. | verified: `Update.de_json` api_kwargs capture |
| D3 | **Alert cap check lives in TWO places** | Duplicated guard: `backend/api/routes/alerts.py` `create_new_alert` lines 32-44 AND `backend/services/alerting.py` `create_alert` lines 285-299. BOTH compare against `MAX_ALERTS_PER_USER` (constants.py:55, default 20, env `ALERT_MAX_PER_USER`). RESOLUTION: both call sites delegate to `get_effective_alert_cap(db, user)` from the new subscriptions module. | `alerts.py:33-44`; `alerting.py:287-299` |
| D4 | **`_get_config` cannot parse dicts** | `_get_config(key, default, cast)` handles int/float with dedicated branches (constants.py:34-39); the generic `cast(raw)` fallback exists but the negative clamp at lines 47-49 (`if val < 0`) is meaningless for dicts. RESOLUTION (locked): add a new `_get_json_config(key, default)` helper (json.loads, warn-and-fallback on error, NO clamp) for `BOOST_PRICE_STARS`. | `constants.py:21-51` |
| D5 | **Backend calls Telegram directly (no PTB dependency)** | `backend/requirements.txt` has NO python-telegram-bot. House pattern: raw httpx to `https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/...` — `services/owner_dm.py` (sendMessage), `api/routes/channels.py:100-118` (getFile), `api/routes/ingestion.py:103-122` (getChat). RESOLUTION: the backend Star-payment adapter uses the same raw-httpx pattern; invoice payloads are plain JSON, never PTB objects. | `owner_dm.py:25,49-53` |
| D6 | **Listener→backend auth seam** | `listener/client.py:5` `INTERNAL_HEADERS = {"X-Internal-Service": "index-listener"}`; backend `services/auth.py:43-104` `authenticate(init_data, db, x_internal_service)` supports the internal bypass when header == "index-listener" and init_data is a digit telegram_id. All new internal fulfillment endpoints MUST use this seam (init_data = user telegram_id + header). | `client.py:5,54`; `auth.py:62-68` |
| D7 | **Category browse is not a separate endpoint** | Category browse is `POST /search/` with `category` in the body (`frontend/src/hooks/useShop.js:178-180` sets `body.category`; route `api/routes/search.py:27-35` passes it to `perform_hybrid_search`, filtered post-SQL at `services/search.py:179`). RESOLUTION: ONE application point for the boost pin — the `/search/` route. The For You feed (`api/routes/feed.py` → `services/recommendation.py`) is NEVER touched. | `useShop.js:168-202`; `search.py` (service):176-180 |
| D8 | **Search SQL lacks exclusion seam** | `_execute_search_sql` (services/search.py:14-141) has no exclude-ids clause; organic results are sliced at `perform_hybrid_search` lines 174-183 AFTER fetching limit+10. RESOLUTION: add ADDITIVE optional param `exclude_item_ids` threaded into `perform_hybrid_search` → `_execute_search_sql` (SQL `AND i.id NOT IN (...)` when non-empty). Relevance math untouched. | `search.py:14,143,172` |
| D9 | **View interaction types** | Views are logged as `interaction_type='view_item'` (server, `api/routes/items.py:79`) and `'view_item_card'` (client, `ItemCard.jsx:36` via `logEvent`). DB default is `'view'` (models.py:37). RESOLUTION: stats count `interaction_type IN ('view_item','view_item_card')` — the two explicit view events. | `items.py:79`; `ItemCard.jsx:35-37` |
| D10 | **Processing DM is text-only today** | `listener/worker.py:98` `await dm_message.edit_text(edit_text)` — no reply_markup. The boost button must be added via `edit_text(..., reply_markup=...)`. Worker already has `result['item_id']` (client.py:23) and `channel_info['id']`. Deep-link precedent: `listener/notifications.py:136` `f"{WEB_APP_URL}/item/{item['id']}"` via `WebAppInfo`. | `worker.py:81-107`; `notifications.py:20-24,136` |
| D11 | **No Stores deep-link route exists** | `frontend/src/App.jsx` routes only `/welcome` and `/*` (MainLayout); StoresPage is a tab gated by local `activeTab` state. RESOLUTION: new route `/stores/:channelId/:itemId` → MainLayout forces `activeTab='stores'` and passes the pair down to StoresPage → ChannelInventory → ProductEditPanel. | `App.jsx:18-54,105-112` |
| D12 | **Top-level category keys** | Frontend `TAXONOMY` has 19 top-level keys (taxonomy.js:1-20). CONTEXT.md:228 lists a legacy family name ("Mobile Phones & Tablets") that is NOT a taxonomy.js key — AI extraction may emit it. RESOLUTION: `BOOST_PRICE_STARS` lookup = exact key match, else floor (`Other`, default 25 Stars). Unknown categories get the floor — safe default, no crash. | `taxonomy.js:1-20`; `CONTEXT.md:228` |
| D13 | **Dedup transfer hook point** | `api/routes/ingestion.py:176-189` soft-deletes `best_match` and sets `was_replaced`; new item created at lines 204-219, `db.commit()` at line 231. RESOLUTION: boost transfer executes after the new item flush (before line 231 commit) so it commits atomically with the replacement. | `ingestion.py:176-231` |
| D14 | **Sold/reported_sold hook points** | `services/item_status.py`: `mark_sold` sets status at line 165; `report_sold` threshold flip at lines 97-100. `relist_item` (line 144) resets to active — boost stays ended (Rule 6.1: no refund, no revival). | `item_status.py:97-100,144,165` |
| D15 | **Stats endpoints today** | `GET /items/stats` (items.py:25-43) is marketplace-wide counts — NOT owner analytics. No owner stats endpoint exists. Owner hooks today: `GET /channels/mine` (channels.py:124-162), `GET /channels/{id}/items` (channels.py:340-399). | `items.py:25-43`; `channels.py:340-399` |

---

## 1. Architecture Context

### 1.1 The friction

Monetization is the first revenue feature on a codebase that has never handled money. Three structural facts shape everything:

1. **The update stream is single-owner.** One bot, long-polling (`listener/main.py:72` `application.run_polling()`), receives channel posts, buyer commands, AND — after this build — `pre_checkout_query`, `successful_payment`, and `subscription` updates on the same stream. Webhook and getUpdates are mutually exclusive; long-polling stays. The 10-second `pre_checkout_query` deadline means the payment handler must be a **zero-work passthrough** — the serial ingestion worker's `HEARTBEAT_INTERVAL` sleeps (`worker.py:78,116`) must never gate it. PTB dispatches each update to its handler independently of the `background_worker` asyncio task, but the pre-checkout handler itself must do nothing but `answer(True)`.
2. **Telegram is a True external dependency.** The backend has no PTB package (D5) and reaches Telegram over raw httpx. The listener owns the update stream via PTB objects. The result: TWO adapters at the Telegram seam, one per process, both driven by `TELEGRAM_BOT_TOKEN`.
3. **The cap is duplicated.** The alert cap is enforced in two places (D3). Any subscription that raises the cap must change BOTH — this is the locality problem the blueprint solves by introducing one cap-resolution module.

### 1.2 The new seam (locked)

```
Frontend (Mini App)          Backend                      Telegram            Listener (PTB)
─────────────────            ───────                      ────────            ──────────────
boost UI ── quote ──►    GET /items/{id}/boost-quote
            ◄─────────   {price_stars}                                   
Boost with Stars ──►    POST /items/{id}/boost-order ──createInvoiceLink──►   (invoice)
            ◄─────────   {invoice_url, payload}                              
Telegram.WebApp.openInvoice(url) ──────────────────────────────────────────►   buyer pays
                                                    pre_checkout_query ──►  answer(True) ≤10s
                                                    successful_payment ──►  POST /internal/payments/fulfill-*
            ◄─ poll ──  GET /items/{id}/boost-quote  ◄── (activation, idempotent on telegram_payment_charge_id)
```

- The **listener owns the Telegram update stream** (interface: PTB objects). It translates payment updates into backend calls over the internal seam (D6).
- The **backend owns all fulfillment** (boost activation, subscription records, alert-cap math, dashboard gating, invoice creation).
- Fulfillment is **idempotent on `telegram_payment_charge_id`** — replaying a `successful_payment` must not double-activate. The DB unique constraint on `telegram_payment_charge_id` is the enforcement; the service returns the existing record on replay.

### 1.3 Dependency categories (skill vocabulary)

| Module | Category | Test strategy |
|--------|----------|---------------|
| `services/telegram_payments.py` (adapter seam) | **True external** — Telegram. Injected port; the httpx implementation is one adapter, the fake is the second (real seam). | `FakeStarPaymentsAdapter` in tests; assert on observable outcomes |
| `services/boost.py`, `services/subscriptions.py`, `services/stats.py` | **Local-substitutable** — SQLAlchemy Session over the local Postgres (`suq_test_db` via conftest `db_session`). | In-process tests via the conftest fixture (D-pattern: same physical DB, seed through fixture) |
| `api/routes/*` route modules | Interface-stable **thin adapters** — auth seam (D6) + delegation. Deletion test: removing a route leaves all logic in the services; routes earn their keep only as the HTTP surface. | Route tests via the service interfaces; auth exercised with the existing `authenticate` pattern |
| `listener/payments.py` + `client.py` additions | **Adapter** over the PTB update stream and the backend HTTP seam. | Mocked via fake update objects + monkeypatched `client` functions; no Telegram network in tests |
| Frontend modules | Presentation adapters over the new endpoints. | Manual + build-verification; no unit framework mandated beyond existing patterns |

---

## 2. The New Interfaces

### 2.1 `backend/services/telegram_payments.py` — the Star-payments adapter seam (module: `StarPaymentsAdapter` port)

Everything the backend needs from Telegram money-wise lives behind this interface. The listener does NOT import it — the listener speaks PTB objects natively. The backend implementation is raw httpx (D5).

```
class StarPaymentsAdapter (Protocol):
    async def create_invoice_link(self, *, title: str, description: str,
                                  payload: str, currency: str = "XTR",
                                  prices: list[tuple[str, int]],
                                  subscription_period: int | None = None) -> str
        # POST /bot{TOKEN}/createInvoiceLink
        # title 1-32 chars, description 1-255, payload 1-128 bytes,
        # exactly one LabeledPrice {label, amount} (amount = Stars, integer),
        # provider_token omitted, subscription_period in seconds (2592000 only).

    async def edit_user_star_subscription(self, *, user_id: int,
                                          telegram_payment_charge_id: str,
                                          is_canceled: bool) -> bool

    async def get_star_transactions(self, *, offset: int = 0,
                                    limit: int = 100) -> list[dict]
        # for ledger reconciliation; StarTransaction.id == telegram_payment_charge_id
        # for incoming payments

    async def get_my_star_balance(self) -> int

class HttpxStarPaymentsAdapter(StarPaymentsAdapter):  # the real adapter
    # BOT_TOKEN from os.getenv("TELEGRAM_BOT_TOKEN") at module import (owner_dm.py:25 pattern)
    # each method: async httpx client, timeout 10.0, non-200 -> log warning + raise
    #   RuntimeError("Telegram API error: <text[:200]>")  (callers translate to 502)

# module-level default instance for production:
star_payments: StarPaymentsAdapter = HttpxStarPaymentsAdapter()
# tests monkeypatch `services.boost.star_payments` / `services.subscriptions.star_payments`.
```

Invariants: the interface returns Telegram's invoice URL string only; never raises on network errors without logging; price amounts are always int Stars. Error modes: `RuntimeError` on HTTP failure (route modules translate to HTTPException 502). What it hides: the bot-token URL construction, JSON payload shapes, timeout policy, and the PTB-free requirement (D5).

### 2.2 `backend/services/boost.py` — the deep module for all boost behavior

```
# --- Purchase (buyer-facing, invoked by route modules) ---
def get_boost_price(db, item: Item) -> int
    # BOOST_PRICE_STARS[item.category] with exact-key lookup, else BOOST_PRICE_STARS["Other"]
    # (floor, D12). Always returns a positive int.

def create_boost_order(db, user: User, item: Item) -> dict
    # Validates: item exists (404), owner (Channel.registered_by == user.telegram_id, else 403),
    #   item.status == 'active' and item.is_active (400 if sold/soft-deleted),
    #   no ACTIVE boost exists for the item (409 "already boosted").
    # payload = f"b:{item.id}:{secrets.token_hex(4)}"   (≤128 bytes, unique per invoice)
    # Calls star_payments.create_invoice_link(title="Boost this product",
    #   description="7 days of top placement in category & search", payload=payload,
    #   prices=[("Boost", price)]).
    # Returns {"invoice_url": str, "payload": str, "price_stars": int, "duration_days": int}
    # Hidden behind this: price lookup, eligibility, payload encoding, Telegram call.

# --- Fulfillment (internal, idempotent) ---
def fulfill_boost(db, *, telegram_user_id: int, telegram_payment_charge_id: str,
                  invoice_payload: str, total_amount: int) -> Boost
    # 1. Existing boost with this charge id -> return it (replay no-op). [idempotency]
    # 2. Parse payload "b:{item_id}:{nonce}" -> item; verify channel.registered_by
    #    == telegram_user_id (else log + raise 403; never activate a foreign boost).
    # 3. Create Boost(item_id, channel_id, user_id, source='paid',
    #    price_paid_stars=total_amount, telegram_payment_charge_id,
    #    starts_at=now_utc, ends_at=now_utc + BOOST_DURATION_DAYS). commit + refresh.
    #    price_paid_stars = the ACTUAL charged amount from successful_payment
    #    (sp.total_amount, int Stars) — NEVER re-read BOOST_PRICE_STARS at fulfillment
    #    time: the invoice fixed the price at order creation and the charge id is
    #    unique per invoice, so total_amount always corresponds to this order.
    # Invariant: two calls with the same charge id return the same Boost row.

def fulfill_credit_boost(db, user: User, item: Item) -> Boost
    # Credit path: requires ACTIVE all_in_one subscription with remaining credit
    # (get_credit_boosts_remaining > 0, §2.3). Creates Boost(source='credit',
    # telegram_payment_charge_id=NULL, price_paid_stars=NULL). Same ownership/eligibility
    # validation as create_boost_order. Invariant: credit boosts and paid boosts are
    # indistinguishable in every placement query below (one table, no source filter).

# --- Placement (the pinned layer) ---
def get_pinned_boosted_items(db, *, category: str | None = None,
                             query_text: str | None = None,
                             now: datetime | None = None) -> list[Item]
    # SELECT boosts JOIN items WHERE ends_at > now AND item.status == 'active'
    #   AND item.is_active == True
    # Filters: category given -> item.category == category (exact);
    #          query_text given and non-empty -> item.title ILIKE %query% (case-insensitive).
    # ORDER: deterministic time-sliced rotation, NO background jobs, NO mutable state:
    #   1. sort candidates by item.id ASC
    #   2. rotation_offset = int(now.timestamp()) // (BOOST_ROTATION_MINUTES * 60) % len(candidates)
    #   3. return candidates[rotation_offset:] + candidates[:rotation_offset]
    # Rotation never pauses the clock (Rule 4.2/4.3). Called ONLY from the /search/ route
    # (D7). NEVER from services/recommendation.py (Rule 3.2).
    # Returns ORM Item list; the caller maps ids onto serialized responses.

# --- Lifecycle hooks (Rule 6) ---
def end_boost_for_item(db, item_id: int) -> None
    # UPDATE boosts SET ends_at = now_utc WHERE item_id == item_id AND ends_at > now_utc
    # (sold / reported_sold -> boost ends immediately, no refund. Rule 6.1.)

def transfer_boost(db, old_item_id: int, new_item_id: int) -> None
    # UPDATE boosts SET item_id = new_item_id
    # WHERE item_id == old_item_id AND ends_at > now_utc   (dedup replacement, Rule 6.2)
    # Wall-clock duration is preserved: starts_at/ends_at untouched.

def get_boost_status(db, item_id: int) -> dict | None
    # {"active": bool, "ends_at": iso|None, "source": 'paid'|'credit'|None}
    # for the frontend refresh loop after invoiceClosed.
```

### 2.3 `backend/services/subscriptions.py` — subscriptions, cap math, credit, lapse

```
def get_effective_alert_cap(db, user: User) -> int
    # MAX_ALERTS_PER_USER + (ALERTS_SUBSCRIPTION_EXTRA_ALERTS if an ACTIVE
    # subscription exists else 0). THE single cap authority — both call sites (D3) use it.

def get_active_subscription(db, user: User) -> Subscription | None
    # status == 'active' AND current_period_end > now_utc. One active per user (service rule).

def create_subscription_order(db, user: User, product: str) -> dict
    # product in {"alerts_only", "all_in_one"} else 400.
    # Active subscription exists -> 409 (v1: renewals are automatic; no upgrade path).
    # price = ALERTS_ONLY_PRICE_STARS | ALL_IN_ONE_PRICE_STARS.
    # payload = f"s:{user.id}:{product}:{secrets.token_hex(4)}"
    # star_payments.create_invoice_link(..., prices=[(product_title, price)],
    #   subscription_period=SUBSCRIPTION_PERIOD_SECONDS)   # 2592000 — hard-locked, XTR only
    # Returns {"invoice_url", "payload", "price_stars"}.

def fulfill_subscription_payment(db, *, telegram_user_id: int,
        telegram_payment_charge_id: str, invoice_payload: str,
        total_amount: int, subscription_expiration_date: datetime | None,
        is_recurring: bool, is_first_recurring: bool) -> Subscription
    # Idempotent on telegram_payment_charge_id (return existing row on replay).
    # Parse payload -> user + product. Create/refresh the user's subscription:
    #   status='active', current_period_start=now, current_period_end=
    #   subscription_expiration_date (Telegram's authoritative value; REQUIRED for
    #   first+renewal charges — 400 if missing).
    # After activation: reactivate_lapsed_alerts(db, user) (§below).
    # Invariant: initial charge and renewals (is_recurring) land here; renewals update
    # the SAME row's period_end; period_start stays the initial purchase.

def handle_subscription_state_update(db, *, telegram_user_id: int,
        invoice_payload: str, state: str) -> None
    # state in {"canceled","active","failed"} else log+ignore.
    # Locate subscription by payload (or user). canceled/failed -> status=state then
    # lapse_benefits(db, user). active -> status='active' then reactivate_lapsed_alerts.

def lapse_benefits(db, user: User) -> None
    # THE lapse-deactivation mechanism (locked, Rule 7.1.2):
    #   - Deactivate alerts BEYOND the free cap: select active alerts for user ordered
    #     by id ASC; keep the first get_effective_alert_cap(alerts) active? NO — the
    #     rule is: extra alerts beyond the FREE cap get paused. Set is_active=False AND
    #     lapsed=True on every active alert past the first MAX_ALERTS_PER_USER (by id).
    #   - Lapse-deactivation is DISTINGUISHABLE from user pause via Alert.lapsed:
    #     user pause leaves lapsed=False (default); lapse sets lapsed=True. (D-new:
    #     additive boolean column, §3.1.)

def reactivate_lapsed_alerts(db, user: User) -> None
    # On renewal: set is_active=True for alerts WHERE user_id==user AND lapsed==True,
    # oldest-first, up to the new effective cap. Alerts past the cap stay lapsed.

def get_credit_boosts_remaining(db, user: User) -> int
    # 0 if no active all_in_one subscription. Else:
    # ALL_IN_ONE_MONTHLY_BOOST_CREDIT - count(Boost WHERE user_id==user AND
    #   source=='credit' AND created_at BETWEEN current_period_start AND current_period_end)
    # Credit expires at period end by construction (window query) — no rollover (Rule 7.3.2).

def get_subscription_status(db, user: User) -> dict
    # {"product": str|None, "status": str|None, "current_period_end": iso|None,
    #  "extra_alerts": int, "credit_remaining": int, "credit_total": int}
```

Lapse mechanism decision (locked, per ticket requirement): new column `Alert.lapsed BOOLEAN NOT NULL DEFAULT False`. User pause = `is_active=False, lapsed=False`. Lapse = `is_active=False, lapsed=True`. The pause/resume route (`api/routes/alerts.py` `toggle_alert_pause`) gains ONE guard: resuming an alert with `lapsed=True` requires an active subscription at that moment (else 400 "Subscription required to reactivate this alert"). Everything else in the pause route is untouched.

### 2.4 `backend/services/stats.py` — seller intelligence aggregation

```
def get_channel_dashboard(db, channel_id: int, user: User) -> dict
    # Owner-only (route enforces). Returns:
    # {"is_pro": bool,  # active all_in_one subscription
    #  "core": {
    #     "items": [ {item_id, title, image_path, status,
    #                 views_total, views_daily: [{date, count}]  # last 7 days,
    #                 alert_matches: int,   # distinct alerts that fired for THIS item
    #                 dispatched: {bullseye: int, ring: int}     # SENT notifications }],
    #     "matching_buyers": int,  # distinct alerts with >=1 notification on channel items
    #     "total_dispatched": {bullseye: int, ring: int}
    #  },
    #  "pro": null | {
    #     "price_positioning": [ {item_id, median_price, pct_diff} ],  # vs same top-level
    #                                                                 # category median this week
    #     "category_pulse": {category, this_week: int, last_week: int},
    #     "top_performers": [ {item_id, title, views} ]  # channel items by views, limit 5
    #  }}

    # Data sources (verified, D9):
    #   views:       user_interactions WHERE interaction_type IN ('view_item','view_item_card')
    #   dispatched:  notifications WHERE item.channel_id == X AND status == 'SENT',
    #                grouped by match_tier ('bullseye'/'ring')
    #   alert_matches: notifications JOIN alerts, distinct alerts per item
    #   median:      percentile_cont(0.5) over price of items WHERE category == X
    #                AND status == 'active' AND price IS NOT NULL
    #   pulse:       count(items WHERE category == X AND created_at in week bucket)
    # No fake numbers — every figure traces to these tables (Rule 8.x "no estimates").
```

### 2.5 New route modules (thin HTTP adapters)

| Route | Auth | Body/Params | Returns | Delegates to |
|-------|------|-------------|---------|--------------|
| `GET /items/{item_id}/boost-quote` | `authenticate(init_data, db)` | — | `BoostQuoteResponse {price_stars, duration_days, category, active_boost}` | `boost.get_boost_price` + `get_boost_status` |
| `POST /items/{item_id}/boost-order` | same | — | `BoostOrderResponse {invoice_url, payload, price_stars, duration_days}` | `boost.create_boost_order` |
| `POST /items/{item_id}/boost-credit` | same | — | `BoostOrderResponse`-shaped `{boost: {id, ends_at, source}}` | `boost.fulfill_credit_boost` |
| `POST /internal/payments/fulfill-boost` | internal seam (D6) | `{telegram_payment_charge_id, invoice_payload, total_amount}` | `{status: "ok", boost_id}` | `boost.fulfill_boost` |
| `POST /internal/payments/fulfill-subscription` | internal seam | `{telegram_payment_charge_id, invoice_payload, total_amount, subscription_expiration_date, is_recurring, is_first_recurring}` | `{status: "ok", subscription_id}` | `subscriptions.fulfill_subscription_payment` |
| `POST /internal/payments/subscription-state` | internal seam | `{invoice_payload, state}` | `{status: "ok"}` | `subscriptions.handle_subscription_state_update` |
| `POST /subscriptions/order` | `authenticate` | `{product}` | `SubscriptionOrderResponse {invoice_url, payload, price_stars}` | `subscriptions.create_subscription_order` |
| `GET /subscriptions/status` | `authenticate` | — | `SubscriptionStatusResponse` | `subscriptions.get_subscription_status` |
| `GET /channels/{channel_id}/stats` | `authenticate` | — | `ChannelStatsResponse` | `stats.get_channel_dashboard` |

Internal endpoints live in a new router module `api/routes/payments.py` (no prefix; internal paths are explicit). Buyer-facing subscription endpoints live in `api/routes/subscriptions.py` (prefix `/subscriptions`). Boost purchase endpoints live in `api/routes/items.py` per NB-43's file list.

### 2.6 Listener payment modules

```
listener/payments.py (new):
    async def handle_pre_checkout(update, context) -> None
        # query = update.pre_checkout_query; await query.answer(True)
        # ZERO other work — the 10s clock is running. No DB, no client call.
        # Failure mode: exception -> log; Telegram cancels the transaction — acceptable
        # (buyer can retry; nothing was charged).

    async def handle_successful_payment(update, context) -> None
        # sp = update.effective_message.successful_payment   (fields verified: currency,
        #   total_amount, invoice_payload, telegram_payment_charge_id,
        #   provider_payment_charge_id, subscription_expiration_date, is_recurring,
        #   is_first_recurring)
        # user_id = update.effective_user.id
        # payload routing (first 2 chars):
        #   "b:" -> fulfill_boost_api(user_id, sp.telegram_payment_charge_id, sp.invoice_payload, sp.total_amount)
        #   "s:" -> fulfill_subscription_api(user_id, ..., sp.total_amount,
        #           sp.subscription_expiration_date, sp.is_recurring, sp.is_first_recurring)
        # Unknown prefix -> log warning. Delivery of goods happens HERE, never in
        # handle_pre_checkout (locked rule). Best-effort: failure logs; the backend
        # reconcile pass (§6) replays missed payments.

    async def handle_subscription_update(update, context) -> None
        # sub = update.api_kwargs.get('subscription')  (D2 — PTB 22.8 api_kwargs seam)
        # if not a dict with 'state' -> return
        # state in {"canceled","active","failed"} -> subscription_state_api(user_id,
        #   sub['invoice_payload'], sub['state'])

listener/client.py additions (mirror D6):
    async def fulfill_boost_api(user_id: int, charge_id: str, payload: str, total_amount: int) -> bool
        # POST {API_BASE}/internal/payments/fulfill-boost?init_data={user_id}
        #   headers=INTERNAL_HEADERS, json={telegram_payment_charge_id, invoice_payload, total_amount}
    async def fulfill_subscription_api(...) -> bool   # same shape
    async def subscription_state_api(user_id: int, payload: str, state: str) -> bool
```

Handler registration order in `listener/main.py` (order matters — PTB checks handlers in registration order; the catch-all MUST be last):
1. existing handlers (unchanged)
2. `PreCheckoutQueryHandler(payments.handle_pre_checkout)`
3. `MessageHandler(filters.SuccessfulPayment, payments.handle_successful_payment)`
4. `TypeHandler(Update, payments.handle_subscription_update)` — **last** (matches every Update; nothing after it).

### 2.7 Boost DM button (NB-45)

`listener/worker.py` success branch (both `is_replaced=True` and `False` paths, lines 88-99): replace `edit_text(edit_text)` with `edit_text(edit_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Boost this product", web_app=WebAppInfo(url=f"{WEB_APP_URL}/stores/{channel_id}/{result['item_id']}"))]]))`. `channel_id` comes from `channel_info.get('id')` (get_channel_info already returns it, client.py:141-161); guard `if channel_id and result.get('item_id')`. Button text generic; price never appears in the DM (Rule 2.4/5.2). The deep link uses path params (`/stores/{channel_id}/{item_id}`) to match the `App.jsx` route `/stores/:channelId/:itemId` (§2.8) — the query-param form is NOT used.

### 2.8 Frontend interfaces

| Module | Change |
|--------|--------|
| `App.jsx` | Add `<Route path="/stores/:channelId/:itemId" element={<MainLayout />} />` inside the existing `<Routes>` (App.jsx:107-111). `MainLayout` reads `useParams()`; when channelId present, forces `activeTab='stores'` and renders `<StoresPage deepLink={{channelId, itemId}} />`. All existing routes unchanged. |
| `StoresPage.jsx` | Accept optional `deepLink` prop; on mount, if set, auto-open `ChannelInventory` with the channel from `channels` (or fetch), then auto-open `ProductEditPanel` for the item — reusing the existing `selectedChannel`/`selectedProduct` state (StoresPage.jsx:11, 87-94). Also renders a subscription status card (from `useSubscription`) and the upgrade entry point. |
| `hooks/useBoost.js` (new) | `getQuote(itemId)`, `createOrder(itemId)` → `{invoice_url}` then `window.Telegram.WebApp.openInvoice(url, cb)`; on `invoiceClosed` `status==='paid'` → re-fetch quote; exposes `{quote, activeBoost, boosting, error, payWithStars}`. Mirrors `getInitData`/`getAnalyticsHeaders` patterns from `useChannelInventory.js:22-28`. |
| `hooks/useSubscription.js` (new) | `getStatus()`, `createOrder(product)`, `openInvoice(product)`, `applyCreditBoost(itemId)`; exposes status + credit_remaining. |
| `ProductEditPanel.jsx` | New "Boost" section between Status Controls and Save (additive): shows `quote.price_stars` in-context ("Boost this item for 7 days — N Stars"), active-boost status if any, "Boost with Stars" button → `useBoost.payWithStars`, and "Use Subscription Credit (N left)" button when `credit_remaining > 0`. On paid → toast + status refresh. |
| `ItemCard.jsx` | Additive "Boosted" badge: `{item.is_boosted && (<div className="absolute top-2 left-2 bg-amber-500 ...">⚡ Boosted</div>)}` — placed next to the match badge (ItemCard.jsx:41-58); no other changes. |
| `ChannelInventory.jsx` | Register third tab in `TAB_REGISTRY` (lines 13-16): `{ id: 'dashboard', label: 'Insights', icon: BarChart }` → renders `SellerIntelligenceDashboard`. Registry pattern makes this additive (inventory-management.md Rule 5.1). |
| `components/SellerIntelligenceDashboard.jsx` (new) | Fetches `GET /channels/{channel_id}/stats` (init_data + analytics headers); renders Core block always; renders Intelligence block only when `is_pro`, else upgrade prompt (NB-47 gating). |
| `schemas`/`utils/analytics.js` | Unchanged (analytics.js already generic; boost events may be logged via `logEvent('boost_purchase', itemId)` — optional, additive). |

---

## 3. Strict Import Map

ADDITIVE ONLY — every existing import, field, and signature is preserved. `+` = added, `·` = unchanged, `−` = removed (only where explicitly mandated).

### 3.1 `backend/constants.py`

| Import | Change |
|--------|--------|
| `import os, logging` | · |
| `from typing import Any, Union` | · |
| `import json` | **+** (for `_get_json_config`) |

New module members (append after line 83, group header `# --- Monetization (NB-43..NB-47) ---`):

```
def _get_json_config(key: str, default: dict) -> dict
    # json.loads(os.getenv(key)) on success; on ValueError/TypeError/None -> warn + default.

BOOST_DURATION_DAYS: int = _get_config("BOOST_DURATION_DAYS", 7, int)
BOOST_ROTATION_MINUTES: int = _get_config("BOOST_ROTATION_MINUTES", 30, int)
BOOST_PRICE_STARS: dict = _get_json_config("BOOST_PRICE_STARS", { ...19 taxonomy keys + "Other": 25... })
ALERTS_ONLY_PRICE_STARS: int = _get_config("ALERTS_ONLY_PRICE_STARS", 30, int)
ALL_IN_ONE_PRICE_STARS: int = _get_config("ALL_IN_ONE_PRICE_STARS", 100, int)
ALERTS_SUBSCRIPTION_EXTRA_ALERTS: int = _get_config("ALERTS_SUBSCRIPTION_EXTRA_ALERTS", 10, int)
ALL_IN_ONE_MONTHLY_BOOST_CREDIT: int = _get_config("ALL_IN_ONE_MONTHLY_BOOST_CREDIT", 2, int)
MONETIZATION_ENABLED: int = _get_config("MONETIZATION_ENABLED", 1, int)   # 0 = kill switch
SUBSCRIPTION_PERIOD_SECONDS: int = 2592000   # HARD-LOCKED by Telegram (30d); NO env override, NO comment ambiguity
```

`BOOST_PRICE_STARS` default dict: keys exactly the 19 top-level keys of `frontend/src/constants/taxonomy.js` (verified, D12) plus `"Other": 25`. Suggested operator-adjustable defaults (Stars): Mobile Phones 150, Laptops & Computers 120, Tablets 100, Electronics 80, Vehicles 200, Property 250, Home, Appliances & Furniture 50, Men's Fashion 40, Women's Fashion 40, Shoes 40, Health & Beauty 40, Commercial & Tools 60, Sports, Arts & Outdoors 40, Babies & Kids 30, Animals & Pets 30, Agriculture & Food 40, Services 30, Other 25.

### 3.2 `backend/models.py`

| Import | Change |
|--------|--------|
| `from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, BigInteger, Boolean, UniqueConstraint` | · (all types needed for new tables already imported) |
| `from sqlalchemy.orm import relationship, Mapped, mapped_column` | · |
| `from pgvector.sqlalchemy import Vector` | · |
| `from database import Base` | · |

New columns/models (append after `ItemEdit`, line 259):

- `Alert` class: add `lapsed = Column(Boolean, default=False, nullable=False)` after `deleted_at` (line 73). Comment: `# NB-46: True = deactivated by subscription lapse (distinct from user pause)`.
- New `class Boost(Base)` → `__tablename__ = "boosts"`: `id` (PK, index), `item_id` (FK `items.id` ON DELETE CASCADE, not null, index), `channel_id` (FK `channels.id`, not null), `user_id` (FK `users.id`, not null, index), `source` (String, not null, default `"paid"`), `price_paid_stars` (Integer, nullable — NULL for credit), `telegram_payment_charge_id` (String, nullable, **unique=True** — the idempotency key; NULLs are distinct in Postgres so multiple credit boosts coexist), `starts_at` (DateTime(timezone=True), not null), `ends_at` (DateTime(timezone=True), not null, index), `created_at` (server_default=func.now()).
- New `class Subscription(Base)` → `__tablename__ = "subscriptions"`: `id` (PK, index), `user_id` (FK `users.id`, not null, index), `product` (String, not null), `status` (String, not null, default `"active"`), `telegram_payment_charge_id` (String, nullable, unique=True), `invoice_payload` (String, not null), `current_period_start` (DateTime(timezone=True), nullable), `current_period_end` (DateTime(timezone=True), nullable), `is_recurring` (Boolean, default False), `created_at`, `updated_at` (server_default=func.now(), onupdate=func.now()).

No new relationships required — services query directly (matches the explicit-query style of `services/item_status.py`). Do NOT add `Item.boosts` / `User.subscriptions` relationships (keeps the deletion test clean).

### 3.3 `backend/services/` modules

**`services/telegram_payments.py` (NEW)** — imports: `import os`, `import logging`, `import httpx`, `from typing import Protocol, Optional, List, Tuple`. Module constants: `BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")`, `logger = logging.getLogger("index_payments")`.

**`services/boost.py` (NEW)** — imports: `from sqlalchemy.orm import Session`; `from sqlalchemy import select, update`; `from datetime import datetime, timedelta, timezone`; `import secrets`; `import logging`; `from fastapi import HTTPException`; `from models import Item, Channel, Boost, User`; `from constants import BOOST_DURATION_DAYS, BOOST_PRICE_STARS, BOOST_ROTATION_MINUTES`; `from services.telegram_payments import star_payments`; `from services.subscriptions import get_credit_boosts_remaining, get_active_subscription` — **direction check (no import cycle):** `subscriptions.py` imports `models` + `constants` + `telegram_payments` ONLY; it never imports `boost.py`. Cycle-free.

**`services/subscriptions.py` (NEW)** — imports: `from sqlalchemy.orm import Session`; `from sqlalchemy import select, func, update`; `from datetime import datetime, timezone`; `import secrets, logging`; `from fastapi import HTTPException`; `from models import Subscription, Alert, User, Boost`; `from constants import (MAX_ALERTS_PER_USER, ALERTS_SUBSCRIPTION_EXTRA_ALERTS, ALERTS_ONLY_PRICE_STARS, ALL_IN_ONE_PRICE_STARS, ALL_IN_ONE_MONTHLY_BOOST_CREDIT, SUBSCRIPTION_PERIOD_SECONDS)`; `from services.telegram_payments import star_payments`.

**`services/stats.py` (NEW)** — imports: `from sqlalchemy.orm import Session`; `from sqlalchemy import select, func`; `from datetime import datetime, timedelta, timezone`; `from models import Item, Channel, UserInteraction, Notification, Alert`; `from services.subscriptions import get_active_subscription` (gating).

**`services/search.py`** — imports: `from typing import List, Optional, Any, Tuple` (·). Signature changes (ADDITIVE): `_execute_search_sql(db, vec_literal, query_text, limit, offset, exclude_unpriced=False, exclude_item_ids: Optional[List[int]] = None)` — SQL gains `AND i.id NOT IN :exclude_ids` clause emitted only when non-empty (bindparam of list); `perform_hybrid_search(..., exclude_unpriced=False, exclude_item_ids: Optional[List[int]] = None)` — thread-through. All existing callers keep working (default None).

**`services/alerting.py`** — imports: keep every existing import; **+** `from services.subscriptions import get_effective_alert_cap`. Replace the body of the cap check at lines 287-299 (`if MAX_ALERTS_PER_USER > 0:` block) with `cap = get_effective_alert_cap(db, user)`; if `cap > 0` count active and compare against `cap`; error message text unchanged except it interpolates `cap` instead of `MAX_ALERTS_PER_USER` ("You've reached the maximum of {cap} active alerts..."). `MAX_ALERTS_PER_USER` remains in the import list (additive rule — the constant is still the free cap inside the subscriptions module).

**`services/item_status.py`** — imports: **+** `from services.boost import end_boost_for_item`. Call sites: `mark_sold` after `item.status = "sold"` (line 165) → `end_boost_for_item(db, item_id)`; `report_sold` after the threshold flip (lines 97-100) → `end_boost_for_item(db, item_id)`. `relist_item` untouched (boost stays ended). `update_item` untouched (Rule 6.3: edits don't interrupt boosts).

### 3.4 `backend/api/routes/`

**`api/routes/items.py`** — imports **+**: `from services.boost import get_boost_price, get_boost_status, create_boost_order, fulfill_credit_boost`; `from schemas import BoostQuoteResponse, BoostOrderResponse, BoostStatusResponse` (new schemas, §3.5). New routes appended AFTER the existing ones (after line 222): `GET /{item_id}/boost-quote`, `POST /{item_id}/boost-order`, `POST /{item_id}/boost-credit` — all `init_data`-authenticated, all delegating (§2.5). All existing imports/routes unchanged.

**`api/routes/search.py`** — imports **+**: `from datetime import datetime, timezone`; `from services.boost import get_pinned_boosted_items`. `search_items` (lines 17-66) gains the pin layer: compute `now = datetime.now(timezone.utc)`; `pinned = get_pinned_boosted_items(db, category=query.category or None, query_text=query.query or None, now=now)`; `pinned_ids = {i.id for i in pinned}`; pass `exclude_item_ids=list(pinned_ids)` into `search_service.perform_hybrid_search`; after constructing `SearchResponse` items, set `item.is_boosted = item.id in pinned_ids` on each serialized ItemResponse; page composition = pinned (in rotation order) followed by organic slice; `total` stays the organic count. `search_by_image` untouched (image search is not an eligible surface).

**`api/routes/alerts.py`** — imports **+**: `from services.subscriptions import get_effective_alert_cap`. Replace the route-level guard at lines 33-44 with `cap = get_effective_alert_cap(db, user)` + same count/compare/interpolate. Keep the existing `MAX_ALERTS_PER_USER` import (additive rule). `toggle_alert_pause` (lines 119-168): add the lapsed-guard — before flipping `is_active` to True, if `alert.lapsed` is True, require `get_active_subscription(db, user)` else raise 400 ("Subscription required to reactivate this alert"). Pausing a lapsed alert stays allowed.

**`api/routes/payments.py` (NEW internal router)** — imports: `from typing import Optional`; `from fastapi import APIRouter, Depends, Header, HTTPException`; `from sqlalchemy.orm import Session`; `from database import get_db`; `from services.auth import authenticate`; `from services.boost import fulfill_boost`; `from services.subscriptions import fulfill_subscription_payment, handle_subscription_state_update`; `from schemas import FulfillBoostRequest, FulfillSubscriptionRequest, SubscriptionStateRequest`. Three POST routes per §2.5; each authenticates via `authenticate(body.init_data, db, x_internal_service)` (D6) and translates service exceptions to 502 (Telegram) / 400 (bad payload) / 404. Registration in main.py with NO prefix.

**`api/routes/subscriptions.py` (NEW)** — imports: `from fastapi import APIRouter, Depends`; `from sqlalchemy.orm import Session`; `from database import get_db`; `from services.auth import authenticate`; `from services.subscriptions import create_subscription_order, get_subscription_status`; `from schemas import SubscriptionOrderRequest, SubscriptionOrderResponse, SubscriptionStatusResponse`. `POST /order`, `GET /status`.

**`api/routes/channels.py`** — imports **+**: `from services.stats import get_channel_dashboard`; `from schemas import ChannelStatsResponse`. New route `GET /{channel_id}/stats` (owner-only, `authenticate(init_data, db)`, ownership check identical to `get_channel_items` lines 355-365) delegating to `stats.get_channel_dashboard`. All existing routes unchanged.

**`backend/main.py`** — imports **+**: `from api.routes import payments, subscriptions` (extend line 13). Registrations after line 280: `app.include_router(payments.router)` (no prefix), `app.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])`. New idempotent migration block (append after the TECH-25 block, ~line 187): `ALTER TABLE alerts ADD COLUMN IF NOT EXISTS lapsed BOOLEAN DEFAULT FALSE`; `CREATE TABLE IF NOT EXISTS boosts (...)` with `UNIQUE(telegram_payment_charge_id)`, index on `item_id`, index on `ends_at`; `CREATE TABLE IF NOT EXISTS subscriptions (...)` with `UNIQUE(telegram_payment_charge_id)`, index on `user_id`. Every `ALTER/CREATE` inside the same `try/except` warn-and-continue style as existing blocks (main.py:67-187).

**`backend/schemas.py`** — ADDITIVE new schemas (append at end, after line 303):
`BoostStatusResponse {active: bool, ends_at: Optional[datetime], source: Optional[str]}`; `BoostQuoteResponse {price_stars: int, duration_days: int, category: Optional[str], active_boost: Optional[BoostStatusResponse]}`; `BoostOrderResponse {invoice_url: str, payload: str, price_stars: int, duration_days: int}`; `FulfillBoostRequest {init_data: str, telegram_payment_charge_id: str, invoice_payload: str, total_amount: int}`; `FulfillSubscriptionRequest {init_data: str, telegram_payment_charge_id: str, invoice_payload: str, total_amount: int, subscription_expiration_date: Optional[datetime], is_recurring: bool = False, is_first_recurring: bool = False}`; `SubscriptionStateRequest {init_data: str, invoice_payload: str, state: str}`; `SubscriptionOrderRequest {product: str}`; `SubscriptionOrderResponse {invoice_url: str, payload: str, price_stars: int}`; `SubscriptionStatusResponse {product: Optional[str], status: Optional[str], current_period_end: Optional[datetime], extra_alerts: int, credit_remaining: int, credit_total: int}`; `ChannelStatsResponse` (core/pro nested models per §2.4); `ItemResponse` gains `is_boosted: bool = False` (additive field, line ~95).

### 3.5 `listener/`

**`listener/payments.py` (NEW)** — imports: `from telegram import Update`; `from telegram.ext import ContextTypes`; `from client import fulfill_boost_api, fulfill_subscription_api, subscription_state_api`; `from config import logger`.

**`listener/client.py`** — imports **+**: nothing new needed (`httpx` present). Add three functions (§2.6) following the exact `INTERNAL_HEADERS` + `init_data` pattern of `clear_item_reports_api` (lines 164-181).

**`listener/worker.py`** — imports **+**: `from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo`; `from config import logger, HEARTBEAT_INTERVAL, MAX_RETRIES_LIMIT, WEB_APP_URL`. Modify the success-edit branch (lines 88-99): capture `channel_id = channel_info.get('id')` (available from line 30); build the reply_markup (§2.7); `await dm_message.edit_text(edit_text, reply_markup=reply_markup)` in BOTH the replaced and non-replaced branches (same button, per NB-45).

**`listener/main.py`** — imports **+**: `from telegram import Update`; `from telegram.ext import TypeHandler`; `from payments import handle_pre_checkout, handle_successful_payment, handle_subscription_update`. Registration block after line 53 (channel ingestion): `PreCheckoutQueryHandler(handle_pre_checkout)`, `MessageHandler(filters.SuccessfulPayment, handle_successful_payment)`, and LAST `TypeHandler(Update, handle_subscription_update)`.

### 3.6 `frontend/src/`

| File | Imports changed |
|------|-----------------|
| `App.jsx` | **+** `useParams` from react-router-dom; add route `/stores/:channelId/:itemId` (§2.8). |
| `pages/StoresPage.jsx` | **+** `useSubscription` hook, `BarChart3`/`Star` icons as needed. |
| `hooks/useBoost.js` (NEW) | `API_BASE_URL` from `../config`, `getAnalyticsHeaders` from `../utils/analytics` (same patterns as `useChannelInventory.js:1-3`). |
| `hooks/useSubscription.js` (NEW) | same two imports. |
| `components/ProductEditPanel.jsx` | **+** `Rocket`/`Star` icons from lucide-react; `useBoost` hook; existing imports untouched. |
| `components/ItemCard.jsx` | no new imports (badge uses existing inline styles); render-only change. |
| `components/ChannelInventory.jsx` | **+** `BarChart` icon from lucide-react; `SellerIntelligenceDashboard` component. |
| `components/SellerIntelligenceDashboard.jsx` (NEW) | `API_BASE_URL`, `getAnalyticsHeaders`, lucide icons. |

No changes: `utils/analytics.js`, `config.js`, `constants/taxonomy.js`.

---

## 4. Execution Steps

Atomic commits: ONE per phase, and ONLY after the phase's QA gate passes (AGENTS.md: only @build commits, and only with @qa approval). Branch: create `feat/monetization` from main before Phase 1; never commit mid-phase. Verification commands listed per phase run against the local stack (`docker compose` services are `db`, `api`, `listener`, `frontend`).

### Phase 1 — Config, data model, boost core (no payments yet)

1. `backend/constants.py`: add `import json`, `_get_json_config`, the §3.1 monetization group. Verify: `python -c "import constants; print(constants.BOOST_PRICE_STARS, constants.SUBSCRIPTION_PERIOD_SECONDS)"` inside the api container; also `BOOST_PRICE_STARS='{"Mobile Phones":99}' python -c ...` to prove env override parses.
2. `backend/models.py`: add `Alert.lapsed`, `Boost`, `Subscription` (§3.2).
3. `backend/main.py`: add the migration block (§3.4) — restart api, confirm `boosts`, `subscriptions`, `alerts.lapsed` exist (`docker exec index_db psql -U $DB_USER -d $DB_NAME -c '\d boosts'`).
4. `backend/services/telegram_payments.py`: the Protocol + `HttpxStarPaymentsAdapter` + module-level `star_payments` (real adapter not yet exercised — invoice creation is Phase 2, but the module and its fake land here so boost service tests have the seam).
5. `backend/services/boost.py`: `get_boost_price`, `create_boost_order` (guarded by `MONETIZATION_ENABLED` → 503 when off), `fulfill_boost` (idempotent), `fulfill_credit_boost` (validates credit via subscriptions.get_credit_boosts_remaining — stub that function in subscriptions.py NOW returning 0), `get_pinned_boosted_items` (rotation math), `end_boost_for_item`, `transfer_boost`, `get_boost_status`. `create_boost_order` calls `star_payments.create_invoice_link`.
6. `backend/services/subscriptions.py` (partial): `get_effective_alert_cap`, `get_active_subscription`, `get_credit_boosts_remaining`, `lapse_benefits`, `reactivate_lapsed_alerts` (full fulfillment methods are Phase 3 — define the module now to keep the import direction clean).
7. Tests (Phase 1 scope): `backend/tests/test_boost.py`, `backend/tests/fake_telegram_payments.py` (§5). Run: `docker exec index_api python -m pytest tests/test_boost.py -q`.
8. **QA gate + atomic commit** `feat/monetization: phase 1 — monetization config, models, boost core (NB-43/44)'.

### Phase 2 — Stars payments seam, fulfillment, search pin

1. `backend/api/routes/items.py`: `GET /{item_id}/boost-quote`, `POST /{item_id}/boost-order`, `POST /{item_id}/boost-credit` (+schemas). Wire `MONETIZATION_ENABLED` guard in the router (single module-level check → 503).
2. `backend/api/routes/payments.py` (internal fulfillment router) + main.py registration.
3. `backend/services/search.py`: additive `exclude_item_ids` threading; `api/routes/search.py`: pin layer + `is_boosted` marking.
4. `backend/schemas.py`: `ItemResponse.is_boosted`, all payment schemas.
5. `listener/payments.py`, `listener/client.py` additions, `listener/main.py` handler registration (order per §2.6).
6. `listener/worker.py`: boost button on both success DM variants (§2.7).
7. `backend/services/item_status.py`: `end_boost_for_item` hooks; `backend/api/routes/ingestion.py`: `transfer_boost` after new-item flush (before line 231 commit).
8. Frontend: `ItemCard.jsx` Boosted badge; `useBoost.js` + `ProductEditPanel.jsx` boost section; `App.jsx` deep-link route; `StoresPage.jsx` deepLink handling (NB-45 landing). Manual verify in Mini App: DM → button → lands on exact product edit panel.
9. Tests: §5 scope. `docker exec index_api python -m pytest tests/test_boost.py tests/test_payments_flow.py -q`.
10. **QA gate + atomic commit** `feat/monetization: phase 2 — stars payments seam, boost fulfillment, search pin (NB-43/44/45)`.

### Phase 3 — Subscriptions & alert cap

1. `backend/services/subscriptions.py` (complete): `create_subscription_order`, `fulfill_subscription_payment`, `handle_subscription_state_update`.
2. `backend/api/routes/subscriptions.py` + main.py registration.
3. `backend/api/routes/payments.py`: wire `fulfill-subscription` and `subscription-state` routes.
4. Alert cap refactor (D3): `services/alerting.py:287-299` and `api/routes/alerts.py:33-44` both delegate to `get_effective_alert_cap`; `toggle_alert_pause` lapsed-guard (§2.3).
5. Listener: successful_payment payload routing (`b:`/`s:` prefixes), subscription api_kwargs handler (D2).
6. Tests: §5 scope. **QA gate + atomic commit** `feat/monetization: phase 3 — star subscriptions, lapse mechanism, cap math (NB-46)`.

### Phase 4 — Seller Intelligence dashboard

1. `backend/services/stats.py` (§2.4) + `GET /channels/{channel_id}/stats` in `api/routes/channels.py` + schemas.
2. Frontend: `SellerIntelligenceDashboard.jsx` + `ChannelInventory.jsx` tab registration.
3. Tests: §5 scope. **QA gate + atomic commit** `feat/monetization: phase 4 — seller intelligence dashboard (NB-47)`.

### Phase 5 — Frontend subscriptions UI & polish

1. `useSubscription.js`; `StoresPage.jsx` subscription status card + upgrade entry; `ProductEditPanel.jsx` credit-boost button when `credit_remaining > 0`.
2. End-to-end manual pass in the Mini App: quote → invoice → pay (test Stars) → boost active → refresh shows Boosted badge; subscription purchase → cap raised; lapse (cancel via `edit_user_star_subscription` from a scratch bot script) → extras paused with distinct lapsed state; renewal → reactivated.
3. **QA gate + atomic commit** `feat/monetization: phase 5 — subscription UI and credit boosts`.

### Phase 6 — Reconciliation, regression, hardening

1. `services/telegram_payments.py`: `get_star_transactions` adapter + new internal route `POST /internal/payments/reconcile` (or a module function `reconcile_star_payments(db)`) that pulls recent transactions, matches `StarTransaction.id` against unfulfilled `telegram_payment_charge_id`-less invoice payloads... precisely: fetch transactions since last watermark, for each incoming transaction whose `id` has no Boost/Subscription row, look up the payload in the transaction data and replay `fulfill_boost`/`fulfill_subscription_payment` (both are idempotent — safe). Wire it to the existing daily timer pattern in `main.py` (the TECH-22 scheduler block, lines 244-262) with a `MONETIZATION_ENABLED` guard.
2. Full regression: `docker exec index_api python -m pytest -q` (baseline: 116 passed / 2 pre-existing failures / 18 skipped per tech-backlog.md:27 — the two pre-existing failures must remain the ONLY failures).
3. Frontend build: `docker compose build frontend && docker compose up -d frontend`.
4. **QA gate + atomic commit** `feat/monetization: phase 6 — star reconciliation and regression`.

---

## 5. Testing Strategy

**Telegram is True external → the adapter seam is the test surface.** All tests run in-process against `suq_test_db` via the existing `db_session` fixture (`backend/tests/conftest.py:58-68` — new tables auto-register because conftest imports `models` at line 47). No test ever touches `api.telegram.org`.

### 5.1 `backend/tests/fake_telegram_payments.py` — the second adapter (makes the seam real)

In-memory `FakeStarPaymentsAdapter` implementing the §2.1 Protocol: `create_invoice_link` returns a deterministic fake URL and records the call (assertable: title, description, payload, prices, subscription_period); `edit_user_star_subscription` records; `get_star_transactions` returns from an in-memory ledger the test seeds. Tests install it via `monkeypatch.setattr("services.boost.star_payments", fake)` / `"services.subscriptions.star_payments"` / `"api.routes.items.star_payments"`.

### 5.2 Required test modules & assertions (observable outcomes only)

| Module | Cases (minimum) |
|--------|-----------------|
| `tests/test_boost.py` | quote returns price for category; Other/unknown category → floor; quote requires ownership (403); order calls adapter with exactly one LabeledPrice, XTR, payload ≤128 bytes; fulfill_boost creates Boost with ends_at = starts_at + 7d and price_paid_stars == the charged total_amount; **replay of same charge id returns same Boost row and no second row** (price_paid_stars still equals the charged amount, never the then-current category price — test by changing BOOST_PRICE_STARS between order and fulfillment); fulfill rejects foreign channel owner; credit boost consumes credit and is placement-indistinguishable; `get_pinned_boosted_items` returns only active/eligible items, excludes sold/soft-deleted, filters by category and title-query, NEVER returns items when feed flag... (feed is untouched — assert recommendation.py has no import edge to boost.py via graphify); **rotation**: fixed `now` values 30 min apart produce different order, same `now` same order, all items still present (rotation is a permutation); `end_boost_for_item` expires boost; `transfer_boost` moves remaining time to replacement. |
| `tests/test_subscriptions.py` | cap = free + extra when active (both call sites — alerts.py route function and alerting.create_alert produce identical reject/pass behavior at 20/21/30/31 alerts); order uses subscription_period=2592000; fulfillment idempotent on charge id; renewal updates period_end on the SAME row; lapse: subscription canceled → alerts beyond free cap get `is_active=False, lapsed=True`; user-paused alerts keep `lapsed=False`; renewal reactivates lapsed alerts oldest-first up to cap; resume of lapsed alert without subscription → 400; credit_remaining = 2 → 1 → 0 → new period resets (simulate by advancing period_end). |
| `tests/test_stats.py` | views counts only `view_item`/`view_item_card`; sparkline window 7 days; dispatched bullseye/ring split from SENT notifications; median/percentile math on seeded prices; pro block None without subscription, populated with it; every number traces to seeded rows (no estimates). |
| `tests/test_payments_flow.py` | full loop with fake adapter: order → fulfill (listener call shape) → boost active; unknown payload prefix ignored; fulfill-boost with missing charge id → 400; internal seam auth: request without `X-Internal-Service: index-listener` → 403. |
| `tests/test_alert_cap_regression.py` | existing TECH-20/TECH-25 suites unchanged and green (the cap refactor must not alter free-tier behavior with no subscription). |

Listener-side logic (payload routing, api_kwargs parsing) is exercised via direct unit calls with synthetic update-like objects and monkeypatched `client` functions — the listener container has no pytest harness today; @build may add `listener/tests/test_payments_routing.py` runnable from the listener container, OR keep those three functions in `listener/payments.py` so thin they are verified by the Phase 5 manual pass. Prefer the latter (deletion test: routing logic is ~20 lines).

---

## 6. Rollout & Rollback Notes

1. **Kill switch:** `MONETIZATION_ENABLED` (default 1). When 0: all monetization route modules return 503 at the router level; the listener still registers handlers but the payload-prefix routing logs-and-drops (fulfillment endpoints 503 too — nothing activates); frontend hides boost/subscription UI (quote fetch returns 503 → hide section). Rollback = set env to 0 and restart `api` + `listener` — no code revert needed for an emergency stop.
2. **Lost `successful_payment`:** idempotent fulfillment means replay is safe. The Phase 6 reconciliation (`get_star_transactions`) replays any incoming transaction whose charge id has no fulfillment row. Until Phase 6 ships, a lost update means a buyer paid and the boost did not activate — the operator restores it by re-posting the fulfillment via the internal endpoint (documented in the phase-6 commit message). `telegram_payment_charge_id` is stored on every Boost/Subscription row precisely for this.
3. **10-second pre-checkout constraint:** `handle_pre_checkout` does exactly `query.answer(True)`. If it ever raises or is slow, Telegram cancels the transaction with zero charge — safe failure. The listener's ingestion worker sleeps (`HEARTBEAT_INTERVAL`) are on a separate asyncio task and cannot delay handler dispatch; @build must not add any `await` of network calls inside `handle_pre_checkout`.
4. **Subscription period is Telegram-hard-locked**: `SUBSCRIPTION_PERIOD_SECONDS = 2592000` is a plain module constant with no env override (Telegram rejects anything else; a configurable value would only produce 400s).
5. **Price changes are operator-only**: `BOOST_PRICE_STARS` env JSON + restart of `api`. Rule 2.3 (no reactive price movement) is preserved because the price is read at order creation; a price change never alters an in-flight invoice (payload carries no price — the invoice itself fixed it).
6. **Payment update ordering:** `subscription` (user-side cancel) may arrive before/after renewals. `handle_subscription_state_update` and `fulfill_subscription_payment` are both last-write-wins on status/period_end; the active-ness predicate (`status='active' AND period_end > now`) makes transient interleavings self-healing on the next event. Lapse benefits run eagerly on `canceled`/`failed` — an out-of-order renewal afterward re-runs `reactivate_lapsed_alerts` (idempotent).
7. **DB rollback:** dropping the three new objects (`boosts`, `subscriptions`, `alerts.lapsed`) is the only schema revert; all other changes are additive and inert without the env config.

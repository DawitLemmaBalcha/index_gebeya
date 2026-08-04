# NB-48 — Monetization Hub & Entry Points (EXECUTION BLUEPRINT)

**Date:** 2026-08-04
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture
**Ticket:** NB-48 — pending-behaviors.md:134-153
**Master spec:** docs/behaviors/monetization.md §10 (locked), §2.4, §2.6-2.7, §7, §8
**Branch:** feat/monetization, HEAD 0944db6 — single phase, one atomic commit

## 1. Architecture Context

**Friction.** Three revenue products (Boost, Alerts-Only, All-in-One) are undiscoverable. The Alerts-Only subscription is sold from the Stores tab where no seller ever feels the alert cap; the Alerts tab hides the cap entirely; locked Insights shows an inert card with no action; and every entry point jumped straight to the Stars invoice with zero value explanation. The ticket inverts this: entry at the moment of need, an explanatory hub before any payment, never a bare redirect to an invoice (Rule 10.1.1, 10.2.6).

**Dependency categories.**
- **Frontend — one deep new page module + shallow adapters.** `MonetizationHub.jsx` is the deep module: it carries the three tailored pitches, the shared "How Stars work" explainer, the cross-sells, and ALL subscription invoice opens. Every entry point (`AlertsPage` banner, `StoresPage` cards, `SellerIntelligenceDashboard` prompt, `ProductEditPanel` learn-more) is a presentation **adapter** over existing hooks, leading to the hub. One new data adapter (`useBoosts.js`) consumes the one new endpoint.
- **Backend — additive, local-substitutable.** The extended `SubscriptionStatusResponse` becomes the single "seller monetization context" payload (caps + prices + threshold). One new owner-scoped boosts-list endpoint mirrors the `channels.py` route family. One constant. One error-message string. No new payment logic, no purchase-flow changes.
- **Seams.** `/hub/:tab?` (navigation contract), `SubscriptionStatusResponse` (hub + banner data), `GET /channels/{id}/boosts` (Stores card data). Locality: all cap math stays in `services/subscriptions.py` (`get_effective_alert_cap` is the single cap authority); all boost placement/list logic stays in `services/boost.py`.

## 2. The New Interfaces

### 2.1 Route contract (frontend)
- **`/hub/:tab?`** — `tab` ∈ {`boost`, `alerts`, `all-in-one`}; invalid or absent → fall back to **`all-in-one`**. Verified against §10.2.1: the All-in-One tab is the superset story, so the bare `/hub` default selling everything is consistent (entry points always pass an explicit tab, so the default only serves manual navigation). **Note recorded:** architect's "default All-in-One is fine" confirmed against spec.
- **`/hub/boost?item=<id>`** — boost preselect: exact price + direct "Boost this item" action.
- **`/stores`** — lands the seller on the Stores tab (the "pick an item" target from the hub's Boost tab). Requires an additive `initialTab` prop on `MainLayout`.
- Registered in `App.jsx` **before** the `/*` catch-all. The hub renders **outside** `MainLayout` (no bottom nav — a focused purchase page with its own back affordance, `navigate(-1)`).

### 2.2 `SubscriptionStatusResponse` — extended, additive
New fields (zero-defaulted so existing consumers are untouched):

| Field | Source |
|---|---|
| `free_cap: int` | `MAX_ALERTS_PER_USER` |
| `effective_cap: int` | `get_effective_alert_cap(db, user)` (the single cap authority) |
| `cap_banner_threshold: int` | `ALERT_CAP_BANNER_THRESHOLD` (new constant) |
| `alerts_only_price_stars: int` | `ALERTS_ONLY_PRICE_STARS` |
| `all_in_one_price_stars: int` | `ALL_IN_ONE_PRICE_STARS` |
| `boost_floor_price_stars: int` | `BOOST_PRICE_STARS.get("Other", min(BOOST_PRICE_STARS.values()))` — "Other" is the designated floor bucket per Rule 2.2; `min()` guards a malformed config missing the key |
| `boost_duration_days: int` | `BOOST_DURATION_DAYS` |

This payload is now the hub's data endpoint: **prices never appear on any existing endpoint** (verified — `SubscriptionOrderResponse` only exists post-POST; `BoostQuoteResponse` is per-item), so extending the status response is the minimal additive seam. Both branches of `get_subscription_status` (subscribed / not) return all fields.

### 2.3 `GET /channels/{channel_id}/boosts` — new endpoint
- **Shape:** `[{item_id, title, ends_at, source}]` via new `BoostSummaryResponse` schema (`item_id: int; title: Optional[str]; ends_at: datetime; source: str`).
- **Active-only:** `ends_at > now` AND `Item.status == 'active'` AND `Item.is_active == True`; defensive dedupe per item (latest id wins, mirroring `get_boost_status`); sorted `ends_at` ascending (soonest-expiring first for the "time remaining" card).
- **Ownership:** 403 (boost-domain convention from `items.py` `_require_boost_owner`; deliberately NOT the 404 the stats route uses — the locked test spec requires 403, and boost data is owner-sensitive in the boost domain).
- **Kill switch:** 503 via a `_monetization_enabled_or_503()` helper added to `channels.py` (mirrors `items.py:34`).
- **Why per-channel over `/boosts/mine`:** `channels.py` is the owner-scoped route family (`GET /{channel_id}/items`, `GET /{channel_id}/stats`); the frontend already holds the channel list in memory (`useOwnerChannels`) and fans out with `Promise.all` (1–3 fetches). One active boost per item is enforced at order time, so the join is cheap.

### 2.4 Entry-point adapters (each leads to the hub FIRST — never bare payment)
1. **AlertsPage cap banner** — shows when `effective_cap - alerts.length <= cap_banner_threshold` (and always once at/over the cap): "You're at 18 of 20 active alerts — get 10 more." Tap → `navigate('/hub/alerts')`. Hidden when monetization is disabled (`status` null after `getStatus` 503s) and while loading.
2. **StoresPage restructure** — Alerts-Only CTA **removed** (Rule 10.3.1; the active-subscription status label may remain — offering ≠ status display); All-in-One CTA becomes navigation to `/hub/all-in-one` (no `openInvoice`); new **boost management card** below the subscription card: per-channel active boosts (item title + time remaining from `ends_at`), "Boost a product" → `/hub/boost`, one-line All-in-One upsell → `/hub/all-in-one`. Card renders for owners whenever the boosts fetch succeeds (empty state included: "No active boosts"); hides on 503/failure.
3. **SellerIntelligenceDashboard locked prompt** — currently an **inert card** (verified, lines 205-218: text only, no button). Gains an "Unlock Seller Intelligence" button → `navigate('/hub/all-in-one')`.
4. **ProductEditPanel boost section** — verified: no "learn more" affordance exists; direct buy + credit buttons stay (Rule 10.2.6 explicitly allows payment from an item's own boost section). **Minimal change:** one small "Learn more" link under the explanatory copy → `navigate('/hub/boost?item=<id>')`. Nothing else.
5. **Alerts rejection message** (`alerts.py:43-46`, route-level guard) — text addition only: `"You've reached the maximum of {cap} active alerts. Pause or delete an existing alert to create a new one. Need more? Open the Alerts tab in the hub."` Existing tests assert substrings (`f"{MAX_ALERTS_PER_USER}" in detail`) — safe. The service-level backstop in `alerting.py:288` stays untouched (route guard fires first in the UI flow; ticket scope is the route).

### 2.5 Kill switch (blueprint §6.1)
`MONETIZATION_ENABLED=0` → `/subscriptions/status`, `/items/{id}/boost-quote`, and `/channels/{id}/boosts` all 503 → the hub shows an "unavailable" state with **no buy actions** (`status === null && !loading` after `getStatus`), the Stores boost card and banner hide (existing `subStatus !== null` gating pattern).

## 3. Strict Import Map (additive only — nothing removed)

### Backend

**`backend/constants.py`** — no import changes. Add one line in the monetization group (after `MONETIZATION_ENABLED`, line 139):
`ALERT_CAP_BANNER_THRESHOLD: int = _get_config("ALERT_CAP_BANNER_THRESHOLD", 2, int)`.

**`backend/schemas.py`** — no import changes (`datetime`, `List`, `Optional` already in use). Add `BoostSummaryResponse` after `BoostCreditResponse` (line 338). Extend `SubscriptionStatusResponse` (lines 377-383) with the seven fields from §2.2.

**`backend/services/subscriptions.py`** — extend the constants import block (lines 23-30) with `ALERT_CAP_BANNER_THRESHOLD`, `BOOST_DURATION_DAYS`, `BOOST_PRICE_STARS`. **No new module imports** (cycle rule: `subscriptions.py` must never import `boost.py` — hence the floor is computed from constants directly, with a comment noting the deliberate mirror of `boost._OTHER_FLOOR`). `get_subscription_status` (lines 269-290): add the seven keys to BOTH return dicts; `effective_cap` via the in-module `get_effective_alert_cap(db, user)`.

**`backend/services/boost.py`** — no import changes (`select`, `Boost`, `Item`, `User` already imported, lines 18-27). Add `list_active_channel_boosts(db: Session, channel_id: int) -> list[dict]` returning `[{item_id, title, ends_at, source}]` per §2.3.

**`backend/api/routes/channels.py`** — add imports: `from constants import MONETIZATION_ENABLED`; `BoostSummaryResponse` to the existing `schemas` import (line 16); `from services.boost import list_active_channel_boosts`. Add the `_monetization_enabled_or_503()` helper (copy of `items.py:34-37`). New route `GET /{channel_id}/boosts` (registered after `/stats`, line 429) per §2.3. Route-order safety verified: no existing template can shadow `/{channel_id}/boosts`.

**`backend/api/routes/alerts.py`** — no import changes. Replace the detail string at line 45 per §2.4.5.

### Frontend

**`frontend/src/pages/MonetizationHub.jsx` (NEW)** — `react` (`useState`, `useEffect`, `useCallback`); `react-router-dom` (`useNavigate`, `useParams`, `useSearchParams`); `lucide-react` icons (ArrowLeft, Star, Bell, Sparkles, Rocket, ChevronDown); `../hooks/useSubscription` (`useSubscription`); `../hooks/useBoost` (`useBoost`); `../hooks/useAlerts` (`useAlerts`). **Must NOT import `BOOST_PRICE_STARS` or any config table** (rate-card ban).

**`frontend/src/hooks/useBoosts.js` (NEW)** — `react` (`useState`, `useCallback`); `../config` (`API_BASE_URL`); `../utils/analytics` (`getAnalyticsHeaders`). Interface: `{ boosts, loading, error, hasBeenFetched, fetchBoosts(channels) }` — `fetchBoosts` does `Promise.all(channels.map(c => GET /channels/{c.id}/boosts))`, merges and sorts by `ends_at` asc, keeps the module-level cache house pattern (`_boostsCache`).

**`frontend/src/App.jsx`** — add `import MonetizationHub from './pages/MonetizationHub';`. Add `<Route path="/hub/:tab?" element={<MonetizationHub />} />` and `<Route path="/stores" element={<MainLayout initialTab="stores" />} />` before the `/*` route (line 116). `MainLayout` signature becomes `({ initialSearchQuery = '', initialTab })`; `useState(initialTab || (deepLink ? 'stores' : 'explore'))` (line 25).

**`frontend/src/pages/StoresPage.jsx`** — add `import { useNavigate } from 'react-router-dom';` and `import { useBoosts } from '../hooks/useBoosts';`. Keep all existing imports (icons, `useOwnerChannels`, `useSubscription`, `API_BASE_URL`, `getAnalyticsHeaders`, `ChannelInventory`). Remove `openInvoice('alerts_only')` (line 187) and `openInvoice('all_in_one')` (line 194) — both replaced by navigation; `openInvoice` is no longer called from this file.

**`frontend/src/pages/AlertsPage.jsx`** — add `import { useSubscription } from '../hooks/useSubscription';`. `useNavigate` already imported (line 2).

**`frontend/src/components/SellerIntelligenceDashboard.jsx`** — add `import { useNavigate } from 'react-router-dom';`.

**`frontend/src/components/ProductEditPanel.jsx`** — add `import { useNavigate } from 'react-router-dom';` (verified absent today).

## 4. Execution Steps (single phase — one atomic commit)

**Backend additive changes**
1. `constants.py`: add `ALERT_CAP_BANNER_THRESHOLD` (§3).
2. `schemas.py`: add `BoostSummaryResponse`; extend `SubscriptionStatusResponse` (7 fields, zero-defaults).
3. `services/subscriptions.py`: extend constants import; fill the 7 keys in both branches of `get_subscription_status` (floor via `BOOST_PRICE_STARS.get("Other", min(...))`, comment noting the `boost._OTHER_FLOOR` mirror and why no import).
4. `services/boost.py`: add `list_active_channel_boosts` (join Boost+Item; filters per §2.3; dedupe by item_id; order ends_at asc).
5. `api/routes/channels.py`: add `_monetization_enabled_or_503`, imports, and `GET /{channel_id}/boosts` (403 non-owner, 503 kill switch, `List[BoostSummaryResponse]`).
6. `api/routes/alerts.py`: replace the cap-rejection detail string (upgrade path appended; exact wording in §2.4.5).
7. Backend tests (§5) — extend `test_subscriptions.py`, `test_boost.py`, `test_alert_cap_regression.py`. Run affected suites; then the full suite. **Do not proceed until green.**

**Frontend hub**
8. Create `useBoosts.js`.
9. Create `MonetizationHub.jsx`:
   - Tab state driven by `useParams().tab`, validated against the three values, default `all-in-one`; tab switch via `navigate('/hub/<tab>')` (URL is the single source of truth — deep links and back-button work).
   - Header with back arrow (`navigate(-1)`) + title.
   - `getStatus()` on mount (and `fetchAlerts()` if `!hasBeenFetched`); loading state while `subLoading`; if `status === null` after load → unavailable state, no buy actions.
   - **Boost tab:** if `?item` present → `useBoost(itemId)` + `refreshQuote()`; on success show the item's exact `quote.price_stars` + "Boost this item" (`payWithStars`) + active-boost state if `quote.active_boost`; on quote failure (403/404/503) fall back to the guide state. No item → "from {status.boost_floor_price_stars} Stars" + "Choose a product" → `navigate('/stores')`. **Never a category table.**
   - **Alerts tab:** "You're at {alerts.length} of {status.effective_cap} active alerts", "+{status.extra_alerts} more for {status.alerts_only_price_stars} Stars", buy → `openInvoice('alerts_only')`; if `status.product` set → subscribed state instead of buy.
   - **All-in-One tab:** superset list (intelligence + credit + extra alerts), credit counter `credit_remaining/credit_total`, price, buy → `openInvoice('all_in_one')`.
   - **"How Stars work" explainer:** one collapsible local component rendered on all tabs (what Stars are; buy via Telegram's flow; 30-day auto-renew + cancel-anytime for subscriptions; one-time for boosts).
   - **Cross-sell one-liners:** Boost → All-in-One (2 free boosts/period + insights); Alerts → All-in-One (superset); All-in-One → "Need visibility now? Buy a boost" → Boost tab.
10. `App.jsx`: register `/hub/:tab?` and `/stores`; `MainLayout` gains `initialTab`.

**Frontend entry points**
11. `AlertsPage.jsx`: add `useSubscription` effect (`getStatus()` on mount); banner between the header (ends line 142) and the Active Alerts section (line 144) per §2.4.1; tap → `navigate('/hub/alerts')`.
12. `StoresPage.jsx`: delete the Alerts-Only button; All-in-One button → `navigate('/hub/all-in-one')`; add the boost management card (fetches via `useBoosts().fetchBoosts(channels)` on mount; item title + time remaining; "Boost a product" → `/hub/boost`; upsell → `/hub/all-in-one`).
13. `SellerIntelligenceDashboard.jsx`: add the unlock button to the locked prompt (lines 205-218) → `navigate('/hub/all-in-one')`.
14. `ProductEditPanel.jsx`: add the "Learn more" link in the non-boosted branch of the boost section (after the explanatory copy, ~line 260) → `navigate('/hub/boost?item={item.id}')`.

**Tests → verification → docs ride-along → atomic commit**
15. Frontend tests (§5); `npm test` + `npm run build` green; grep gates (§6).
16. `graphify update .` to refresh the AST graph.
17. **Atomic commit (single commit, @qa-approved):** the code + the docs ride-along already in the working tree — `docs/behaviors/monetization.md` (§10), `docs/behaviors/pending-behaviors.md` (NB-48), `CONTEXT.md`, and this blueprint (`docs/plans/monetization-hub-blueprint.md`). **Do NOT stage** the unrelated working-tree debris: deleted `index_gebeya_ultra_premium_landing_page.tsx`, deleted `landing-page-prompt.md`, and `opencode.zip` — flag to @architect for a separate decision.

## 5. Testing Requirements

**Backend (pytest, house patterns: `db_session` fixture, `TestClient` + `include_router` + `dependency_overrides[get_db]`, `monkeypatch.setattr(...)` for kill switch)**
- `test_subscriptions.py` — extend `TestGetSubscriptionStatus`: without subscription → `free_cap == MAX_ALERTS_PER_USER`, `effective_cap == MAX_ALERTS_PER_USER`, `cap_banner_threshold == ALERT_CAP_BANNER_THRESHOLD`, price/duration fields present; with `all_in_one` sub → `effective_cap == MAX_ALERTS_PER_USER + ALERTS_SUBSCRIPTION_EXTRA_ALERTS`, prices present.
- `test_boost.py` — `TestMonetizationConstants` gains: `ALERT_CAP_BANNER_THRESHOLD` default 2, env override honored, negative env clamps to 0. New `TestChannelBoostsRoute` (router include pattern from `test_boost.py:586`): owner sees active boost with shape `[item_id, title, ends_at, source]`; expired boost excluded; sold-item boost excluded (via `end_boost_for_item`); non-owner → 403; `monkeypatch.setattr("api.routes.channels.MONETIZATION_ENABLED", 0)` → 503.
- `test_alert_cap_regression.py` — extend `test_route_free_tier_rejects_above_cap` (line 147): detail contains the hub upgrade-path phrase; existing assertions untouched.
- Honest note: the threshold constant is a frontend display threshold — the backend test is constants-loading + status-payload coverage (as above), nothing more.

**Frontend (vitest + @testing-library/react + MemoryRouter + `vi.mock` hook/config pattern from `AlertsPage.test.jsx`)**
- `MonetizationHub.test.jsx` (new): deep-link opens correct tab (`/hub/boost`, `/hub/alerts`, `/hub/all-in-one`); invalid tab (`/hub/bogus`) falls back to All-in-One; no-rate-card (Boost tab shows "from X Stars" floor and never a table — `queryByRole('table')` null); `?item=42` shows exact price + "Boost this item" (mock `useBoost`); kill switch (mock `getStatus` rejecting) → no buy actions + unavailable state; How-Stars explainer toggles on each tab; cross-sell line present per tab.
- `AlertsPage.test.jsx` (extend): banner visibility math — 18/20 with threshold 2 → shown; 17/20 (3 > 2) → hidden; at cap 20/20 → shown; tap navigates to `/hub/alerts` (render inside `Routes` with a stub `/hub/alerts` element and assert it appears).
- `StoresPage.test.jsx` (new): "Upgrade to Alerts Only" absent and no `alerts_only` invoice call; All-in-One CTA navigates to `/hub/all-in-one` (stub route); boost card renders item title + time remaining + "Boost a product" → `/hub/boost`; zero-boosts empty state still renders the card; boosts fetch failure hides the card.
- `SellerIntelligenceDashboard.test.jsx` (new): `is_pro: false` → prompt + unlock CTA navigates to `/hub/all-in-one`; `is_pro: true` → intelligence block renders (regression).

## 6. Verification (commands @build must run)
- `cd backend && python -m pytest tests/test_subscriptions.py tests/test_alert_cap_regression.py tests/test_boost.py -q` → then full `python -m pytest -q`.
- `cd frontend && npm test` (vitest run) and `npm run build` (vite build).
- Grep gates (must return no violations):
  - No rate card in hub: no `BOOST_PRICE_STARS` import and no table markup in `frontend/src/pages/MonetizationHub.jsx`.
  - `openInvoice` call sites limited to `MonetizationHub.jsx` (buy actions) + definition in `useSubscription.js`; **zero** in `StoresPage.jsx`/`AlertsPage.jsx`.
  - `alerts_only` / "Upgrade to Alerts Only" absent from `StoresPage.jsx` (status label "Alerts Only Subscription" may remain — it is a status, not an offer).

## 7. Drift Report (locked decisions vs verified current state)
1. **SubscriptionStatusResponse** (schemas.py:377-383) — currently `{product, status, current_period_end, extra_alerts, credit_remaining, credit_total}`: **no cap fields, no prices**. Extension required as specified (§2.2). `get_subscription_status` (subscriptions.py:269-290) returns a plain dict in two branches; both need the new keys. Consumers: only `subscription_status_route` + two tests (graphify-verified) → local change.
2. **Boosts-list endpoint** — **does not exist.** Only per-item `GET /items/{id}/boost-quote` (items.py:258). `Boost` model (models.py:267-288) has `user_id/channel_id/item_id/source/ends_at`; `get_boost_status` (boost.py:297) is per-item. Endpoint added as specified (§2.3).
3. **StoresPage card** (StoresPage.jsx:143-204) — single gradient card gated on `subStatus !== null`; non-subscribed branch has two direct-invoice buttons (`openInvoice('alerts_only')` line 187, `openInvoice('all_in_one')` line 194). Subscribed branch shows status (extra_alerts, credit, renews). Restructure as specified.
4. **AlertsPage** (323 lines) — no banner; header ends line 142, active list starts 144. `useAlerts` returns only ACTIVE alerts (`GET /alerts/` filters `is_active == True`), so `alerts.length` is exactly the count the cap guard counts. AlertsPage does not currently call `getStatus` — the effect is added.
5. **App.jsx routes** (112-117) — `/welcome`, `/stores/:channelId/:itemId`, `/*`; `MainLayout` (18-59) has no `initialTab` prop and `useState(deepLink ? 'stores' : 'explore')` — both need the additive change for the `/stores` pick-an-item target.
6. **Locked-Pro prompt** — SellerIntelligenceDashboard.jsx:205-218: **inert card** (text only, no CTA, no navigation import). Button + `useNavigate` added.
7. **ProductEditPanel boost section** (236-303) — already at top with direct buy + credit buttons; **no learn-more affordance exists** — the minimal hub link is added, nothing restructured.
8. **Cap rejection message** — alerts.py:45, route-level; tests assert only substrings (test_alert_cap_regression.py:155, and service-level at 90/114 untouched) → append safe.
9. **Kill switch** — status/quote 503s exist (subscriptions.py:27-31, items.py:266); channels.py has no 503 helper yet — added with the route.
10. **Prices** — absent from all GET endpoints; the status-response extension is the only minimal seam (verified).

# Pending Behaviors — Gap Ledger

> **Purpose:** This document maps every known behavioral gap, missing rule, or unhandled edge case in the system. Each entry is a uniquely identified ticket with a concrete user-acceptance criterion.
>
> **Cleanup note (2026-08-01):** All previously-implemented tickets (NB-33..NB-42) have been moved to the **Archive** section at the bottom. Only genuinely-pending tickets live in the active list below.

---

# ACTIVE TICKETS

## NB-17: Product Gallery Inconsistency in API Responses (existing, low priority)

*(Unchanged — retained from original ledger)*

---

## NB-18: Expired Alerts Are Never Permanently Removed (existing, low priority)

*(Unchanged — retained from original ledger)*

---

## NB-19: Missing Product Condition and Location in Frontend Display (existing, low priority)

*(Unchanged — retained from original ledger)*

---

## NB-20: LLM Judge "Fail-Open" Does Not Distinguish Between Error Types (existing, low priority)

*(Unchanged — retained from original ledger)*

---

## NB-43: [IMPLEMENTED] Boost — Purchase & Pinned Placement

**Priority:** HIGH
**Affected Features:** Monetization, Search, Stores
**File(s):** `backend/constants.py` (prices/duration table), `backend/services/boost.py` (new), `backend/api/routes/items.py` (boost endpoints), `frontend/src/components/ProductEditPanel.jsx` (Boost action), `frontend/src/components/ItemCard.jsx` (Boosted badge)
**Behavior doc:** `docs/behaviors/monetization.md` §§1–3

**The Gap:**
Sellers have no way to pay for visibility. The platform gives all traffic away free, with no revenue stream.

**User Acceptance Criteria:**
- A channel owner can purchase a **Boost** for any item in their channel for a fixed price in **Telegram Stars**.
- A boost has exactly **one duration: 7 days** — no tiered durations exist anywhere in the UI or backend.
- The price varies by the item's **top-level category**, defined in a single configuration table (`BOOST_PRICE_STARS`); "Other/Uncategorized" is the floor price. Prices are flat — no ladder, no auction, no bidding.
- The seller sees the price **only on the specific item they are boosting** ("Boost this item for 7 days — 150 Stars"); no global price list or rate card is ever shown.
- Only the channel owner (`registered_by`) can boost items in their channel. Buyers see no boost UI.
- A boosted item appears **pinned at the top** of (a) its own category browse view and (b) search results whose query matches its title or category.
- A boosted item **never** appears in the For You feed.
- Every boosted card carries a visible **"Boosted" badge**; the boosted item is excluded from the organic list below so it never appears twice on one page.
- The search relevance algorithm itself is unchanged — boosting is a pinned layer applied on top of results, not a score modification.
- Failed or cancelled Stars payment leaves the item unboosted and charges nothing.

---

## NB-44: [IMPLEMENTED] Boost — Rotation & Item Lifecycle

**Priority:** HIGH
**Affected Features:** Monetization, Search
**File(s):** `backend/services/boost.py`, `backend/constants.py` (`BOOST_ROTATION_MINUTES`), `backend/services/item_status.py` (sold/relist hooks), `backend/api/routes/ingestion.py` (dedup hook)
**Behavior doc:** `docs/behaviors/monetization.md` §§4, 6

**The Gap:**
Without rules for many simultaneous boosters and item-status changes, the pinned block becomes unfair or broken.

**User Acceptance Criteria:**
- **No slot cap:** every boosted item in a category shows in the pinned block, regardless of how many sellers boost simultaneously.
- The **order within** the pinned block rotates on a fixed cadence (`BOOST_ROTATION_MINUTES`, default 30) computed from the clock at page-load — no background jobs, no mutable state. No booster permanently owns position #1.
- A boost's 7 days run in wall-clock time; rotation position never pauses or extends them.
- If a boosted item is marked `sold` or `reported_sold`, the boost **ends immediately** and the item leaves the pinned block. No refund.
- If a boosted item is **dedup-replaced** (TECH-21), the remaining boost time **transfers to the replacement item**.
- Editing a boosted item's title/price/specs does not interrupt the boost.
- When the 7 days elapse, the item returns to its organic position silently.

---

## NB-45: [IMPLEMENTED] Boost — Telegram DM Button

**Priority:** MEDIUM
**Affected Features:** Listener, Monetization, Stores
**File(s):** `listener/worker.py` (processing DM), `listener/bot_ui.py` or `listener/client.py` (button + deep link), `frontend/src/App.jsx` (deep-link routing), `frontend/src/components/ChannelInventory.jsx` (land on exact product)
**Behavior doc:** `docs/behaviors/monetization.md` §5

**The Gap:**
The highest-conversion moment — the moment an item gets indexed and the owner is reading the success DM — has no monetization entry point.

**User Acceptance Criteria:**
- Every item-result DM to a channel owner carries a **"🚀 Boost this product"** button: both the "✅ Indexed" processing DM and the "✅ Updated: ... replaced your previous listing" dedup DM.
- Tapping the button opens the Mini App at the seller's Stores tab → that channel's inventory → the product edit panel for the **exact item**, with the Boost action visible (price shown in context, never a rate card).
- The button text is generic; the price appears only inside the boost UI.
- The deep link carries the item identity so the app lands on the right product even if the seller has many channels.

---

## NB-46: [IMPLEMENTED] Subscriptions — Alerts-Only & All-in-One

**Priority:** HIGH
**Affected Features:** Monetization, Alerts, Stores
**File(s):** `backend/models.py` (subscription record), `backend/services/subscriptions.py` (new), `backend/api/routes/alerts.py` (cap check), `backend/constants.py` (prices, allowances), `listener/` (payment update handlers), `frontend/src/pages/StoresPage.jsx` (purchase UI)
**Behavior doc:** `docs/behaviors/monetization.md` §7

**The Gap:**
Sellers who flip products need more alerts than the free cap, and power sellers need an all-in-one paid tier. No subscription product exists.

**User Acceptance Criteria:**
- Two subscription products, both paid in Stars via **Telegram's native Star Subscriptions** (`createInvoiceLink` + `subscription_period`) — **auto-renewing 30-day periods** (Telegram hard-locks the period to 30 days; there is no 28-day option and no trial parameter). Each charge arrives as `successful_payment` with `is_first_recurring`/`is_recurring`/`subscription_expiration_date`; cancellations arrive as `subscription` updates (`canceled | active | failed`); operator-side cancellation via `editUserStarSubscription`.
- **Alerts-Only:** raises the seller's active-alert cap by `ALERTS_SUBSCRIPTION_EXTRA_ALERTS` (default +10).
- **All-in-One:** includes the Seller Intelligence block (NB-47), `ALL_IN_ONE_MONTHLY_BOOST_CREDIT` boosts per period (default 2, usable on any of the seller's items in any category), and the same extra-alert cap as Alerts-Only (superset).
- Unused monthly boost credit **expires** at the end of the 30-day period — no rollover.
- Subscription credit and standalone paid boosts are separate: a seller can buy paid boosts while credit remains; credit and paid boosts are indistinguishable in placement/rotation.
- When a subscription lapses, benefits stop; extra active alerts beyond the free cap are **paused, not deleted** — they survive and reactivate on renewal. Lapse-deactivation must be distinguishable from user-initiated pause in the data model.

---

## NB-47: [IMPLEMENTED] Seller Intelligence Dashboard

**Priority:** MEDIUM
**Affected Features:** Stores, Monetization
**File(s):** `backend/services/stats.py` or `backend/api/routes/channels.py` (aggregation endpoints), `frontend/src/components/InventorySettingsTab.jsx` or new dashboard tab
**Behavior doc:** `docs/behaviors/monetization.md` §8

**The Gap:**
Channel owners have no insight into whether their listings work — no views, no match awareness, no price context — and the All-in-One subscription has nothing to gate.

**User Acceptance Criteria:**
- **Core block (free, all owners):** per-item view counts with 7-day sparkline (real interaction data); "X buyers have active alerts matching your items" with matching items listed; "your item was sent to Y buyers" with bullseye/ring breakdown.
- **Intelligence block (All-in-One only):** price positioning ("your price is X% above/below the median for [category] this week"); category pulse (new items/week with week-over-week comparison); top performers ranked by views.
- Gating: an owner without the subscription sees the Core block and a clear upgrade prompt for the Intelligence block; with it, everything renders from live data.
- No fake or estimated numbers anywhere — every figure traces to real interaction/notification/catalog data.

## NB-48: [IMPLEMENTED] Monetization Hub & Entry Points (Discoverability)

**Priority:** MEDIUM
**Affected Features:** Monetization, Stores, Alerts, Frontend
**File(s):** `frontend/src/pages/MonetizationHub.jsx` (new), `frontend/src/pages/AlertsPage.jsx` (cap banner), `frontend/src/pages/StoresPage.jsx` (boost management card replaces old subscription card), `frontend/src/components/SellerIntelligenceDashboard.jsx` (locked-block upgrade prompt), `frontend/src/components/ProductEditPanel.jsx` (boost section already at top — hub link), `frontend/src/hooks/useSubscription.js` / `useBoost.js`, `frontend/src/App.jsx` (hub route), `backend/constants.py` (cap-banner threshold)
**Behavior doc:** `docs/behaviors/monetization.md` §10

**The Gap:**
The three paid products are undiscoverable. The Alerts-Only subscription was offered from the Stores tab where it makes no sense; the Alerts tab gives no hint that alerts are limited; and every entry point jumped straight to the Stars invoice with no value explanation. The user explicitly directed: entry at the moment of need, an explanatory page before payment, never a bare redirect to payment.

**User Acceptance Criteria:**
- **Alerts tab:** a cap-awareness banner appears when the seller is at or near the free alert cap ("You're at 18 of 20 active alerts — get 10 more"; threshold configurable in constants). When alert creation is rejected at the cap, the error includes the upgrade path.
- **Stores tab:** the old "Alerts-Only upgrade" subscription card is REMOVED (it made no sense in Stores). Replaced by a boost management card showing active boosts (item + time remaining), a "Boost a product" action, and the All-in-One upsell. The All-in-One card stays in Stores.
- **Monetization Hub (new page):** one page, three tabs — Boost / Alerts / All-in-One. Deep-linkable per tab; opens on the tab matching the entry point. Boost tab shows "from X Stars" (floor) or the exact price of a preselected item — NEVER a category rate card (Rule 2.4). Alerts tab shows the seller's own usage count. All-in-One tab lists the full superset (intelligence + boost credit + extra alerts).
- **Shared "How Stars work" explainer** on the hub: what Stars are, how to buy, 30-day auto-renew + cancel-anytime for subscriptions, one-time for boosts.
- **No bare redirect to payment:** the Stars invoice opens only from the hub's buy action or an item's boost section. Every entry point (banner, card, prompt) leads to the hub first.
- **Insights (locked Pro block):** non-subscribers see an upgrade prompt ("Unlock price positioning, category pulse & top performers") that opens the hub on the All-in-One tab.
- **Cross-sell:** each hub tab carries a one-line upsell to the next tier.
- Backend: `constants.py` gains the cap-banner threshold (e.g., `ALERT_CAP_BANNER_THRESHOLD`, default 2 alerts below cap); hub data (usage counts, active boosts, prices, subscription status) served via existing endpoints — no new payment logic.
- Tests: frontend tests for banner visibility at threshold, hub tab routing/deep-link, no-rate-card rendering; backend test for the threshold constant behavior. Full regression green.

## NB-49: Ops Console — Shell, Auth & Scaffolding

**Priority:** HIGH
**Affected Features:** Admin, Ops
**File(s):** `frontend/src/pages/OpsConsole.jsx` (new), `frontend/src/App.jsx` (route `/ops`), admin auth session (new, separate namespace from sqladmin), `backend/api/routes/ops_auth.py` (new), `backend/models.py` (`audit_log`, `admin_settings`), `backend/services/audit.py` (new), `backend/services/settings_registry.py` (new), `backend/main.py` (migrations)
**Behavior doc:** `docs/behaviors/ops-console.md` §§1–2

**The Gap:**
All platform operations today are env config + restarts + raw sqladmin row-editing. There is no curated, audited, action-oriented operations surface — and no shell to grow one without patchwork.

**User Acceptance Criteria:**
- `/ops` route renders a standalone admin page (no bottom nav, no Telegram embed), gated by admin credentials (username/password → session) in a **separate session namespace from sqladmin** (console login ≠ sqladmin access).
- Left-rail nav lists **all ten sections** (§2 map); unimplemented sections render a "Coming soon" stub — the shell shape never changes as sections ship.
- The auth seam carries a `role` field internally (always `admin` in v1); permission checks call `has_role(session, "admin")` so future roles are data changes, not code changes.
- **One audit wrapper**: every console mutation writes `audit_log` rows `{admin_user, action, section, entity_type, entity_id, before, after, created_at}` via the single mutation path. Audit rows are never deleted.
- **Settings registry**: `admin_settings` typed KV table + registry `(key, type, current_value, source: db|env, description)`; powers the effective-config view.
- Shared component kit (table, empty-state, confirm, toast, inline-edit) used across all sections.
- Backend: `/ops/health` probe endpoint skeleton + auth endpoints; migrations for `audit_log` + `admin_settings`.
- Tests: auth separation (console session doesn't open sqladmin), audit wrapper writes rows on mutation, settings registry reads/writes with source labeling, route gating (no console access unauthenticated). Full regression green.

---

## NB-50: Ops Console — Section 1: Overview (full implementation)

**Priority:** HIGH
**Affected Features:** Ops, Ingestion, Schedulers
**File(s):** `backend/api/routes/ops_health.py` (new), `backend/models.py` (`scheduler_runs` table), `backend/services/cleanup.py` + `backend/services/reconciliation.py` + `listener/photo_refresher.py` (write `scheduler_runs`), listener heartbeat (new), `frontend/src/sections/OpsOverview.jsx` (new)
**Behavior doc:** `docs/behaviors/ops-console.md` §3

**The Gap:**
No single screen answers "is the platform healthy right now?" — service status, bot health, ingestion throughput, AI failover, scheduler runs, and money signals are scattered across logs and sqladmin.

**User Acceptance Criteria:**
- Service health: api/listener/frontend/db up-down, uptime, restart counts (poll ≤ 30s, data labeled with age).
- Bot health: Telegram connection state, update lag, handler error rate (last hour).
- Ingestion worker: queue depth, items/hour, rate-limit headroom, AI-provider status + failover events (24h).
- Schedulers: for cleanup, reconciliation, photo refresher — last run, last success, last error (requires the new `scheduler_runs` table written by each job; instrumentation gap closed).
- Money signals: star balance, pending/unfulfilled payment count.
- No fake numbers anywhere — every figure traces to a real probe or table.
- Tests: health endpoint shape, scheduler_runs writes, stale-data labeling. Full regression green.

---

## NB-51: Ops Console — Section 6: Monetization (pricing, toggles, revenue, moderation, test tools)

**Priority:** HIGH
**Affected Features:** Monetization, Ops
**File(s):** `backend/models.py` (`boost_prices` table), `backend/services/boost.py` (price reads go DB-first with cache + invalidation; seed from constants on startup), `backend/services/settings_registry.py` (feature toggles + subscription settings as DB flags), `backend/api/routes/ops_monetization.py` (new), `frontend/src/sections/OpsMonetization.jsx` (new)
**Behavior doc:** `docs/behaviors/ops-console.md` §4; `docs/behaviors/monetization.md` Rules 1.3/2.2/2.3 (amended)

**The Gap:**
Boost prices are env config requiring restarts; no demand context; feature kill switches require env edits; revenue is invisible; moderation is sqladmin row-hacking.

**User Acceptance Criteria:**
- `boost_prices` table (category, subcategory, price_stars, updated_at, updated_by), seeded from `BOOST_PRICE_STARS` defaults on startup; `get_boost_price` reads DB-first (fallback chain: subcategory → category → Other floor) with a small cache invalidated on edit; **edits take effect instantly, no restart**.
- Pricing screen: subcategories grouped by category, each row `Subcategory | Price | Active boosts | Boosts this week` (demand context from `boosts` joined to items); inline edit with confirm; bulk actions "Set category", "+N% across category", "Reset to floor".
- Feature toggles as instant DB flags: `MONETIZATION_ENABLED`, boost purchases, subscription purchases, credit boosts — 503/UI-hide behavior preserved exactly.
- Subscription settings visible + editable live: alerts-only price, all-in-one price, extra-alert allowance, monthly credit.
- Revenue dashboard: Stars earned (from `getStarTransactions` ledger), active subs, active boosts, expiring-soon (24h). Real data only.
- Boost moderation: curated active-boost list (item/channel/source/ends-at/price); **end boost early** action invoking existing `end_boost_for_item`, audit-logged, no refunds.
- Price edits never disturb in-flight purchases (invoice fixed at creation).
- Tests: seed-on-startup, DB-first fallback chain, cache invalidation on edit, instant toggle effect (503 path), demand-context counts, end-early moderation, in-flight price stability. Full regression green.

---

## NB-52: Ops Console — Sections 8 & 9: Settings & Flags + Audit

**Priority:** HIGH
**Affected Features:** Ops
**File(s):** `backend/services/settings_registry.py` (complete registry surface), `backend/api/routes/ops_settings.py` (new), `backend/api/routes/ops_audit.py` (new), `frontend/src/sections/OpsSettings.jsx` (new), `frontend/src/sections/OpsAudit.jsx` (new)
**Behavior doc:** `docs/behaviors/ops-console.md` §§5–6

**The Gap:**
Operational knobs live in env files; there is no effective-config view and no audit trail for console actions.

**User Acceptance Criteria:**
- Settings registry surfaces every operational knob (monetization flags, alert cap, banner threshold, rotation minutes, retention days, LLM fail-open policy): description, live value, source (db/env).
- DB-sourced knobs: editable with confirm + audit, instant effect. Env-sourced knobs: read-only with "requires deploy" labeling — the console never claims an edit took effect when it didn't.
- Effective-config view: full current configuration, DB overrides on top of env defaults, source-labeled.
- Audit section: read-only list of every console mutation, filterable by section and admin; no edits/deletes.
- Tests: registry read/write + source labeling, env-vs-db precedence, audit list filtering, read-only enforcement. Full regression green.

---

## NB-53: Ops Console — Section 7: Payments

**Priority:** MEDIUM
**Affected Features:** Monetization, Payments
**File(s):** `backend/api/routes/ops_payments.py` (new), `frontend/src/sections/OpsPayments.jsx` (new)
**Behavior doc:** `docs/behaviors/ops-console.md` §7

**The Gap:**
Star revenue and payment state are invisible outside logs; reconciliation has no run-now control; refunds require raw API calls.

**User Acceptance Criteria:**
- Star transaction ledger (from `getStarTransactions`), current balance, last reconciliation run + result.
- Reconciliation run-now button triggering the existing daily reconciliation immediately, result displayed.
- Refund action via `refundStarPayment` for a specific charge id, confirm + audit + warning dialog.
- Tests: ledger rendering, run-now invocation, refund guard rails. Full regression green.

---

## NB-54: Ops Console — Section 10: Support Toolkit

**Priority:** MEDIUM
**Affected Features:** Ops, Monetization, Stores
**File(s):** `backend/api/routes/ops_tools.py` (new), `frontend/src/sections/OpsTools.jsx` (new)
**Behavior doc:** `docs/behaviors/ops-console.md` §8

**The Gap:**
UAT and support workflows require sqladmin row-inserts (test boosts/subscriptions) and there is no way to simulate a payment fulfillment or generate deep links.

**User Acceptance Criteria:**
- One-click TEST boost grant (item) and TEST subscription grant/revoke (user): clearly labeled TEST, audit-logged, no real payment.
- **Payment-webhook simulator**: trigger a synthetic `successful_payment` fulfillment for a charge id + payload — the exact listener flow, without Telegram. The primary UAT tool for the monetization stack.
- Deep-link generator: Mini App links to any item/channel for support handoffs.
- All actions: explicit confirmation, audit rows, never touch real Telegram payments.
- Tests: simulator drives the same fulfillment path as the real listener flow (idempotency included); grant/revoke guards. Full regression green.

---

# ARCHIVE — Implemented Tickets

> Cleanup note (2026-08-01): these tickets are fully implemented and shipped. They remain here for history only.

## NB-33: Landing Page — Full API Integration (Real Data) [IMPLEMENTED]
## NB-34: Landing Page as Telegram Mini App Onboarding [IMPLEMENTED]
## NB-35: Design System — Landing Page UI Adopted Across Webapp [IMPLEMENTED]
## NB-36: Bottom Navigation Bar — Explore, Alerts, Stores [IMPLEMENTED]
## NB-37: Stores — Channel Owner Dashboard [IMPLEMENTED]
## NB-38: Processing Notifications & Store Management (Pause/Remove) [IMPLEMENTED]
## NB-39: Alert Guardrails — Configurable Limits, Auto-Pause, Throttle, Dedup [IMPLEMENTED]
## NB-40: Dedup Redesign — Soft-Delete + Recreate + Alert Filter Badges [IMPLEMENTED]
## NB-41: Crowdsourced Sold Reports & Product Status Lifecycle [IMPLEMENTED]
## NB-42: Inventory Management — Store Owner Product Control [IMPLEMENTED]

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

## NB-48: Monetization Hub & Entry Points (Discoverability)

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

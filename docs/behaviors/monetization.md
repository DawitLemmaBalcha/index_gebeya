# Monetization — Boost, Subscriptions & Seller Intelligence

> **Status:** ✅ IMPLEMENTED (2026-08-04, commits 22c3ea1..cb68aab on feat/monetization, QA APPROVED)

---

## Overview

Three revenue products, all paid in **Telegram Stars** (the only payment rail — a deliberate decision; Stars flow one way, seller → platform):

1. **Boost** — a one-time purchase: pin an item to the top of its category and relevant searches for a fixed duration.
2. **Alerts-Only Subscription** — unlocks extra active alerts beyond the free cap.
3. **All-in-One Subscription** — seller intelligence dashboard + monthly boost credit + extra alerts.

The free marketplace experience (browsing, searching, buying, alerts at the free cap, channel listing) is **never gated**. We monetize attention, not access.

---

## 1. Payment Rules (Global)

**Rule 1.1 — Stars Only.** Every monetized action (boost, subscriptions) is paid exclusively in Telegram Stars. No ETB, no cards, no other rails in v1.

**Rule 1.2 — One-Way Flow.** Stars are a collection rail only. The platform never pays sellers out in Stars. Refunds are not issued for boost time or subscription time (see Boost Lifecycle for the one exception: dedup replacement transfers the boost).

**Rule 1.3 — Configuration.** Every price, duration, rotation cadence, and subscription allowance lives in `backend/constants.py` with environment-variable overrides (house pattern). No hardcoded monetization numbers anywhere.

---

## 2. Boost — Purchase

**Rule 2.1 — One Duration, No Tiers.** A boost is a single unit: **7 days** (`BOOST_DURATION_DAYS`, default 7). There is no 3-day or 14-day option. Deliberately simple — one price, one duration.

**Rule 2.2 — Price by Top-Level Category.** Boost price varies by the item's top-level category (e.g., phones/electronics cost more than makeup/stationery). Prices are defined per category in a single configuration table (`BOOST_PRICE_STARS` keyed by top-level category). The "Other / Uncategorized" bucket gets the floor price. Subcategory-level pricing does not exist.

**Rule 2.3 — No Ladder, No Auction.** The price for a category is a flat published number. It is adjusted **manually** by the operators when the volume of boosters changes materially (more boosters → raise price; fewer → lower). There is no automatic price-ladder trigger and no bidding. A seller must never see the price move reactively between two visits to the same category.

**Rule 2.4 — Price Shown In Context, Never As a Rate Card.** The seller only ever sees the boost price **on the specific item they are boosting** ("Boost this item for 7 days — 150 Stars"). The platform never displays a global boost price list, so sellers never compare category prices against each other.

**Rule 2.5 — Eligibility.** Only the channel owner (the user who registered the channel via `registered_by`) can boost items belonging to their channels. Buyers cannot boost.

**Rule 2.6 — Purchase Entry Points.** A boost can be purchased from:
- The product edit panel in the seller's dashboard (Stores tab → channel inventory → product), showing the price for that item's category.
- The "🚀 Boost this product" button on the Indexed/Updated Telegram DM (see Section 5), which deep-links into that exact product's panel.

**Rule 2.7 — Payment Flow.** Tap "Boost with Stars" → Stars invoice → on success, the item is boosted immediately and the seller sees confirmation. Failure/cancellation leaves the item unboosted and charges nothing.

---

## 3. Boost — Placement (Where It Appears)

**Rule 3.1 — Relevance-Gated Surfaces.** A boosted item appears pinned at the top of exactly two surfaces:
- **Category browse** — the browse view of the item's own top-level category.
- **Search results** — searches whose query matches the item's title or category.

**Rule 3.2 — Never In the For You Feed.** Boosted items never appear in the personalized recommendation feed. The feed is the product's trust core and is per-user; boosting has no place there.

**Rule 3.3 — Merged Pin, Labeled.** The boosted item occupies the **top position of the organic results list** (not a visually separate "ads" block), and every boosted card carries a visible **"Boosted" badge**. The label protects buyer trust; the position sells the product.

**Rule 3.4 — No Duplicates on a Page.** A boosted item that occupies the pinned position is excluded from the organic list below it — it never appears twice on the same page.

**Rule 3.5 — Relevance Math Untouched.** The search relevance algorithm itself is not modified. Boosting is a **pinned layer applied on top of the results** — the underlying ranking scores are unchanged; boosting only affects which items occupy the reserved top positions of eligible surfaces.

---

## 4. Boost — Rotation & Multiple Boosters

**Rule 4.1 — No Slot Cap.** Every boosted item shows in the pinned block of its eligible surfaces. If 30 sellers boost the same category, all 30 appear at the top — buyers scroll past them to reach organic results. Saturation is regulated by **price**, never by hiding paying customers.

**Rule 4.2 — Time-Sliced Order Rotation.** Within the pinned block, the *order* of boosted items rotates on a fixed cadence (`BOOST_ROTATION_MINUTES`, default 30). No booster permanently owns position #1. The rotation is computed from the clock at page-load time — deterministic, no background jobs, no mutable state.

**Rule 4.3 — Wall-Clock Duration.** A boost's 7 days run in real time. Rotation position never pauses or extends the clock; if the boost expires mid-cycle, the item simply drops out of the pinned block.

---

## 5. Boost — Telegram DM Button

**Rule 5.1 — Button on Item DMs.** Every item-result DM to a channel owner carries a **"🚀 Boost this product"** button:
- The "✅ Indexed: [Title] — [Price] ETB" processing DM.
- The "✅ Updated: ... replaced your previous listing" dedup-replacement DM.

**Rule 5.2 — Deep Link to the Product.** Tapping the button opens the Mini App at the seller's Stores tab → that channel's inventory → the product edit panel for the exact item, with the Boost action visible (price shown in context per Rule 2.4). The button text itself is generic; the price appears only in the boost UI.

---

## 6. Boost — Item Lifecycle Collisions

**Rule 6.1 — Item Marked Sold / Reported Sold.** If a boosted item's status changes to `sold` or `reported_sold`, the boost **ends immediately** — the item stops appearing in the pinned block. No refund of the remaining boost time (Stars are final).

**Rule 6.2 — Dedup Replacement.** If a boosted item is soft-deleted and replaced by a duplicate detection (TECH-21), the **remaining boost transfers to the replacement item** — the seller keeps their paid visibility, now on the live listing.

**Rule 6.3 — Item Edited.** Editing a boosted item's title, price, or specs does not affect the boost; it continues for the remainder of its 7 days.

**Rule 6.4 — Natural Expiry.** When the 7 days elapse, the item returns to its organic position with no renewal prompt in the results — renewal is initiated by the seller from the dashboard or a future DM.

---

## 7. Subscriptions

### 7.1 Common Rules

**Rule 7.1.1 — Native 30-Day Auto-Renewing Star Subscriptions.** Both subscriptions are paid in Stars using **Telegram's native Star Subscriptions** (Bot API 8.0+, `createInvoiceLink` + `subscription_period`). The period is **hard-locked by Telegram to 30 days** (2592000 seconds) — there is no 28-day option, and no trial-period parameter exists. Each charge (initial + renewals) arrives as a `successful_payment` update with `is_first_recurring` / `is_recurring` / `subscription_expiration_date`. Cancellation is possible via `editUserStarSubscription`; user-side changes arrive as `subscription` updates with state `canceled | active | failed`. We do not bill manually — Telegram handles the recurring charges.

**Rule 7.1.2 — Benefits Only While Active.** All subscription benefits (extra alerts, dashboard intelligence, boost credit) apply only while the subscription is **active**. Active-ness is derived from the payment/subscription events: `successful_payment` with a future `subscription_expiration_date`, and no `canceled`/`failed` `subscription` update since. When a subscription lapses, the seller returns to free-tier limits. Extra active alerts beyond the free cap are **paused, not deleted** — they survive and reactivate on renewal, and this automated lapse-deactivation must never be conflated with user-initiated pause (separate markers/mechanisms in the data model).

### 7.2 Alerts-Only Subscription

**Rule 7.2.1 — What It Unlocks.** Raises the seller's active-alert cap above the free limit (`ALERTS_SUBSCRIPTION_EXTRA_ALERTS`, default +10). All alert features otherwise behave identically to free alerts.

### 7.3 All-in-One Subscription

**Rule 7.3.1 — What It Includes.**
- **Seller Intelligence block** (see Section 8 — the Pro-only dashboard rows).
- **Monthly boost credit** (`ALL_IN_ONE_MONTHLY_BOOST_CREDIT`, default 2): the subscription includes N boosts per 30-day period, usable on any of the seller's items, in any category (category price is irrelevant — credit is per-boost, not per-Stars).
- **Alerts boost** — same extra-alert cap as the Alerts-Only subscription (it is a superset).

**Rule 7.3.2 — Credit Expiry.** Unused monthly boost credit expires at the end of the 30-day period. It does not roll over (drives usage and keeps accounting simple).

**Rule 7.3.3 — Credit Is Separate From Paid Boosts.** A seller can always buy additional standalone boosts with Stars even while their subscription credit is unused. The two never combine or conflict; credit boosts and paid boosts are indistinguishable in placement and rotation.

---

## 8. Seller Intelligence Dashboard (Pro)

The dashboard appears in the seller's Stores tab, channel-level and item-level. It splits into a **Core block (free, for every channel owner)** and an **Intelligence block (Pro-only, gated by the All-in-One subscription)**.

### 8.1 Core Block (Free)

**Rule 8.1.1 — Views Per Item.** Per-item view counts with a 7-day sparkline. Sourced from real interaction data, not estimates.

**Rule 8.1.2 — Alert Matches.** "X buyers have active alerts matching your items," with the specific matching items listed. This is the platform's structural advantage — intent data no other marketplace has.

**Rule 8.1.3 — Notifications Dispatched.** "Your item was sent to Y buyers" with bullseye/ring breakdown. The closest proxy to a sales signal.

### 8.2 Intelligence Block (Pro-Only)

**Rule 8.2.1 — Price Positioning.** "Your price is X% above/below the median for [category] this week" — computed from active items in the same top-level category.

**Rule 8.2.2 — Category Pulse.** New items indexed per week in the seller's category, with a week-over-week comparison ("23 new phones this week vs 18 last week").

**Rule 8.2.3 — Top Performers.** The seller's items ranked by views, to inform which items to boost.

### 8.3 Deferred (Not in v1)

**Rule 8.3.1 — Traffic source attribution** (search vs category vs feed) — not tracked yet.
**Rule 8.3.2 — Click-through to Telegram conversation** — the future "proof metric" for boost renewal; explicitly the first follow-up build after launch.

---

## 9. Behavior Doc Cross-References

- Alert caps, pausing, expiry: `alert-guardrails.md`
- Dedup replacement lifecycle (boost transfer): `dedup-redesign.md`
- Processing DMs (boost button host): `processing-store-management.md`
- Stores/inventory dashboard (boost + dashboard host): `inventory-management.md`

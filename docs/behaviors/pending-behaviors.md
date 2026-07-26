# Pending Behaviors — Gap Ledger

> **Purpose:** This document maps every known behavioral gap, missing rule, or unhandled edge case in the system. Each entry is a uniquely identified ticket with a concrete user-acceptance criterion.

---

## NB-33: Landing Page — Full API Integration (Real Data) [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Frontend, Search
**File(s):** `frontend/src/pages/LandingPage.jsx`, `frontend/src/components/ItemCard.jsx`

**The Gap:**
The landing page uses 6 hardcoded fake products with Unsplash images. The search bar filters these fakes locally instead of hitting the real `/search/` endpoint. There is no image search. Stats (products indexed, channels monitored) are made-up numbers. The category grid is hardcoded. The phone mockup is purely decorative.

**User Acceptance Criteria:**
- The hero search bar queries the real `/search/` endpoint and renders results using the real `ItemCard` component.
- The camera button triggers real image search via `/search/by-image`.
- The stats bar fetches live counts from a backend endpoint (`SELECT COUNT(*) FROM items`, `SELECT COUNT(*) FROM channels`).
- The category grid is generated dynamically from the taxonomy and shows real item counts per category.
- Every product card uses the existing `ItemCard` component — no fake products, no placeholder data.
- Stats gracefully degrade to "--" if the API is down.

---

## NB-34: Landing Page as Telegram Mini App Onboarding [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Frontend
**File(s):** `frontend/src/App.jsx`, `frontend/src/pages/LandingPage.jsx`

**The Gap:**
There is no onboarding experience inside the Telegram Mini App. Users open the bot and go straight to an empty feed with no context about what the platform does, how it works, or why they should use it. The landing page content exists but is only shown on the open web.

**User Acceptance Criteria:**
- First-time Telegram Mini App users (no `onboarding_seen` in localStorage) see the full landing page content — hero, problem/solution, how-it-works, categories, FAQ.
- All "Open in Telegram" CTAs are replaced with a single "Get Started" button in the Telegram version.
- Tapping "Get Started" sets `onboarding_seen = true` and transitions to the marketplace with infinite scroll, search, and bottom navbar.
- Returning users (with `onboarding_seen`) skip the landing page entirely and go straight to the marketplace.
- The open web version always shows the landing page — no access to the full webapp from a browser.

---

## NB-35: Design System — Landing Page UI Adopted Across Webapp [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Frontend
**File(s):** `frontend/src/index.css`, multiple components

**The Gap:**
The landing page and the webapp have two completely different visual identities. The landing page uses a warm editorial design (paper backgrounds, bold typography, amber accents, Inter + Noto Sans Ethiopic fonts). The webapp uses generic Tailwind grays, a different font (Outfit), a different color scheme, and no visual connection to the landing page. They look like two different products.

**User Acceptance Criteria:**
- The webapp adopts the landing page's color palette: warm paper backgrounds (`#FAF6F0`), amber/gold primary, Ethiopian green accent, dark sections.
- The webapp uses Inter as the primary font and Noto Sans Ethiopic for Amharic text. Outfit is removed.
- The navigation header in the webapp matches the landing page header in height, logo treatment, and style.
- Product cards, category chips, search bar, and all UI elements adopt the warm editorial aesthetic.
- The transition from onboarding landing page to webapp feels like a natural continuation of the same product — not a jarring switch to a different app.

---

## NB-36: Bottom Navigation Bar — Explore, Alerts, Stores [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Frontend
**File(s):** New `BottomNav` component, `frontend/src/App.jsx`, `frontend/src/pages/Home.jsx`

**The Gap:**
The webapp has no persistent navigation. The feed is the only accessible view. Alerts can only be created from product detail pages and managed via bot commands. Channel owners have no interface at all for managing their stores. The experience is flat — one page, no structure.

**User Acceptance Criteria:**
- A bottom navigation bar with three tabs is always visible: Explore, Alerts, Stores.
- **Explore tab:** The current home page experience — infinite scroll feed, search bar, category browsing. This is the default tab.
- **Alerts tab:** List of user's active alerts with pause/delete actions. "Create Alert" button opens the same flow as the current product page alert modal. Match history shows recent notifications with links to products.
- **Stores tab:** Channel owners see their listed channels with stats (product count, views, clicks), pause/resume, and remove actions. Non-owners see a prompt explaining how to list their channel.
- Tab state is preserved when switching — feed scroll position and search state are not lost.
- Each tab loads its content only on first activation (lazy loading).
- The bottom navbar hides when navigating to a product detail page and restores on back.

---

## NB-37: Stores — Channel Owner Dashboard [IMPLEMENTED]

**Priority:** MEDIUM
**Affected Features:** Frontend, Backend
**File(s):** New backend endpoint for store stats, frontend Stores tab

**The Gap:**
Channel owners who add the bot have no way to see their channels' performance or manage their listings. They add the bot and hope it works. There is no pause/resume, no stats, no management interface.

**User Acceptance Criteria:**
- Channel owners see each of their channels as a card with: @username, title, status (Active/Paused), product count, view count, Telegram click-through count.
- **Pause/Resume:** Tapping pauses indexing for that channel (products stay, new posts are ignored). Tapping again resumes.
- **Remove:** Disconnects the channel. Products stay in catalog, future posts are not ingested.
- **Add another:** A persistent card at the bottom with instructions for adding the bot to additional channels.
- Stats are fetched from a backend endpoint that aggregates data per channel. View counts and click-through counts require tracking — this may start as "coming soon" and ship incrementally.
- Non-owners see an educational prompt, not an empty dashboard.

---

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

## NB-38: Processing Notifications & Store Management (Pause/Remove) [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Listener, Stores, Ingestion
**File(s):** `listener/worker.py`, `listener/client.py`, `backend/models.py`, `frontend/src/pages/StoresPage.jsx`

**The Gap:**
Channel owners have no visibility into whether their posts are being processed. Stores tab has non-functional Pause/Remove buttons. No confirmation modals. No auto-leave on remove.

**User Acceptance Criteria:**
- Processing DM: When a post from a registered channel is ingested, the owner gets one DM that starts as "⏳ Processing..." and is edited to "✅ Indexed: [Title] — [Price] ETB" on completion.
- Pause: Confirmation modal → sets `indexing_paused` on channel → bot DMs owner → ingestion skips paused channels.
- Resume: No confirmation needed. Clears flag → bot DMs owner.
- Remove: Confirmation modal → `getChat` + `leaveChat` → mark removed → bot DMs owner.
- DMs only sent to channels with `registered_by` set.

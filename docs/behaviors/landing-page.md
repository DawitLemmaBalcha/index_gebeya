# Landing Page, Onboarding & Design System

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

The landing page is the first impression for all visitors — open web and first-time Telegram users. It must use real data from the API (not placeholder products), support real text and image search, show live marketplace stats, and serve as an onboarding layer inside the Telegram Mini App. The landing page's design language (colors, fonts, typography, spacing) becomes the native look of the entire platform.

---

## Behavioral Rules

### 1. Landing Page Content — All Real Data

**Rule 1.1 — Real Product Search**
The hero search bar queries the actual `/search/` endpoint. Typing a query and pressing enter (or tapping "Search Index") fires a real hybrid search. Results render as product cards using the same `ItemCard` component as the webapp — not fake HTML placeholders. Image search via camera upload hits `/search/by-image`.

**Rule 1.2 — Real Stats**
The stats bar at the top of the page pulls live numbers from a backend endpoint:
- **Products indexed:** `SELECT COUNT(*) FROM items`
- **Channels monitored:** `SELECT COUNT(*) FROM channels`
- **Average search speed:** tracked from recent search execution times
- **Buyer commission:** always "0 Birr" (static, not an API call)

These numbers are fetched once on page load and cached for the session. They do not auto-refresh.

**Rule 1.3 — Real Category Showcase**
The category grid is populated from the actual taxonomy, not a hardcoded list. Clicking a category navigates to the webapp (inside Telegram) or triggers a search on the landing page (open web). Category item counts are real — pulled from the database.

**Rule 1.4 — Real Phone Mockup**
The phone mockup tabs (Search, Alerts, Saved) display real data when the user is authenticated. On the open web, they show demo content. Inside Telegram, the "Alerts" tab shows the user's actual active alerts.

**Rule 1.5 — No Fake Products**
Every product card, every search result, every category count comes from the database. The `sampleProducts` array is deleted. All product rendering uses the existing `ItemCard` component.

### 2. Onboarding Flow — Telegram First Visit

**Rule 2.1 — Landing Page as Welcome Screen**
When a user opens the Mini App for the first time (no `onboarding_seen` flag in `localStorage`), they see the full landing page content — hero, problem/solution, how-it-works, categories, FAQ — but with all "Open in Telegram" CTAs replaced with a single "Get Started" button at the bottom.

**Rule 2.2 — "Get Started" Transitions to Marketplace**
Tapping "Get Started" sets `onboarding_seen = true` in `localStorage` and transitions to the marketplace (the current webapp with infinite scroll, search, alerts, stores). No page reload — smooth in-app transition.

**Rule 2.3 — Returning Users Skip Onboarding**
If `onboarding_seen` is already set, the Mini App opens directly to the marketplace. No welcome screen, no landing page. Straight to the feed.

**Rule 2.4 — Open Web Always Shows Landing Page**
On the open web (browser), the landing page is always shown regardless of localStorage state. There is no way to reach the full webapp from a browser — the webapp is Telegram-only.

**Rule 2.5 — "Open in Telegram" CTAs**
All CTAs that say "Open in Telegram" link to `https://t.me/IndexGebeyaBot`. They appear on the open web version ONLY. They are stripped from the Telegram Mini App version.

### 3. Design System Adoption

**Rule 3.1 — Unified Color Palette**
The entire platform adopts the landing page's color scheme:
- Background: `#FAF6F0` (warm paper) instead of `bg-gray-50`
- Primary: amber/gold spectrum (`#F59E0B` to `#B45309`)
- Accent: Ethiopian green (`#047857`)
- Dark: `#0F0E11` for dark sections
- Cards: white with warm borders

**Rule 3.2 — Unified Typography**
The entire platform uses `Inter` as the primary font and `Noto Sans Ethiopic` for Amharic text. The previous `Outfit` font is removed.

**Rule 3.3 — Consistent Navigation Header**
The landing page header and the webapp NavBar share the same visual design — same height, same logo treatment, same button styles. The only difference is the content: landing page has "Open in Telegram," webapp has search bar and hamburger.

**Rule 3.4 — Warm Editorial Tone**
The visual language of the landing page — generous whitespace, bold typography, warm paper backgrounds, subtle amber accents — carries into the webapp. Product cards, search bar, category chips all adopt the same aesthetic.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| API stats endpoint is down | Stats show "--" instead of numbers. The rest of the page renders normally. |
| Search returns zero results | "No items match this search" message. Suggest different keywords or categories. |
| Image search fails | "Could not process image" toast. Search bar remains functional. |
| localStorage is unavailable (private browsing) | Onboarding always shows. User sees welcome screen every visit. Acceptable degradation. |

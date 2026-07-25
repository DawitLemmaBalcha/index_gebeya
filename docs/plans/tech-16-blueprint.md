# TECH-16 Blueprint: Landing Page — Real API, Onboarding, Design System

> **Date:** 2026-07-25  
> **Parent Tickets:** NB-33, NB-34, NB-35  
> **Priority:** HIGH  
> **Source Docs:** `docs/behaviors/landing-page.md`, `docs/adr/tech-backlog.md`

---

## Goal

Replace hardcoded mock data in the landing page with live API calls, add a backend stats endpoint, implement Telegram onboarding gate in App.jsx, strip "Open in Telegram" CTAs inside Telegram WebView, and unify the design system across the entire platform.

---

## Files to Modify/Create

| Action | File Path |
|--------|-----------|
| MODIFY | `frontend/src/pages/LandingPage.jsx` |
| MODIFY | `frontend/src/App.jsx` |
| MODIFY | `frontend/src/index.css` |
| MODIFY | `frontend/src/components/ItemCard.jsx` |
| MODIFY | `frontend/src/components/home/NavBar.jsx` |
| MODIFY | `backend/api/routes/items.py` |
| MODIFY | `backend/main.py` |

---

## Strict Import Map

### 1. LandingPage.jsx — New Imports

The following imports must be added to `LandingPage.jsx`:

| Import | Source Module | Purpose |
|--------|--------------|---------|
| `API_BASE_URL` | `../config` | Base URL for fetch calls to `/search/` and `/stats` |
| `ItemCard` | `../components/ItemCard` | Render search results using the shared product card component |
| `TAXONOMY` | `../constants/taxonomy` | Generate category grid dynamically from the official taxonomy |
| `useRef` | `react` (existing import already has `useState, useEffect` — add `useRef`) | Reference for hidden file input (camera/image upload) |

### 2. App.jsx — New Imports & Local State

| Import / Addition | Source | Purpose |
|-------------------|--------|---------|
| `useState` | `react` (existing import does NOT include `useState` — must add it) | Manage `showOnboarding` state for the onboarding gate |
| `Telegram` type check | Already present via `isTelegramWebView()` function | No new import needed; function already exists at top of file |

### 3. Backend — New Route & Registration

| Item | Module | Purpose |
|------|--------|---------|
| `router` (APIRouter) | `backend/api/routes/items.py` | Add `GET /stats` endpoint to the existing items router |
| `stats.router` import | `backend/main.py` line 13 | If stats is extracted to a separate file, import it; otherwise no change since items router is already imported |
| `from sqlalchemy import func` | `backend/api/routes/items.py` (already imported via `select`) | Already available; `func.count()` will be used for COUNT queries |

### 4. TAXONOMY — Already Exists (No Changes)

The `frontend/src/constants/taxonomy.js` file is already present and correctly structured. It will be imported read-only into `LandingPage.jsx` to generate the category grid.

### 5. No New Backend Schemas Required

The response shape for `/stats` is simple enough to use a plain `dict` return from FastAPI. No new Pydantic model is required unless the team prefers typed responses. If typed, add:

```python
# In backend/schemas.py, add:
class StatsResponse(BaseModel):
    product_count: int
    channel_count: int
```

---

## Step-by-Step Execution

### Phase 1 — Backend: Stats Endpoint

**Step 1.1** — In `backend/api/routes/items.py`, add a new `GET /stats` endpoint to the existing `router`. The endpoint must:
- Accept `db: Session = Depends(get_db)`
- Execute `SELECT COUNT(*) FROM items` to get `product_count`
- Execute `SELECT COUNT(*) FROM channels` to get `channel_count`
- Return a JSON dict: `{ "product_count": <int>, "channel_count": <int> }`
- Use `db.execute(select(func.count()).select_from(Item)).scalar()` pattern (consistent with existing code style using SQLAlchemy `select`)
- Do NOT add background tasks or analytics logging (this is a simple read endpoint)
- Place the new route BEFORE the `/{item_id}` route to avoid path conflicts

**Step 1.2** — No changes to `backend/main.py` are required for this endpoint because the `items.router` is already registered at prefix `/items`, meaning the new endpoint will be served at `GET /items/stats`. This is acceptable since it logically groups under items.

> **Alternative considered:** A separate `stats.py` route file registered at `/stats`. Rejected to minimize file changes — the items router already exists and the query is trivially simple.

---

### Phase 2 — LandingPage.jsx: Real API Integration

**Step 2.1 — Remove hardcoded data.** Delete the following from `LandingPage.jsx`:
- The entire `sampleProducts` array (lines 3–10)
- The entire `categories` array (lines 12–21)
- The `statProducts` state variable and its animated counter `useEffect` (lines 37–50)
- The `postCount` state variable (line 37)
- The `estimatedReach` derived value (line 76)

**Step 2.2 — Add new state variables.** Add the following `useState` declarations in the component body:
- `searchResults` — initialized to `null`, holds array of items from `/search/` API
- `isSearching` — initialized to `false`, loading state for text search
- `isSearchingImage` — initialized to `false`, loading state for image search
- `stats` — initialized to `null`, holds `{ product_count, channel_count }` from `/stats` API
- `searchError` — initialized to `null`, holds error message for failed searches

**Step 2.3 — Add file input ref.** Add `const fileInputRef = useRef(null)` for the hidden file input that handles camera/image upload.

**Step 2.4 — Fetch stats on mount.** Add a `useEffect` with empty dependency array that:
- Fetches `GET /items/stats` (or `GET /stats` if the endpoint is registered differently)
- On success: parses JSON, sets `stats` state
- On failure: sets `stats` to `{ product_count: null, channel_count: null }` (null values will render as "--" per behavior doc error rules)
- Uses `API_BASE_URL` from config for the fetch URL

**Step 2.5 — Rewrite `handleSearch`.** Replace the current fake-filter logic with a real API call:
- Prevent default form submission
- Trim the query; if empty, clear results and return
- Set `isSearching = true`, clear previous errors
- Fire `POST ${API_BASE_URL}/search/` with JSON body `{ query: searchQuery, limit: 50 }` and header `Content-Type: application/json`
- On success: set `searchResults = data.items`
- On failure: set `searchError` with appropriate message
- Finally: set `isSearching = false`

**Step 2.6 — Add `handleImageSearch` function.** Create a function that:
- Accepts a `File` object
- Sets `isSearchingImage = true`
- Creates a `FormData`, appends the file as `"file"`
- Fires `POST ${API_BASE_URL}/search/by-image` with the FormData body (no Content-Type header — browser sets multipart automatically)
- On success: sets `searchResults = data` (the endpoint returns `List[ItemResponse]`)
- On failure: shows a toast or sets `searchError` with "Could not process image"
- Finally: sets `isSearchingImage = false` and resets the file input value

**Step 2.7 — Add hidden file input in JSX.** Add an `<input type="file" ref={fileInputRef} onChange={...} hidden accept="image/*" />` element inside the search bar area. Wire the camera icon button (which currently does not exist in LandingPage) to trigger `fileInputRef.current.click()`.

**Step 2.8 — Add camera button to search bar.** In the hero search bar (currently a form with text input + "Search Index" button), add a camera button between the text input and the submit button. The button should:
- Be a `<button type="button">` (not submit)
- On click: trigger `fileInputRef.current?.click()`
- Show a camera icon (SVG or Unicode)
- Be visually consistent with the landing page's amber aesthetic

**Step 2.9 — Replace inline product cards with `ItemCard` component.** In the results section (currently lines 164–191), replace the entire grid of inline HTML product cards with:
- A `<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">` container
- Inside: `searchResults.map(item => <ItemCard key={item.id} item={item} apiUrl={API_BASE_URL} onSelect={...} />)`
- The `onSelect` handler should open the Telegram post URL: `window.open(\`https://t.me/${item.channel?.username}/${item.telegram_message_id}\`, '_blank')` — this works for both open web and Telegram onboarding modes
- When `isSearching` is true, show a loading skeleton or spinner
- When `searchError` is set, show the error message
- When `searchResults` is empty array (search returned no results), show "No items match this search" message with suggestion to try different keywords

**Step 2.10 — Update stats bar to use real data.** In the stats bar section (the dark bg-slate-900 section currently lines 207–216):
- Replace the hardcoded `statProducts.toLocaleString()` (which was the animated counter) with `stats?.product_count?.toLocaleString() || "--"`
- Replace the hardcoded `852` channels with `stats?.channel_count?.toLocaleString() || "--"`
- Keep "0.3s" and "0 Birr" as static values (average search speed and buyer commission are not live yet)
- The stats bar must render gracefully when `stats` is still `null` (initial load) — show "--" for all values until fetch completes

**Step 2.11 — Generate category grid from TAXONOMY.** In the "What You Can Find Today" section (currently lines 274–289):
- Import `TAXONOMY` from `../constants/taxonomy`
- Replace the hardcoded `categories` array usage with `Object.keys(TAXONOMY).map(catName => ...)`
- Each category button should:
  - Use a deterministic emoji per category (map category names to emojis in a small lookup object, or use a generic icon)
  - Display the category name as the title
  - Display the subcategory list truncated as the description (e.g., first 3 subcategories joined by ", " with an ellipsis)
  - On click: set `searchQuery` to the category name and trigger `handleSearch` with that category (or navigate appropriately)
- Note: Real per-category item counts require an additional API endpoint or extending `/stats`. For TECH-16, category counts can be omitted or shown as static estimates. The acceptance criteria says "Category grid generated from taxonomy with real item counts" — to fulfill this, extend the `/stats` endpoint to also return `category_counts: { "CategoryName": <int>, ... }` by running a `GROUP BY category` query. Add this as part of Step 1.1.

**Step 2.12 — Wire popular search chips to real API.** The popular search chips (lines 148–152) currently set `searchQuery` which triggers the debounced search. They should continue to work as-is since setting `searchQuery` will now trigger the real API search via the updated `handleSearch` function. No changes needed here assuming `handleSearch` is connected to the form submit.

**Step 2.13 — Conditionally render based on `isTelegram` prop.** Add `isTelegram` and `onGetStarted` to the component's destructured props:
- `const LandingPage = ({ isTelegram = false, onGetStarted = null }) => {`
- When `isTelegram` is `true`:
  - **Hide** all "Open in Telegram" CTAs: the header button (line 101–104), the hero CTA button (line 196–199), the seller section CTA (line 304), the final CTA section button (line 405), and the footer Telegram Bot link (line 417)
  - **Show** a "Get Started" button at the very bottom of the page (after the FAQ section, before the footer) that calls `onGetStarted` when clicked
  - The "Get Started" button should be styled prominently: full-width on mobile, centered, with brand-600 background, white text, rounded-2xl, similar to the existing final CTA style
- When `isTelegram` is `false` (open web, the default):
  - All "Open in Telegram" CTAs render normally
  - No "Get Started" button

---

### Phase 3 — App.jsx: Onboarding Gate

**Step 3.1 — Add `useState` to React import.** Change the import line from:
```
import React from 'react';
```
to:
```
import React, { useState } from 'react';
```

**Step 3.2 — Add onboarding state logic.** Add state initialization inside the `App` component, BEFORE the existing `if (!isTelegramWebView())` check:
- `const [showOnboarding, setShowOnboarding] = useState(() => { ... })`
- The initializer function must:
  - Return `false` if NOT in Telegram WebView (open web always shows landing page via different path)
  - Return `true` if `localStorage.getItem('onboarding_seen')` is falsy (null, undefined, or empty string)
  - Return `false` if the flag is set to `'true'`
- Wrap the `localStorage` access in a try/catch to handle private browsing mode where localStorage is unavailable — if it throws, default to `true` (always show onboarding, per behavior doc degradation rule)

**Step 3.3 — Add `handleGetStarted` callback.** Create a function that:
- Sets `localStorage.setItem('onboarding_seen', 'true')` (wrapped in try/catch)
- Sets `setShowOnboarding(false)`

**Step 3.4 — Restructure the return logic.** Replace the current simple ternary with:

```
// Open web: always show landing page (no onboarding concept)
if (!isTelegramWebView()) {
  return <LandingPage />;
}

// Telegram: onboarding not yet seen → show landing page as onboarding
if (showOnboarding) {
  return <LandingPage isTelegram={true} onGetStarted={handleGetStarted} />;
}

// Telegram: already onboarded → show marketplace
return (
  <Router>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/item/:id" element={<ProductPage />} />
    </Routes>
  </Router>
);
```

**Step 3.5 — Key behavioral note.** When `handleGetStarted` fires, `setShowOnboarding(false)` triggers a React re-render. Since `showOnboarding` is now `false`, the third branch renders — the marketplace. This is a smooth in-app transition with no page reload, exactly as specified in the behavior doc Rule 2.2.

---

### Phase 4 — Design System Unification

**Step 4.1 — Update `index.css` root defaults.** In the `:root` block (lines 41–47):
- Change `background-color: #F8FAFC;` to `background-color: #FAF6F0;` (ethiopia-paper)
- Keep `color: #0F172A` (dark slate, already matches)
- The `--font-sans` variable already includes `"Inter", "Noto Sans Ethiopic", sans-serif` — this is correct and complete

**Step 4.2 — Update `NavBar.jsx` color scheme.** Make the following targeted changes:
- **Logo box** (line 28): Change `bg-blue-600` to `bg-slate-900`, and the icon color from `text-white` to `text-brand-500` — matching the landing page header logo treatment
- **Brand text** (line 29): Change `text-gray-900` to `text-slate-900`, and `text-blue-600` to `text-brand-600` on the "Gebeya" portion. Keep `tracking-tight` and `font-bold` (landing page uses `font-extrabold text-xl`, so change line 29 to match: `font-extrabold text-xl`)
- **Navbar background** (line 18): Change `bg-white` to `bg-ethiopia-paper/90 backdrop-blur-md` — matching the landing page header
- **Navbar border** (line 18): Change `border-gray-200` to `border-ethiopia-border` — matching the landing page header
- **Navbar height** (line 21): Change `h-16` to `h-20` — matching the landing page header height
- **Search bar background** (line 35, desktop): Change `bg-gray-100` to `bg-white` with a subtle border `border border-slate-200` to match the landing page search bar aesthetic
- **Search bar focus** (line 35): Change `focus:border-blue-500` to `focus:border-brand-500`
- **Camera button hover** (line 37, 53): Change `hover:text-blue-600` to `hover:text-brand-600`
- **Mobile search** (line 50): Same background and focus changes as desktop search
- **Menu button hover** (line 43): Change `hover:bg-gray-100` to `hover:bg-ethiopia-border/50`

**Step 4.3 — Update `ItemCard.jsx` aesthetic.** Make the following targeted changes to adopt the warm editorial design language:
- **Card container** (line 65): Change `bg-white rounded-xl` to `bg-white rounded-2xl`, and `border-gray-100` to `border-slate-200`, and `shadow-sm hover:shadow-md` to `shadow-soft hover:shadow-warm` (using the custom shadow tokens already defined in `index.css`)
- **Image area background** (line 70): Change `bg-gray-100` to `bg-ethiopia-paper`
- **Condition badge** (line 79): Change `bg-black/60` to `bg-slate-900/70`, matching the landing page category badge style
- **Price color** (line 99): Change `text-green-600` to `text-ethiopia-green` (already defined as `#047857`)
- **Category chip** (line 111): Change `bg-gray-100` to `bg-ethiopia-paper` with `border border-ethiopia-border/50`
- **Call button** (line 121): Change `hover:bg-green-50 text-gray-700 hover:text-green-600` to `hover:bg-ethiopia-green/5 text-gray-700 hover:text-ethiopia-green`, and `border-gray-200` to `border-slate-200`
- **Chat button** (line 133): Change `hover:bg-blue-50 text-gray-700 hover:text-blue-600` to `hover:bg-brand-50 text-gray-700 hover:text-brand-600`, and `border-gray-200` to `border-slate-200`
- **Match badge colors** — keep the purple/blue best-match badges as they serve a functional purpose distinct from the design system

**Step 4.4 — Home.jsx background.** In `Home.jsx` (line 33), change `bg-gray-50` to `bg-ethiopia-paper` to adopt the unified background.

---

## Testing Requirements

### Backend Tests

1. **Stats endpoint returns correct counts:**
   - Insert 5 items and 3 channels into test database
   - Hit `GET /items/stats`
   - Assert response is `{ "product_count": 5, "channel_count": 3 }`
   - If category_counts is included, verify group-by aggregates

2. **Stats endpoint handles empty database:**
   - Truncate items and channels tables
   - Hit `GET /items/stats`
   - Assert response is `{ "product_count": 0, "channel_count": 0 }`

### Frontend Tests

3. **LandingPage fetches and displays real stats:**
   - Mock `GET /items/stats` to return `{ product_count: 142890, channel_count: 852 }`
   - Render LandingPage
   - Assert the stats bar displays "142,890" and "852"
   - Assert "--" is displayed while loading

4. **LandingPage search calls real API:**
   - Mock `POST /search/` to return `{ items: [mockItem1, mockItem2], total: 2 }`
   - Type "iPhone" in search bar, submit form
   - Assert `ItemCard` components render with the mock items
   - Assert the "N MATCHES" badge shows "2 MATCHES"

5. **LandingPage shows "No results" for empty search:**
   - Mock `POST /search/` to return `{ items: [], total: 0 }`
   - Submit a search
   - Assert "No items match this search" message appears

6. **LandingPage handles stats endpoint failure gracefully:**
   - Mock `GET /items/stats` to return 500
   - Assert stats bar shows "--" for all values
   - Assert the rest of the page renders normally

7. **Onboarding gate — first visit:**
   - Clear localStorage
   - Mock `isTelegramWebView()` to return `true`
   - Render App
   - Assert LandingPage is shown with `isTelegram={true}`
   - Assert no "Open in Telegram" CTAs are visible
   - Assert "Get Started" button is present

8. **Onboarding gate — returning user:**
   - Set `localStorage.setItem('onboarding_seen', 'true')`
   - Mock `isTelegramWebView()` to return `true`
   - Render App
   - Assert marketplace (Home) is shown directly, no landing page

9. **Onboarding gate — Get Started transition:**
   - Clear localStorage, start in onboarding mode
   - Click "Get Started" button
   - Assert localStorage now has `onboarding_seen = 'true'`
   - Assert view transitions to marketplace without page reload

10. **Onboarding gate — open web:**
    - Mock `isTelegramWebView()` to return `false`
    - Render App (regardless of localStorage state)
    - Assert LandingPage is always shown
    - Assert "Open in Telegram" CTAs ARE visible

11. **Onboarding gate — localStorage unavailable:**
    - Mock `localStorage.getItem` to throw an error
    - Render App in Telegram mode
    - Assert onboarding always shows (graceful degradation)

12. **NavBar matches landing page header style:**
    - Render NavBar
    - Assert background uses `ethiopia-paper` color
    - Assert logo box uses `bg-slate-900` with `text-brand-500` icon
    - Assert height matches landing page header (h-20)
    - Assert brand text is `font-extrabold text-xl`

13. **LandingPage image search:**
    - Mock `POST /search/by-image` to return `[mockItem1, mockItem2]`
    - Upload an image file via the camera button
    - Assert `ItemCard` components render with results
    - Assert loading state shown during upload

14. **LandingPage image search failure:**
    - Mock `POST /search/by-image` to return 500
    - Upload an image
    - Assert error toast or message appears
    - Assert search bar remains functional afterward

15. **Category grid generated from TAXONOMY:**
    - Render LandingPage
    - Assert the category grid contains buttons for all keys in TAXONOMY
    - Click a category button
    - Assert either search is triggered or filter is applied

16. **No fake products remain:**
    - Grep `LandingPage.jsx` for `sampleProducts`, `categories` array (the hardcoded one), and inline HTML product cards
    - Assert all product rendering uses `<ItemCard>` component

---

## Notes for @build Agent

- **Do NOT** modify `useShop.js` — the landing page uses direct fetch calls, not the shop hook. The shop hook is for the marketplace feed and already works correctly.
- **Do NOT** modify `TAXONOMY` — it is the single source of truth for categories and is imported read-only.
- The `isTelegramWebView()` function in `App.jsx` already exists and works — do not modify it.
- When implementing the stats endpoint, be careful about route ordering in `items.py`: the new `GET /stats` route MUST be defined BEFORE the `GET /{item_id}` route to prevent FastAPI from interpreting "stats" as an item ID.
- If adding per-category counts to the stats endpoint, use `SELECT category, COUNT(*) FROM items GROUP BY category` returned as a dict keyed by category name.
- The landing page already has excellent responsive design and Tailwind classes — preserve all existing layout, spacing, and responsive breakpoints when replacing content.
- For the "Get Started" button inside Telegram onboarding, make it a `<button>` element (not an `<a>` link) that calls `onGetStarted()` on click.
- Font loading: the `@theme` block in `index.css` already declares the font stack. Ensure the Google Fonts `<link>` tags for Inter and Noto Sans Ethiopic are present in `index.html` (check if they need updating from Outfit).

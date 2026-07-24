# Combined Blueprint: TECH-10, TECH-11, TECH-12, TECH-13

**Goal:** Implement four frontend-only improvements — feed caching, search loading indicators, category chip truncation, and mobile navbar for the product detail page — spanning `useShop`, `ProductGrid`, `ItemCard`, `NavBar`, `Home`, and `ProductPage`.

---

## Files to Modify

| File | Tickets |
|------|---------|
| `frontend/src/hooks/useShop.js` | TECH-10 |
| `frontend/src/components/home/ProductGrid.jsx` | TECH-11 (receive + render search-loading) |
| `frontend/src/pages/Home.jsx` | TECH-10 (query param read), TECH-11 (pass new props) |
| `frontend/src/components/ItemCard.jsx` | TECH-12 (category chip CSS) |
| `frontend/src/components/home/NavBar.jsx` | TECH-13 (variant prop for back button) |
| `frontend/src/pages/ProductPage.jsx` | TECH-13 (replace header with NavBar) |

**No new files are created.**

---

## Strict Import Map

### Files with NO import changes (internal logic only)
- `frontend/src/hooks/useShop.js` — exports `useShop`, all existing named exports unchanged.
- `frontend/src/components/ItemCard.jsx` — exports default `ItemCard`, all existing imports unchanged.

### Files with ADDED imports or destructures

**`frontend/src/pages/Home.jsx`**
- **Add to existing `react-router-dom` import:** `useSearchParams`
  - Old: `import { useNavigate } from 'react-router-dom';`
  - New: `import { useNavigate, useSearchParams } from 'react-router-dom';`
- **Add destructure from `useShop()` hook return (already imported):**
  - `isSearchingText` (boolean)
  - `isSearchingVisual` (boolean)

**`frontend/src/components/home/ProductGrid.jsx`**
- **Add exported function signature props:**
  - `isSearchingText` (boolean, default `false`)
  - `isSearchingVisual` (boolean, default `false`)
  - No new import statements needed.

**`frontend/src/components/home/NavBar.jsx`**
- **Add to existing `lucide-react` import:** `ArrowLeft`
  - Old: `import { Search, ShoppingBag, Menu, X, Camera } from 'lucide-react';`
  - New: `import { Search, ShoppingBag, Menu, X, Camera, ArrowLeft } from 'lucide-react';`
- **Add exported function params:**
  - `variant` (string, default `"home"`)
  - `onBack` (function, optional)

**`frontend/src/pages/ProductPage.jsx`**
- **Add import:** `import NavBar from '../components/home/NavBar';`
- **Remove from existing `lucide-react` import:** `Share2`
- **Add local state via `useState`:**
  - `searchQuery` (string, default `""`)
  - `isMobileMenuOpen` (boolean, default `false`)
  - `activeCategory` (string, default `"All"`)

---

## Step-by-Step Execution

### TECH-10 — Feed Caching for Instant Back Navigation

**File:** `frontend/src/hooks/useShop.js`

1. **Create a module-level cache object** at the top of the file (outside the `useShop` function), after the imports but before the function definition. The cache holds:
   - `items` (array)
   - `offset` (number)
   - `hasMore` (boolean)
   - `seenItemIds` (array — serialized from the Set, since Sets don't survive JSON easily; reconstruct into a Set on read)

   Name this variable `_feedCache` and initialize it to `null`.

2. **Modify `useState` initializations** so every piece of feed data reads from the cache if available:
   - `items`: initialize to `_feedCache ? _feedCache.items : []`
   - `loading`: initialize to `!_feedCache` (if cache exists, no initial loading; if not, start in loading state)
   - `offset`: initialize to `_feedCache ? _feedCache.offset : 0`
   - `hasMore`: initialize to `_feedCache ? _feedCache.hasMore : true`
   - `seenItemIds`: initialize to `_feedCache ? new Set(_feedCache.seenItemIds) : new Set()`
   - Search/visual/searching states remain initialized to their current defaults (`""`, `null`, `false`) — they are transient and should always reset.

3. **Guard the initial `useEffect` that calls `fetchItems(0)`.** Before calling `fetchItems(0)`, check if `_feedCache` is not null. If the cache exists, skip the fetch call entirely. However, always reset the transient search states on mount:
   - Set `searchResults` to `null`
   - Set `visualResults` to `null`
   - Set `searchQuery` to `""`
   - Set `minPrice`, `maxPrice`, `filterCategory` to defaults
   
   This effect should run on every mount (empty dependency array stays), but the body conditionally skips the fetch.

4. **Inside `fetchItems`, after a successful `pageOffset === 0` fetch**, populate the module-level cache:
   - Assign `_feedCache` an object with `{ items: data, offset: 0, hasMore: data.length >= LIMIT, seenItemIds: [...newSeenIds] }`
   - This ensures the cache is always fresh when a full reload is triggered (e.g., via explicit refresh action).

5. **In the `handleReset` flow** (called from the Home page when the logo is clicked), the feed should re-fetch from scratch. Currently `handleReset` in `Home.jsx` calls `shop.setActiveCategory("All")`, `shop.setSearchQuery("")`, and `shop.clearVisualSearch()`. Add a guard: when the user explicitly triggers reset, `_feedCache` should be set to `null` so the next mount (or immediate) re-fetches. 
   - Option A: Export a `resetFeedCache` function from `useShop` that sets `_feedCache = null` and triggers `fetchItems(0)`. Call this from `handleReset` in `Home.jsx`.
   - **Choose Option A** — it's the cleanest.

6. **Export `resetFeed` from the hook's return object** along with existing values. Add `resetFeed` to the return statement.

**File:** `frontend/src/pages/Home.jsx` — minimal change for TECH-10:
7. In `handleReset`, call `shop.resetFeed()` before the other reset calls (which already exist). This clears the cache and forces a fresh fetch.

---

### TECH-11 — Search Loading Indicator

**File:** `frontend/src/pages/Home.jsx`

1. Destructure two additional values from the `useShop()` call:
   - `isSearchingText`
   - `isSearchingVisual`

2. Pass both as new props to the `<ProductGrid>` component:
   - `isSearchingText={shop.isSearchingText}`
   - `isSearchingVisual={shop.isSearchingVisual}`

**File:** `frontend/src/components/home/ProductGrid.jsx`

3. Add `isSearchingText` and `isSearchingVisual` to the destructured props in the function signature, each with a default value of `false`.

4. **Insert a new conditional block AFTER the existing `StatusLine` component definition but BEFORE the existing `if (loading) return <spinner>` block.** The new block should check:
   - If `isSearchingText` is true OR `isSearchingVisual` is true, render a skeleton grid.
   - The skeleton grid should consist of 8 placeholder cards arranged in the same responsive grid layout as the real cards (`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4`).
   - Each placeholder card should be a rounded rectangle with a pulsing/animating gray background (use Tailwind's `animate-pulse` with gray background classes, e.g., `bg-gray-200`). Include placeholders for: image area (square, full width), title line, price line, and a small tag chip.
   - The skeleton should include a text label above or below the grid reading "Searching..." (for text search) or "Analyzing image..." (for visual search), differentiated by which boolean is true.
   - This skeleton must render INSTEAD OF the items grid, not alongside it. Return it as a replacement for the entire `<main>` content area (the skeleton should still be wrapped in the same `<main className="max-w-6xl mx-auto px-4 py-8">` container for layout consistency).

5. The existing `loading` spinner (line 47) remains unchanged — it handles the initial feed load state. The new skeleton handles in-flight search state. These two loading states should NOT be confused: the initial spinner is a centered spinner, the search skeleton is a grid of placeholder cards.

6. The existing infinite scroll spinner (`isFetchingMore`, lines 71-74) remains unchanged — it handles pagination.

---

### TECH-12 — Category Name Truncation on Item Cards

**File:** `frontend/src/components/ItemCard.jsx`

1. Locate the category chip `<span>` on line 104:
   ```
   <span className="bg-gray-100 px-2 py-1 rounded line-clamp-1 max-w-[50%]">{item.category || "General"}</span>
   ```

2. Replace the Tailwind classes `line-clamp-1 max-w-[50%]` with `truncate max-w-[60%]`. The new class string should be:
   ```
   bg-gray-100 px-2 py-1 rounded truncate max-w-[60%]
   ```
   - `truncate` applies `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` which is the correct single-line truncation for inline elements in a flex row.
   - `max-w-[60%]` increases the available width from 50% to 60% of the parent flex container, allowing approximately 18-22 characters before ellipsis triggers (depends on font metrics).

3. No other changes needed. The full category name is already displayed uncropped on the product detail page (`ProductPage.jsx`), which satisfies acceptance criteria item 4.

---

### TECH-13 — Mobile Navigation Bar on Product Detail Page

**File:** `frontend/src/components/home/NavBar.jsx`

1. Add two new optional props to the function signature (next to the existing destructured props):
   - `variant = "home"` (string, default `"home"`)
   - `onBack` (function, default `undefined`)

2. Add `ArrowLeft` to the existing `lucide-react` import statement.

3. **Modify the logo/brand area** (currently lines 21-24, the `<div className="flex items-center gap-2 cursor-pointer" onClick={onReset}>...</div>`):
   - Wrap the logo in a conditional: if `variant === "product"`, render a back button instead.
   - The back button should be: `<button onClick={onBack} className="p-2 hover:bg-gray-100 rounded-full"><ArrowLeft size={24} className="text-gray-700" /></button>`
   - The back button should appear in the same left position the logo currently occupies.
   - For the mobile layout, this button should remain visible (the hamburger is on the right side).

4. The desktop search bar (lines 26-34) and the hamburger button (lines 36-38) remain unchanged regardless of variant.

5. The mobile search & category menu (lines 41-57) remains unchanged — it already provides the hamburger-category grid behavior.

6. The `onReset` prop is still called when the logo is clicked (home variant). For product variant, the back button uses `onBack` instead. If `onBack` is not provided, the button should still render but do nothing (defensive).

**File:** `frontend/src/pages/ProductPage.jsx`

7. **Remove the existing header** section (lines 99-103):
   ```
   <div className="bg-white border-b sticky top-0 z-20 px-4 py-3 flex items-center justify-between">
       <button onClick={() => navigate('/')} className="p-2 hover:bg-gray-100 rounded-full"><ArrowLeft size={24} className="text-gray-700" /></button>
       <div className="flex gap-2"><button className="p-2 hover:bg-gray-100 rounded-full text-gray-600"><Share2 size={20} /></button></div>
   </div>
   ```
   Remove the entire `<div>` block.

8. **Remove `Share2` from the `lucide-react` import** on line 3 (it was only used in the header being removed). The import should become:
   ```
   import { ArrowLeft, ShieldCheck, MessageCircle, Phone, Sparkles, AlertCircle, Star, User, Bell } from 'lucide-react';
   ```
   Note: `ArrowLeft` is still needed for the error-state "Back to Home" button on line 85.

9. **Add local state variables** at the top of the `ProductPage` component body (after the existing `useState` declarations for item, reviews, etc.):
   - `const [searchQuery, setSearchQuery] = useState("");`
   - `const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);`
   - `const [activeCategory, setActiveCategory] = useState("All");`

10. **Render the `<NavBar>` component** in place of the removed header. Place it BEFORE the `<div className="max-w-6xl mx-auto p-4 grid...">` container (the same position the old header occupied — the very first child of the root `<div className="min-h-screen bg-gray-50 font-sans pb-10">`).

11. Wire the NavBar props:
    - `variant="product"`
    - `onBack={() => navigate(-1)}` — navigates back in browser history (more robust than always going to `/` if the user arrived from a deep-linked URL). If `navigate(-1)` doesn't feel right for the acceptance criteria "Back arrow is preserved and functional", use `navigate('/')` instead.
    - `onReset={() => navigate('/')}` — clicking the back button (which serves as NavBar's clickable area in product variant) goes home and resets.
    - `searchQuery={searchQuery}`
    - `setSearchQuery={setSearchQuery}`
    - `onImageSearch={() => navigate('/')}` — image search isn't supported inline on the product page; navigating home is the fallback.
    - `isMobileMenuOpen={isMobileMenuOpen}`
    - `setIsMobileMenuOpen={setIsMobileMenuOpen}`
    - `activeCategory={activeCategory}`
    - `setActiveCategory={(cat) => { setActiveCategory(cat); setIsMobileMenuOpen(false); navigate('/'); }}` — selecting a category from the hamburger menu navigates to the home page. The home page will need to handle the category pre-selection (this is a separate concern; for now, navigating home is acceptable per the acceptance criteria).

12. **Add an `onKeyDown` handler to the search input for Enter key submission.** Since NavBar manages its own `<input>`, we need to pass an `onSearchSubmit` prop or handle it externally. The simplest approach: add a new optional prop `onSearchSubmit` to NavBar that fires when the user presses Enter in the search input.
    - **In NavBar.jsx:** Add `onSearchSubmit` to the destructured props. On the desktop search `<input>`, add an `onKeyDown` handler: if `e.key === 'Enter'` and `onSearchSubmit` exists, call `onSearchSubmit(searchQuery)`. On the mobile search `<input>`, do the same.
    - **In ProductPage.jsx:** Pass `onSearchSubmit={(query) => navigate(`/?q=${encodeURIComponent(query)}`)}` to NavBar.
    - **In Home.jsx:** Pass `onSearchSubmit` as a no-op or don't pass it (NavBar should handle `undefined` gracefully) — Home already uses debounced search via `setSearchQuery`, so Enter submission is not needed there.

13. **Handle the `?q=` query parameter on the Home page** so that when ProductPage navigates to `/?q=laptop`, the search is auto-triggered.
    - **File:** `frontend/src/pages/Home.jsx`
    - Add `useSearchParams` to the `react-router-dom` import.
    - At the top of the `Home` component: `const [searchParams] = useSearchParams();`
    - Add a `useEffect` (after the `useShop()` call) that reads `searchParams.get('q')`. If the param exists and is non-empty, call `shop.setSearchQuery(paramValue)`. This effect should run once on mount (`[]` dependency) and handle cleanup if needed.
    - The `useShop` hook's debounced search will then automatically fire the text search, satisfying "results pre-populated".

---

## Testing Requirements

### TECH-10
1. Navigate from Home to a product detail page, then press the browser back button. Verify the feed appears instantly without a loading spinner and without a network request for `/feed/foryou`.
2. Refresh the browser on the Home page. Verify the feed re-fetches (cache is null on fresh page load).
3. Click the logo/Index Gebeya brand on the Home page. Verify the feed re-fetches from scratch (resetFeed clears cache).
4. Perform a text search, then navigate to a product, then navigate back. Verify the search results are cleared (back to normal feed) and feed is restored from cache.
5. Scroll down several pages (infinite scroll), navigate to a product, navigate back. Verify the scroll position and seen items are preserved (offset and seenItemIds are cached).

### TECH-11
1. Type a search query slowly. Verify a skeleton grid appears after the search state flips to `isSearchingText=true` and disappears when results arrive.
2. Verify the skeleton grid is visually distinct from the initial loading spinner (centered circle) and the infinite scroll spinner (small circle at bottom).
3. Trigger an image search. Verify a skeleton or loading indicator appears (with "Analyzing image..." text) and disappears when results arrive.
4. Verify that when search returns zero results, the skeleton is replaced by the "No items found" message, not stuck in loading state.

### TECH-12
1. Create or mock an item with a long category name (e.g., "Home, Appliances & Furniture"). Verify the category chip on the ItemCard truncates with an ellipsis and does not overflow into adjacent elements.
2. Verify short category names (e.g., "Shoes") are displayed fully without truncation.
3. On the ProductPage (detail view), verify the full category name is displayed uncropped.

### TECH-13
1. On a mobile viewport (or responsive emulation), navigate to a product detail page. Verify the share button is gone from the header.
2. Verify a back button (`ArrowLeft`) is present and navigates to the previous page (or Home).
3. Verify a search bar is present in the header and typing + pressing Enter navigates to the Home page with the query in the URL.
4. Verify the hamburger menu button is present on mobile, and tapping it reveals the category grid.
5. Verify selecting a category from the hamburger menu navigates to the Home page.
6. Verify the header remains sticky during vertical scroll on the product page.

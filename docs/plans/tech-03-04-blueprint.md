# Implementation Blueprint: TECH-03 + TECH-04 (Infinite Scroll)

**Goal:** Enable infinite-scroll pagination for the For You feed, with server-side waterfall recommendation mixing based on scroll depth (TECH-03) and client-side IntersectionObserver-driven lazy loading with deduplication (TECH-04).

---

## Files to Modify

- `backend/api/routes/feed.py` — Add `offset` and `exclude` query parameters
- `backend/services/recommendation.py` — Add waterfall mix, wildcard feed, and exclude-id filtering
- `frontend/src/hooks/useShop.js` — Add offset state, paginated fetching, seen-ID tracking
- `frontend/src/components/home/ProductGrid.jsx` — Add sentinel div, IntersectionObserver, loading/end states
- `frontend/src/pages/Home.jsx` — Wire new props from `useShop` to `ProductGrid`

**No new files.**

---

## Step-by-Step Execution

### TECH-03 — Backend

#### Step 1: Add query parameters to the feed endpoint

**File:** `backend/api/routes/feed.py`

- Add `from fastapi import Query` to the import block (line 1).
- Modify the signature of `get_personalized_feed` (line 12) to add two new query parameters after `limit`:
  - `offset: int = 0` — the pagination offset for the waterfall calculation.
  - `exclude: Optional[str] = Query(None, description="Comma-separated item IDs to exclude from results")` — the frontend's seen-ID list.
- Pass both new parameters to the `build_feed()` call (line 27):
  - `offset=offset`
  - `exclude_ids_str=exclude`

#### Step 2: Extend build_feed signature and parse exclude IDs

**File:** `backend/services/recommendation.py`

- Modify the `build_feed` function signature (line 168) to accept two new keyword arguments:
  - `offset: int = 0`
  - `exclude_ids_str: Optional[str] = None`
- At the top of `build_feed`, parse `exclude_ids_str` into a `Set[int]`:
  - If the string is non-empty and not None, split on commas, strip whitespace, convert each token to `int`, and collect into a `set` called `exclude_ids`.
  - If the string is None or empty, use an empty set.
- Calculate `page = offset // limit + 1`.
- Pass `exclude_ids` into every sub-feed function call: `get_session_feed`, `get_discovery_feed`, `get_trending_items`, and the new `get_wildcard_feed`.

#### Step 3: Add exclude_ids parameter to all sub-feed functions

**File:** `backend/services/recommendation.py`

- **`get_trending_items`** (line 39): Add parameter `exclude_ids: set = set()`. In both the trending query and the fallback `get_recent_items` call, add `.where(Item.id.notin_(exclude_ids))` to the SQLAlchemy select statements. Note: use `Item.id.notin_` not `not_in` (the latter is deprecated in SQLAlchemy 2.0+ depending on version).
  - Specifically, the trending subquery (line 47) needs `where(~Item.id.in_(exclude_ids))` OR add the restriction after the `.limit(limit)` by filtering the result list. Simpler: filter out excluded IDs after fetching item objects.
  
  **Recommended approach for all sub-feed functions:** Rather than modifying every SQLAlchemy `.where()` clause, apply the exclude_ids filter at the return boundary of each function — iterate the returned list and remove any item whose `id` is in `exclude_ids`. This avoids touching SQLAlchemy-level filtering in multiple places.

- **`get_session_feed`** (line 77): Add parameter `exclude_ids: set = set()`. After building `results` (line 106), filter out any item where `item.id in exclude_ids`.

- **`get_discovery_feed`** (line 110): Add parameter `exclude_ids: set = set()`. After building `results` (line 166), filter out any item where `item.id in exclude_ids`. Also merge `exclude_ids` with the internal `seen_ids` set used in the sub-query `.where()` clause (line 158) so the database query itself avoids excluded IDs.

- **`get_recent_items`** (line 32): Add parameter `exclude_ids: set = set()`. Filter returned items to remove those in `exclude_ids`.

#### Step 4: Implement the waterfall mix table

**File:** `backend/services/recommendation.py`

Inside `build_feed`, after determining the user state (Cold Start / Explorer / Regular), implement the waterfall logic for the **Regular** state (`count > 10`). Replace the existing hardcoded 40/40/20 split (lines 209–216) with a page-based dispatch:

- Determine `page = offset // limit + 1`.
- Implement the following ratio table:

  | Page | Session % | Discovery % | Trending % | Wildcard % |
  |------|-----------|-------------|------------|------------|
  | 1    | 40%       | 40%         | 20%        | 0%         |
  | 2    | 25%       | 45%         | 30%        | 0%         |
  | 3    | 10%       | 50%         | 40%        | 0%         |
  | 4+   | 0%        | 40%         | 40%        | 20%        |

- Compute integer limits for each sub-feed based on the ratio for the current page.
- **Backfill rule:** After summing the sub-limits, if the total is less than `limit` due to rounding, add the remainder to the largest allocation (Discovery or Trending).

- **Explorer state** (`3 <= count <= 10`): Keep the existing 70% Session / 30% Trending ratio. Do NOT apply the waterfall table. Do NOT include wildcard. Pass the allocated limits and `exclude_ids` to the sub-feed calls.

- **Cold Start state** (`count < 3`): Keep existing behavior (100% Trending). Do NOT include wildcard. Pass `exclude_ids` to `get_trending_items`.

- **Anonymous state** (no user_id/session_id): Keep existing behavior (100% Trending). Pass `exclude_ids` to `get_trending_items`.

#### Step 5: Implement get_wildcard_feed

**File:** `backend/services/recommendation.py`

Add a new function `get_wildcard_feed` with the following signature and logic:

```python
def get_wildcard_feed(db: Session, interactions: List[UserInteraction], limit: int = 10, exclude_ids: set = set()) -> List[Item]:
```

- **Goal:** Pull trending items from the user's second-tier categories — categories they have interacted with but are NOT in their top 3 most-interacted categories.
- **Procedure:**
  1. Collect all interaction `item_id` values from `interactions` where `item_id` is not None.
  2. Fetch the corresponding `Item` records from the database. Build a frequency map of `category` → count.
  3. Sort categories by interaction count descending. The top 3 (or fewer if the user has interacted with fewer than 3 categories) are the "top categories".
  4. Identify "second-tier categories": any category that has at least one interaction but is NOT in the top 3.
  5. If no second-tier categories exist: fall back to `get_trending_items(db, limit, exclude_ids)` and return that result.
  6. If second-tier categories exist:
     - Distribute `limit` evenly across the second-tier categories (minimum 1 per category).
     - For each second-tier category, query for items in that category ordered by `created_at` descending, excluding `exclude_ids`, with the allocated limit.
     - Merge results from all second-tier categories.
  7. If the merged result has fewer than `limit` items, backfill with `get_trending_items` excluding already-included IDs.
  8. Log the second-tier categories used and the count returned.

#### Step 6: Preserve existing deduplication logic

The existing deduplication logic at lines 219–237 of `recommendation.py` (the `seen` set that removes duplicates and backfills from Trending) must remain intact and operate AFTER the waterfall mix assembly. Ensure the `exclude_ids` set is merged into the `seen` set at the start of the deduplication phase so that frontend-excluded IDs are also removed from the final output.

---

### TECH-04 — Frontend

#### Step 7: Add scroll state and paginated fetching to useShop

**File:** `frontend/src/hooks/useShop.js`

**New imports:** Add `useCallback` to the React import line:
```js
import { useState, useEffect, useCallback } from 'react';
```

**New state variables** (add after line 20, after existing state declarations):
- `const LIMIT = 20;` — constant for page size.
- `const [offset, setOffset] = useState(0);` — current page offset, used to track scroll depth.
- `const [hasMore, setHasMore] = useState(true);` — whether the backend may still have more items.
- `const [isFetchingMore, setIsFetchingMore] = useState(false);` — loading state for incremental fetches (distinct from initial `loading`).
- `const [seenItemIds, setSeenItemIds] = useState(new Set());` — tracks all item IDs the frontend has displayed, used to build the `exclude` query parameter.

**Modify `fetchItems`** (line 40):
- Change the function to accept an optional `pageOffset` parameter: `const fetchItems = useCallback(async (pageOffset = 0) => { ... }, []);`.
- Inside, build the URL as: `` `${API_BASE_URL}/feed/foryou?limit=${LIMIT}&offset=${pageOffset}` ``.
- If `seenItemIds.size > 0`, append `&exclude=${[...seenItemIds].join(',')}` to the URL.
- After receiving the JSON response (`data`):
  - If `pageOffset === 0`: replace items entirely with `setItems(data)`.
  - If `pageOffset > 0`: append to existing items with `setItems(prev => [...prev, ...data])`.
  - If `data.length < LIMIT`: set `setHasMore(false)`.
  - If `data.length === 0`: set `setHasMore(false)`.
  - Update `setSeenItemIds(prev => { const next = new Set(prev); data.forEach(item => next.add(item.id)); return next; })`.
  - For the `pageOffset === 0` case, set `setOffset(0)`.
- Remove the hardcoded `limit=50` in the URL. Change the limit to 20 (`LIMIT`).

**Add `fetchMore` function** (after `fetchItems`):
```js
const fetchMore = useCallback(async () => {
    if (!hasMore || isFetchingMore) return;
    const newOffset = offset + LIMIT;
    setIsFetchingMore(true);
    try {
        await fetchItems(newOffset);
        setOffset(newOffset);
    } finally {
        setIsFetchingMore(false);
    }
}, [hasMore, isFetchingMore, offset, fetchItems]);
```

**Update initial fetch useEffect** (line 23):
- Change from `fetchItems()` to `fetchItems(0)`.

**Update the return object** (line 136):
- Add to the returned object: `hasMore`, `isFetchingMore`, `fetchMore`, `LIMIT`.

**Display items logic** (lines 117–131): No changes needed. The `displayItems` derivation already filters from the `items` array, which will now accumulate across pages. Category/subcategory filters operate on the full accumulated pool, satisfying ACC requirement "Filtering by category/subcategory still works on the full accumulated item set."

#### Step 8: Add IntersectionObserver and sentinel to ProductGrid

**File:** `frontend/src/components/home/ProductGrid.jsx`

**New imports:** Add `useRef`, `useEffect` to the React import line:
```js
import React, { useRef, useEffect } from 'react';
```

**New props** (add to the destructured props on line 6):
- `hasMore` (boolean)
- `isFetchingMore` (boolean)
- `onLoadMore` (function, called when sentinel intersects)

**Add sentinel logic** (inside the component, before the `return` statement):
- Create a `useRef` for the sentinel element: `const sentinelRef = useRef(null);`.
- Add a `useEffect` that:
  - Checks if `!hasMore`. If true, disconnects any existing observer and returns early (no cleanup needed since observer is set up each time the effect runs).
  - Creates an `IntersectionObserver` with `rootMargin: '200px'` (detect within 200px of the bottom) and a callback that calls `onLoadMore()` when the sentinel `isIntersecting` and `!isFetchingMore`.
  - Observes `sentinelRef.current`.
  - Returns a cleanup function that disconnects the observer.
- Make the effect depend on `[hasMore, isFetchingMore, onLoadMore]`.

**Add UI elements** (inside the JSX return, after the closing `</div>` of the grid, but before the `</main>` closing tag on line 48):
- Add the sentinel div: `<div ref={sentinelRef} className="h-1" />` (1px invisible element at the bottom).
- After the sentinel, add a conditional block:
  - If `isFetchingMore`: show a loading spinner — a `<div>` with the same spinner classes as the existing loading state (line 26): a centered `<div>` with `animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600`.
  - If `!hasMore && items.length > 0`: show a message — a centered `<p>` with text "You've seen everything!" in muted gray styling (e.g., `text-center text-gray-400 py-6 text-sm`).

**Existing loading state** (line 26): This covers the initial load. Do not change it. The new `isFetchingMore` spinner only appears during incremental fetches AFTER the initial grid is already rendered.

#### Step 9: Wire new props in Home.jsx

**File:** `frontend/src/pages/Home.jsx`

- Add the following props to the `<ProductGrid>` component call (lines 42–53):
  - `hasMore={shop.hasMore}`
  - `isFetchingMore={shop.isFetchingMore}`
  - `onLoadMore={shop.fetchMore}`

---

## Strict Import Map

### Backend — No new imports needed; all types already available.

**`backend/api/routes/feed.py`** — Modified imports:
- Already imports: `APIRouter, Depends, Header, Request` from `fastapi`
- Add import: `Query` from `fastapi`
- Already imports: `get_db` from `database`, `ItemResponse` from `schemas`, `build_feed` from `services.recommendation`

**`backend/services/recommendation.py`** — No new imports needed:
- Already imports: `numpy, logging, json, Session, select, func, desc, or_, List, Dict, Any, datetime, timedelta, Item, UserInteraction, engine`

### Frontend

**`frontend/src/hooks/useShop.js`** — Modified imports:
- `useState, useEffect, useCallback` from `react` (add `useCallback`)
- `API_BASE_URL` from `../config` (unchanged)
- `TAXONOMY` from `../constants/taxonomy` (unchanged)
- `getAnalyticsHeaders` from `../utils/analytics` (unchanged)

**`frontend/src/components/home/ProductGrid.jsx`** — Modified imports:
- `React, useRef, useEffect` from `react` (add `useRef, useEffect`)
- `ItemCard` from `../ItemCard` (unchanged)
- `WifiOff, Camera, Search` from `lucide-react` (unchanged)
- `API_BASE_URL` from `../../config` (unchanged)

**`frontend/src/pages/Home.jsx`** — No import changes needed. Props passed are `hasMore`, `isFetchingMore`, `onLoadMore` which come from the existing `shop = useShop()` call.

---

## Testing Requirements

### Backend Tests (to be written by @build)

1. **Waterfall Page 1 Test:** Call `GET /feed/foryou?limit=20&offset=0` with a Regular user (providing `x-user-id` for a user with >10 interactions). Assert that the response contains items distributed approximately 40% session, 40% discovery, 20% trending. Assert no wildcard items are present.

2. **Waterfall Page 3 Test:** Call `GET /feed/foryou?limit=20&offset=40` (page 3). Assert the mix is approximately 10% session, 50% discovery, 40% trending.

3. **Waterfall Page 4+ Test:** Call `GET /feed/foryou?limit=20&offset=60` (page 4). Assert session items are absent (0%), wildcard items are present (~20%).

4. **Cold Start Excludes Wildcard:** Call with a user having < 3 interactions at any offset. Assert only trending items are returned. Assert no wildcard items.

5. **Explorer Excludes Wildcard:** Call with a user having 3–10 interactions at any offset. Assert 70/30 session/trending mix. Assert no wildcard items.

6. **Deduplication via exclude:** Make two sequential calls with the same user: `?limit=20&offset=0` then `?limit=20&offset=20&exclude=id1,id2,...` where the exclude IDs are the IDs from the first response. Assert no items from the first response appear in the second response.

7. **Empty Response on Exhaustion:** When the backend has returned all available items, the endpoint should return an empty array `[]`, not an error.

8. **Anonymous User Pagination:** Call with no `x-user-id` or `x-session-id` headers. Assert trending items are returned for any offset.

### Frontend Tests (to be written by @build)

1. **Initial Load:** Assert that on mount, `fetchItems(0)` is called with `limit=20&offset=0`. Assert items render in the grid.

2. **Scroll Triggers FetchMore:** Simulate IntersectionObserver intersection. Assert `fetchMore` is called. Assert the new offset is 20. Assert the URL includes `offset=20`.

3. **Append Behavior:** Assert that after `fetchMore`, new items are appended to the grid (existing items remain visible).

4. **Exclude Parameter:** Assert that after the first page, `fetchMore` sends an `exclude` query parameter containing the IDs from the first page.

5. **hasMore = false Stops Fetching:** After a response returns < 20 items, assert that `hasMore` becomes false and no further fetch requests are made on subsequent scrolls.

6. **"You've seen everything" Message:** When `hasMore` is false and items exist, assert the text "You've seen everything!" is rendered.

7. **Loading Spinner:** Assert that during `isFetchingMore`, a spinner is visible at the bottom of the grid.

8. **Filter Persistence on Accumulated Data:** Load 2 pages. Apply a category filter. Assert that items from BOTH pages that match the category are shown, and items from both pages that don't match are hidden.

9. **No Flash of Empty Grid:** During `isFetchingMore`, assert that already-loaded items remain visible (the grid does not disappear).

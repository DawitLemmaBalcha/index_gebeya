# TECH-05: Search Filters UI — Implementation Blueprint

**Date:** 2026-07-23
**Parent Ticket:** NB-25
**Goal:** Add price range inputs and a category dropdown that appear below the search bar when a search query is active, and pass their values to the backend search endpoint.

---

## Files to Modify/Create

| Action   | File Path                                       |
|----------|-------------------------------------------------|
| CREATE   | `frontend/src/components/SearchFilters.jsx`     |
| MODIFY   | `frontend/src/hooks/useShop.js`                 |
| MODIFY   | `frontend/src/pages/Home.jsx`                   |

No backend files are touched. The `/search/` POST endpoint already accepts `min_price`, `max_price`, and `category` in the request body.

---

## Strict Import Map

### New File: `frontend/src/components/SearchFilters.jsx`

**Imports needed by this component:**
- `React` from `react`
- `TAXONOMY` from `../constants/taxonomy`
- `Filter` (icon) from `lucide-react` — used for the badge/pill indicator

**Props contract (all passed from `Home.jsx`):**

| Prop Name          | Type                  | Source in `useShop`      |
|--------------------|-----------------------|---------------------------|
| `searchQuery`      | `string`              | `shop.searchQuery`        |
| `minPrice`         | `string` (controlled) | `shop.minPrice`           |
| `setMinPrice`      | `(val: string) => void`| `shop.setMinPrice`       |
| `maxPrice`         | `string` (controlled) | `shop.maxPrice`           |
| `setMaxPrice`      | `(val: string) => void`| `shop.setMaxPrice`       |
| `filterCategory`   | `string`              | `shop.filterCategory`     |
| `setFilterCategory`| `(val: string) => void`| `shop.setFilterCategory` |

**Exports:**
- Default export: `SearchFilters` (functional component)

---

### Modified File: `frontend/src/hooks/useShop.js`

**New state variables to add (alongside existing `searchQuery`, `searchResults`, etc.):**

| State Variable   | Initial Value | Setter               |
|------------------|---------------|----------------------|
| `minPrice`       | `""`          | `setMinPrice`        |
| `maxPrice`       | `""`          | `setMaxPrice`        |
| `filterCategory` | `"All"`       | `setFilterCategory`  |

**Modified function: `handleTextSearch`**

- Change its parameter from `(query)` to `(query, filters)` where `filters` is an object with shape `{ minPrice, maxPrice, filterCategory }`.
- The POST body sent to `${API_BASE_URL}/search/` must include:
  - `query` (existing, unchanged)
  - `limit` (existing, keep at `50`)
  - `min_price` — only included if `filters.minPrice` is non-empty. Convert to a number. Omit entirely if empty string.
  - `max_price` — only included if `filters.maxPrice` is non-empty. Convert to a number. Omit entirely if empty string.
  - `category` — only included if `filters.filterCategory` is not `"All"` and not empty. Omit entirely if `"All"`.

**Modified effect: debounced search trigger**

- Extend the existing `useEffect` that watches `searchQuery` (the 600ms debounce on line 36) so its dependency array also includes `minPrice`, `maxPrice`, and `filterCategory`.
- When the debounce fires, call `handleTextSearch(searchQuery, { minPrice, maxPrice, filterCategory })`.
- When `searchQuery` is empty, also reset `setMinPrice("")`, `setMaxPrice("")`, `setFilterCategory("All")` to clear the filter state.

**Modified return object (add these properties):**

The hook's return statement must include: `minPrice`, `setMinPrice`, `maxPrice`, `setMaxPrice`, `filterCategory`, `setFilterCategory`.

---

### Modified File: `frontend/src/pages/Home.jsx`

**New import:**
- `import SearchFilters from '../components/SearchFilters';`

**New JSX insertion point:**

In the return block, after the `<NavBar ... />` closing tag and before the `<CategoryBar ... />` conditional, insert a conditional block:

- When `shop.searchQuery` is non-empty and `!shop.visualResults` is true (i.e., not in visual search mode), render:
  ```jsx
  <SearchFilters
    searchQuery={shop.searchQuery}
    minPrice={shop.minPrice}
    setMinPrice={shop.setMinPrice}
    maxPrice={shop.maxPrice}
    setMaxPrice={shop.setMaxPrice}
    filterCategory={shop.filterCategory}
    setFilterCategory={shop.setFilterCategory}
  />
  ```
- The `CategoryBar` conditional on line 33 already checks `!shop.searchQuery`, so the filters naturally replace the category bar when searching. No conflict — the existing guard is sufficient.

---

## Step-by-Step Execution

### Step 1: Add filter state to `useShop.js`

Add three new `useState` declarations after the existing search-related state lines:
- `minPrice` initialized to `""`
- `maxPrice` initialized to `""`
- `filterCategory` initialized to `"All"`

---

### Step 2: Modify `handleTextSearch` signature and body

Change the function signature to accept a second parameter: `filters` (an object with `minPrice`, `maxPrice`, `filterCategory` keys).

Inside the function, construct the request body as an object literal:
- Always include `query` (from the first argument) and `limit: 50`.
- Conditionally add `min_price: Number(filters.minPrice)` only when `filters.minPrice` is non-empty.
- Conditionally add `max_price: Number(filters.maxPrice)` only when `filters.maxPrice` is non-empty.
- Conditionally add `category: filters.filterCategory` only when `filters.filterCategory` is not `"All"`.

The rest of the function (headers, fetch, error handling) remains unchanged.

---

### Step 3: Update the debounce effect to react to filter changes

Modify the `useEffect` that fires on `searchQuery` changes (the one with the 600ms `setTimeout`):

- Add `minPrice`, `maxPrice`, `filterCategory` to the dependency array.
- Change the `handleTextSearch(searchQuery)` call inside the timeout to pass the filter object: `handleTextSearch(searchQuery, { minPrice, maxPrice, filterCategory })`.
- In the `else` branch (when `searchQuery` is empty), add lines to reset filter state: `setMinPrice("")`, `setMaxPrice("")`, `setFilterCategory("All")` before calling `setSearchResults(null)`.

**Note:** Because the same 600ms timer is restarted on any filter change, both typing and filter adjustments share the same debounce cycle. This satisfies the requirement: "Changing any filter value immediately re-triggers the search with the updated filters (debounced alongside the search query debounce at 600ms)."

---

### Step 4: Export new state from the hook

In the return object of `useShop`, add the six new entries:
- `minPrice`, `setMinPrice`, `maxPrice`, `setMaxPrice`, `filterCategory`, `setFilterCategory`

---

### Step 5: Create the `SearchFilters` component

Create the file `frontend/src/components/SearchFilters.jsx`.

**Component structure:**
- Accept all seven props listed in the Import Map section above.
- Guard: if `searchQuery` is empty (trimmed), return `null` (render nothing).
- Compute `activeFilterCount`:
  - 1 if `minPrice !== ""`
  - 1 if `maxPrice !== ""`
  - 1 if `filterCategory !== "All"` and `filterCategory !== ""`
  - Sum these to get the total.

**Layout (top to bottom):**

1. **Container:** A `div` with appropriate padding and styling that sits below the search bar. Use a horizontal layout (`flex`) with `flex-wrap` for responsiveness.

2. **Min Price input:**
   - Type `number`, placeholder `"Min Price (ETB)"`, `min="0"`, `step="1"`.
   - Value controlled by `minPrice`, onChange calls `setMinPrice`.
   - Styled as a compact input (small text, rounded-xl, bg-gray-100).

3. **Max Price input:**
   - Type `number`, placeholder `"Max Price (ETB)"`, `min="0"`, `step="1"`.
   - Value controlled by `maxPrice`, onChange calls `setMaxPrice`.
   - Same compact input styling.

4. **Category dropdown (`<select>`):**
   - Populate options from `Object.keys(TAXONOMY)`. Use "All" as the first/default option.
   - Value controlled by `filterCategory`, onChange calls `setFilterCategory`.
   - Styled to match the input aesthetic.

5. **Active filter badge:**
   - When `activeFilterCount > 0`, display a pill/badge (e.g., a `span` with rounded-full background) showing the count: `"N filter(s) active"`.
   - Use the `Filter` icon from lucide-react for visual polish.
   - When `activeFilterCount === 0`, render nothing for the badge.

**Styling guidance:**
- Use Tailwind CSS classes consistent with the existing design system (gray-100 backgrounds, rounded-xl, border-transparent focus styles).
- The container should sit naturally below the NavBar search input — apply `max-w-6xl mx-auto px-4` to match Home's layout width.

---

### Step 6: Integrate `SearchFilters` into `Home.jsx`

- Import the new component.
- Insert the conditional rendering block between the `</NavBar>` and the CategoryBar conditional, using the guard `shop.searchQuery && !shop.visualResults`.
- Pass all required props from `shop.*` as listed in the Import Map.

---

## Testing Requirements

The `@build` agent must implement and verify the following test cases:

### Behavioural Tests (Manual / Interactive)

1. **Filters appear on search:** Type any text into the search bar. Confirm that price inputs and the category dropdown appear below the NavBar within the debounce window (600ms after typing stops).

2. **Filters hide on clear:** Clear the search bar (click X or delete all text). Confirm the filter inputs disappear and the CategoryBar reappears.

3. **Price filter filters results:** Search for a common term (e.g., "phone"). Set Max Price to 5000. Confirm that all returned items have prices at or below 5000 ETB.

4. **Category filter filters results:** Search for a term, then select a category (e.g., "Electronics") from the dropdown. Confirm returned items belong to that category.

5. **Combined filters:** Set both a price range and a category. Confirm results respect both constraints simultaneously.

6. **Active filter badge:** Set one or more filters. Confirm the badge shows the correct count ("2 filter(s) active"). Clear each filter and confirm the count decrements to 0 and the badge disappears.

7. **Filter change re-triggers search:** Perform a text search. Without re-typing the query, change the Max Price value. Confirm the search re-executes with the new filter after the 600ms debounce.

8. **Reset on clear:** Search with filters active, then clear the search bar. Re-type a query. Confirm filters are reset to defaults (empty prices, "All" category) — not stale from the previous search.

### Edge Cases

9. **Non-numeric price input:** Enter letters or negative numbers in the price fields. Confirm the HTML `type="number"` attribute prevents this at the browser level (no need to send invalid data to the API).

10. **Very large price:** Set Max Price to a very large number (e.g., 999999999). Confirm the backend handles it gracefully (returns all items within that bound).

11. **Min > Max price:** Set Min Price higher than Max Price. Confirm the backend returns empty results or the frontend displays "No items found" — either is acceptable; the system must not crash.

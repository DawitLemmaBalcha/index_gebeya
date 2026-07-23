# Technical Backlog

> Generated from `docs/behaviors/pending-behaviors.md` gap tickets.
> Each TECH ticket maps to one or more NB behavioral tickets.

---

## TECH-05 — Search Filters UI on Frontend

**Parent:** NB-25
**Priority:** HIGH
**Affected Files:**
- `frontend/src/hooks/useShop.js` — modify `handleTextSearch` to pass filters
- `frontend/src/pages/SearchBar.jsx` or new `SearchFilters.jsx` component — add filter UI
- No backend changes needed (schema already supports filters)

**Description:**
The backend search schema already accepts `min_price`, `max_price`, and `category`. The frontend sends none of them. Add filter inputs that appear after a search query is entered and pass their values to the backend.

**Technical Work:**
1. Create a `SearchFilters` component with:
   - Two number inputs: Min Price and Max Price (in ETB), positioned below the search bar
   - A category `<select>` dropdown populated from `TAXONOMY` constants, defaulting to "All"
2. Filters appear **only when** `searchQuery` is non-empty. They hide when the search bar is cleared.
3. Show a small pill/badge count of active filters (e.g., "2 filters active").
4. Modify `handleTextSearch` to include `min_price`, `max_price`, and `category` in the POST body alongside `query` and `limit`.
5. Changing any filter value immediately re-triggers the search with the updated filters (debounced alongside the search query debounce at 600ms).

**Acceptance Criteria:**
- [ ] Typing a search query reveals filter inputs below the search bar
- [ ] Setting a max price and searching returns only items under that price
- [ ] Selecting a category from the dropdown filters results to that category
- [ ] Clearing the search bar hides the filter inputs
- [ ] A visual indicator shows how many filters are currently active
- [ ] Changing a filter re-triggers the search without requiring the buyer to re-type the query

# Browse Seam Blueprint — Server-Side Category Browse with Boost Pin Layer (Option B)

**Date:** 2026-08-05
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture

## 0. Goal

Make category browse a real server-side catalog seam (`GET /items/browse`) with the boost pin layer applied on top — replacing the client-side feed-filter fiction — without touching the relevance engine, the For You feed, or the search route's observable behavior.

## 1. Architecture Context

**The friction.** Today the "Mobile Phones" category view is the For You feed loaded into the browser and client-filtered by `item.category === activeCategory` (`frontend/src/hooks/useShop.js` lines 232–246 — the category filter is at line 237; note: **not** Home.jsx, which is 84 lines and contains no filter logic). The boost pin layer lives only in `backend/api/routes/search.py` (lines 33–70). Result: a boosted item (e.g., item 952) never pins in category browse, because category browse never executes a server-side query. Rule 3.1 is unimplemented for its first surface.

**The two-seam argument.** Search is a relevance engine; browse is a catalog query. The proof is in `backend/services/search.py` lines 173–177: `perform_hybrid_search` **vectorizes an empty string** when there is no query text and computes cosine similarity against every item (`_execute_search_sql`, lines 34–96). Forcing browse through `POST /search/` means computing meaningless similarity over the whole catalog to produce what is really a `WHERE category = X ORDER BY created_at DESC` query. The original blueprint assumption (monetization-blueprint.md D7, line 22: "Category browse is not a separate endpoint… category browse == POST /search/ with body.category") was wrong about the frontend — category chips were wired to the feed, not to search. **This blueprint supersedes D7.** The immutable monetization blueprint is NOT edited; the superseding note lives here.

**Dependency categories.** `catalog.py` is a **deep, Local-substitutable module** — zero app imports beyond models/SQLAlchemy; it can be unit-tested in isolation and replaced by any adapter. `compose_pinned_page` is **in-process, pure-ish composition over the Session** — the pin query is deterministic clock-derived (Rule 4.2), the dedup is set arithmetic (Rule 3.4), no relevance math (Rule 3.5). The frontend hook change is a **presentation adapter** — it swaps the URL source per view mode while reusing the existing items state, infinite-scroll machinery, and the ItemCard badge. The seam between the two backend seams is the response shape (`{items, total}`), deliberately mirrored from search so the frontend renders identically. **Leverage:** one shared composition function, two surfaces. **Locality:** all pin semantics stay in `boost.py`; all catalog navigation lives in `catalog.py`; routes stay thin.

## 2. The New Interfaces

### 2.1 `catalog.browse_category` — the catalog seam (deep module)

New file `backend/services/catalog.py`, module docstring states: *catalog navigation, not relevance*. Single public function:

- Signature: `browse_category(db: Session, category: str, limit: int = 20, offset: int = 0) -> tuple[list[Item], int]`
- Behavior: plain select of `Item` where `category == :category AND status == 'active' AND is_active == True`, `ORDER BY created_at DESC` (recency — identical to the feed's fallback ordering in `services/recommendation.py:32–43`, which the browse view currently mimics by accident), `OFFSET offset LIMIT limit`. A second aggregate query returns the total count of matching rows.
- Returns `(items, total_count)`. NO vectorization, NO similarity, NO threshold, NO score fields.
- Invariant: never calls `get_pinned_boosted_items`, never imports boost — the pin layer is applied by the caller.

### 2.2 `boost.compose_pinned_page` — the shared pin composition (deepening move)

New function in `backend/services/boost.py`, placed immediately after `get_pinned_boosted_items` (line 267) in the existing "Placement (the pinned layer)" section.

- Signature: `compose_pinned_page(db: Session, *, category: str | None = None, query_text: str | None = None, items: list, now: datetime | None = None, pinned: list | None = None) -> tuple[list, set[int]]`
- Behavior, in order:
  1. If `pinned` is not provided, compute `pinned = get_pinned_boosted_items(db, category=category, query_text=query_text, now=now)`; else use the caller-supplied list unchanged (single-query contract, see Deviation 1).
  2. `pinned_ids = {i.id for i in pinned}`.
  3. For every element of `items`: set its `is_boosted` attribute to `True` iff its `id` is in `pinned_ids` (the organic marking, Rule 3.3 — **preserved byte-for-byte from search.py:64–65**).
  4. Return `(pinned + [i for i in items if i.id not in pinned_ids], pinned_ids)` — pinned first in rotation order, organic minus pinned (Rule 3.4 no duplicates on a page).
- Duck-typing contract: `items` and `pinned` are lists of objects exposing `.id` and a writable `is_boosted` attribute. In the search caller the organic items are `ItemResponse` instances (already serialized by `perform_hybrid_search`); in the browse caller they are ORM `Item` instances. `Item` has **no `is_boosted` column** (models.py:183–233) — dynamic attribute assignment works on the declarative model (no `__slots__`), and `ItemResponse.model_validate` reads dynamic attributes via `getattr` under `from_attributes=True` (proven in production: `read_item` and the search route already `model_validate` ORM Items whose `report_count`/`is_boosted`/`total_score` attributes are absent or dynamic, falling back to field defaults).
- Does NOT touch `total` — the caller owns count semantics (search: organic count; browse: category count).
- `query_text` matching semantics are inherited unchanged from `get_pinned_boosted_items` (case-insensitive substring on title, lines 254–259).

**Deviation 1 (additive, documented):** the locked signature had no `pinned` parameter. It is required: `TestSearchPinLayer` (backend/tests/test_payments_flow.py:312) asserts the search route passes `exclude_item_ids == [boosted_item.id]` into `perform_hybrid_search`, which forces the pinned query to run BEFORE the search. A single `compose_pinned_page` call cannot precede the search it consumes, so the search route keeps its pinned query (search.py:33–40, unchanged) and hands the result to compose via `pinned=`. Behavior identical, one query per request, tests green.

**Deviation 2 (additive, documented):** the locked signature typed `items: list[Item]`; the search caller's organic list is `List[ItemResponse]` (perform_hybrid_search returns serialized models). The parameter is duck-typed (documented above) rather than strict — both callers pass their native types; no conversion, no behavior change.

### 2.3 The route — `GET /items/browse`

In `backend/api/routes/items.py`, registered **immediately after `get_recent_items` (line 85) and BEFORE `read_item`'s `@router.get("/{item_id}")` (line 88)** — FastAPI matches in registration order, and `/items/browse` would otherwise be swallowed by the int path parameter (`item_id="browse"` → 422).

- Query params: `category` (required — see Deviation 3), `limit: int = 20`, `offset: int = 0` (mirrors the search conventions: `SearchQuery.limit` default 20, **no max cap anywhere** in the search route or service; browse mirrors that — no cap).
- **Deviation 3:** a required FastAPI query param yields a 422, not 400. The locked contract says "category required else 400". Implement as an `Optional` query param defaulting to `None`; raise `HTTPException(400, detail="category is required")` when missing/blank/whitespace-only (strip before use).
- Auth: **unauthenticated** — matches the read-route convention (`/items/recent` items.py:75, `/items/{item_id}` items.py:88 have no `authenticate`; analytics flow via optional `x-user-id`/`x-session-id` headers, exactly as `read_item` lines 99–110).
- Body: call `catalog.browse_category(db, category, limit, offset)`; then `page_items, _ = compose_pinned_page(db, category=category, items=organic, now=None)` (omitting `now` lets compose use its internal clock — rotation stays deterministic per page load, Rule 4.2); serialize every element of `page_items` with `ItemResponse.model_validate` (uniform ORM input here; `is_boosted` rides the dynamic attribute); return `BrowseResponse(items=[...], total=total_count)`.
- Analytics: append the read-route convention — optional header parse + `background_tasks.add_task(AnalyticsService.log_interaction, interaction_type="browse", meta_data={"category": category, "result_count": total})` (mirrors `read_item`).
- Response schema: new `BrowseResponse(BaseModel)` with `items: List[ItemResponse]` and `total: int` (schemas.py, next to `SearchResponse` line 144). **Deviation 4:** search's `SearchResponse` also carries `execution_time_ms`; browse omits it — the frontend consumes only `data.items` (useShop.js:198) and the locked shape is `{items, total}`.
- `total` semantics (locked, documented): total = count of matching organic category rows. The pinned block is prepended to **every** offset page (the pin is a reserved top position, not part of organic pagination) — identical to the search surface's semantics; Rule 3.4 is a per-page invariant, not a cross-page one.

### 2.4 Frontend — mode-aware source switching (adapter)

In `frontend/src/hooks/useShop.js`, architect's option (a): a separate explicit browse fetcher, feed path untouched.

- New callback `fetchBrowseCategory(category, pageOffset = 0)`: builds `${API_BASE_URL}/items/browse?category=${encodeURIComponent(category)}&limit=${LIMIT}&offset=${pageOffset}`, attaches `getAnalyticsHeaders()` (like fetchItems line 106), unwraps `data.items` (browse returns `{items, total}`, unlike the bare feed array), sets/appends `items` state exactly like `fetchItems` (lines 117–122), derives `hasMore` from `data.items.length < LIMIT` (mirroring lines 124–129). **Must NOT** touch `seenItemIds` (the feed's `exclude` set and its `_feedCache`, lines 131–147) — browse results must never pollute feed state or the module-level cache.
- New effect on `activeCategory` (with a ref tracking the previous value): (a) transition into a real category → reset scroll state (offset 0, hasMore true) and `fetchBrowseCategory(category, 0)`; (b) transition out of a real category into neutral → `fetchItems(0)` (fresh feed — items state currently holds browse data); (c) neutral → neutral (including `handleTextSearch`'s `setActiveCategory("All")` at line 169, and image search line 206) → no-op. This preserves the existing "typing a query switches to text search" UX with no redundant feed refetch.
- Neutral-category normalization (Deviation 5): `CategoryChips` sets lowercase `'all'` (CategoryChips.jsx:9,27) while `CategoryBar` sets `"All"` (CategoryBar.jsx:16) and the existing filter only recognizes `"All"` — a pre-existing latent bug (mobile "All" chip → empty grid) that browse mode would amplify. Treat both `"All"` and `"all"` as neutral in the new effect, in `fetchMore`, in the retry helper, and in the `displayItems` neutral check (line 237 gains the lowercase alternative).
- `displayItems` filter (lines 232–246): in browse mode (real category), the **category** clause is skipped (server already filtered) while the **subcategory** clause and the "Other" branch (lines 239–243) are preserved verbatim (subcategory filtering stays client-side, per the locked design). Feed mode logic unchanged.
- `fetchMore` (line 156): becomes mode-aware — browse mode calls `fetchBrowseCategory(activeCategory, offset + LIMIT)`, else `fetchItems` (unchanged).
- New returned `retry` helper: mode-aware re-fetch of the current surface (used by ProductGrid's `onRetry`, Home.jsx line 65 — in browse mode, retry must not fire the feed fetcher).
- Return object gains `fetchBrowseCategory` and `retry`; `items`, `hasMore`, `isFetchingMore`, `LIMIT`, `fetchMore` semantics otherwise unchanged. `resetFeed` unchanged.
- Home.jsx: no filter removal needed (there is none); only `onRetry={shop.retry}` (line 65). ItemCard renders the ⚡ Boosted badge automatically from `item.is_boosted` (ItemCard.jsx:96–99) — browse results flow through the same rendering, no change.

**Invariants (locked):** no relevance math in browse; no duplicates on a page (Rule 3.4); feed untouched and boost-free (Rule 3.2 — `services/recommendation.py` has no import edge to boost, verified via graphify: `get_pinned_boosted_items` callers are only `search_items()` and tests); search-route observable behavior unchanged (existing pin tests green); `is_boosted` never persisted.

## 3. Strict Import Map (additive-only)

| File | Action | Exact imports added |
|---|---|---|
| `backend/services/catalog.py` | **NEW** | `from sqlalchemy import select, func` · `from sqlalchemy.orm import Session` · `from models import Item` (no other app imports — deep module) |
| `backend/services/boost.py` | modify | none — `compose_pinned_page` uses in-module `get_pinned_boosted_items`, existing `select`/`Item`/`datetime, timezone` imports |
| `backend/schemas.py` | modify | none — `BrowseResponse` uses existing `BaseModel`, `List`, `ItemResponse` |
| `backend/api/routes/items.py` | modify | extend boost import block (lines 14–20) with `compose_pinned_page` · add `from services import catalog as catalog_service` · extend schemas import (lines 9–10) with `BrowseResponse` · `BackgroundTasks`/`Request` already imported (line 3) |
| `backend/api/routes/search.py` | modify | extend line 14 import: `from services.boost import get_pinned_boosted_items, compose_pinned_page` (no new modules; existing `datetime, timezone` line 6 stays — route keeps its `now` computation) |
| `frontend/src/hooks/useShop.js` | modify | none — uses existing `useState/useEffect/useCallback/useRef`, `API_BASE_URL`, `getAnalyticsHeaders`, `LIMIT` |
| `frontend/src/pages/Home.jsx` | modify | none — swap `onRetry` prop only |
| `frontend/src/__tests__/BrowseSeam.test.jsx` | **NEW** | vitest, `@testing-library/react` (renderHook/act/screen), mock `../config` (pattern: ProductGrid.test.jsx:18–20) |
| `backend/tests/test_catalog.py` | **NEW** | pytest, `models` (User/Channel/Item/Boost), `services.catalog.browse_category` — helper pattern copied from test_boost.py `_make_seller_item` (lines 42–70) |
| `backend/tests/test_items_browse.py` | **NEW** | pytest, FastAPI TestClient pattern from test_boost.py `TestBoostQuoteRoute._client` (lines 597–610), `api.routes.items`, `get_db` override |
| `backend/tests/test_boost.py` | modify | add `compose_pinned_page` to the existing `services.boost` import block (line 26–35) |
| `docs/behaviors/monetization.md` | modify | text-only note under Rule 3.1 (lines 52–54) |

**Removals:** only the inline composition body of `search_items` (search.py lines 62–70: organic marking loop, pinned serialization, forced flag, list concat) — replaced by the compose call + a serialization loop. Nothing else is removed anywhere.

## 4. Execution Steps

1. **Create `backend/services/catalog.py`.** Implement `browse_category` exactly per §2.1. Docstring: catalog navigation seam; explicitly notes it never vectorizes and never imports boost.
2. **Add `compose_pinned_page` to `backend/services/boost.py`** per §2.2 (place after `get_pinned_boosted_items`; update the module docstring's placement-section wording and the `get_pinned_boosted_items` docstring so the "ONE application point" language moves to the composition function).
3. **Refactor `backend/api/routes/search.py`.** Keep lines 33–40 (pinned query + `pinned_ids`, `"All"`→None normalization) and the `perform_hybrid_search` call with `exclude_item_ids=list(pinned_ids)` (line 51) untouched. Replace lines 62–70 with: one `compose_pinned_page` call passing the normalized category, `query.query or None`, the organic `items_list`, `now`, and `pinned=`; then serialize ONLY the pinned ORM elements (`[i for i in page_items if i.id in pinned_ids]`) via `ItemResponse.model_validate`, force `is_boosted = True` on those responses (byte-for-byte with today's lines 67–69), keep the organic elements as-is, and concatenate pinned-first. `total` stays the organic count; `SearchResponse` construction unchanged.
4. **Add `BrowseResponse` to `backend/schemas.py`** next to `SearchResponse` (§2.3).
5. **Add `GET /items/browse` to `backend/api/routes/items.py`** — inserted between `get_recent_items` and `read_item` (ordering is a hard requirement). Implement per §2.3 (400 on blank category, unauthenticated, compose with `now=None`, `model_validate` on all page elements, analytics background task, `BrowseResponse`).
6. **Frontend `useShop.js`**: add `fetchBrowseCategory`, the previous-value ref + category effect, mode-aware `fetchMore`, `retry`, neutral normalization (incl. the lowercase `"all"` in the displayItems neutral check), and the browse-mode displayItems branch that skips the category clause while preserving the subcategory/"Other" clauses. Export the new functions. Do not touch `seenItemIds`, `_feedCache`, or `handleTextSearch`/`handleImageSearch`.
7. **Frontend `Home.jsx`**: point `onRetry` at the mode-aware retry.
8. **Backend tests**: create `test_catalog.py` and `test_items_browse.py`; extend `test_boost.py` (§5). Run them (step 11) — `TestSearchPinLayer` must pass unmodified.
9. **Frontend tests**: create `BrowseSeam.test.jsx` (§5); run vitest.
10. **Docs ride-along**: add to `docs/behaviors/monetization.md` under Rule 3.1 (lines 52–54) a short note: *"Implemented 2026-08-05: category browse is a real server-side surface — `GET /items/browse` applies the pin layer via `boost.compose_pinned_page` (Rule 3.1's first true implementation; supersedes monetization-blueprint D7)."* Do NOT touch `docs/plans/monetization-blueprint.md` (immutable).
11. **Verification** (section 6), then `graphify update .` (repo convention after code changes).
12. **Atomic commit** (single commit, only after @qa approval per AGENTS.md §3, no intermediate commits): message `feat: category browse seam — server-side browse with boost pin layer (NB-43 Rule 3.1 true implementation)`.

## 5. Testing Requirements

**`backend/tests/test_catalog.py` (new)** — `browse_category` with `db_session`:
- returns only active items of the category (sold and soft-deleted (`is_active=False`) siblings excluded);
- recency order (`created_at` desc — create items with explicit timestamps to make ordering deterministic);
- total count correct (includes sold/soft-deleted? No — count matches the filtered set);
- pagination: limit/offset slices correctly, offset beyond end returns empty with correct total.

**`backend/tests/test_boost.py` (extend)** — new `TestComposePinnedPage` class:
- pinned first in rotation order + every pinned element `is_boosted is True`; organic elements marked `False`;
- no duplicates: an item present in both `pinned` and `items` appears exactly once (Rule 3.4);
- no-pinned case: input list returned unchanged, every element `is_boosted is False`;
- category-filtered pins (pinned block contains only same-category boosted items); query-text pins (case-insensitive);
- `pinned=` parameter: when pre-supplied, the same clock yields the same pinned order and no extra query behavior (assert identical output to the internal-query path for a fixed `now`);
- pre-existing `get_pinned_boosted_items` tests and `TestSearchPinLayer` (test_payments_flow.py:264–312) remain green UNMODIFIED — the refactor must not alter search behavior (`items[0]` pinned+flagged, `items[1]` organic unflagged, count==1, `total==1`, `exclude_item_ids` captured).

**`backend/tests/test_items_browse.py` (new)** — route via TestClient:
- 400 when `category` missing/blank; 200 with shape exactly `{items: [...], total: n}`;
- boosted item first with `is_boosted: true`; organic items `is_boosted: false`;
- sold/soft-deleted items absent from browse;
- limit/offset respected; unauthenticated request succeeds (read-route convention).

**`frontend/src/__tests__/BrowseSeam.test.jsx` (new)** — mock `fetch`:
- browse mode (set activeCategory to a real category) calls `/items/browse?category=<encoded>&limit=20&offset=0` and renders returned items;
- neutral `"All"` mode calls `/feed/foryou?limit=20&offset=0` (feed untouched);
- switching category refetches browse with the new category; subcategory switching does not refetch;
- ItemCard renders the ⚡ Boosted badge from a browse response item with `is_boosted: true`.

## 6. Verification

- `pytest backend/tests/test_catalog.py backend/tests/test_items_browse.py backend/tests/test_boost.py backend/tests/test_payments_flow.py -q` — then full `pytest backend/tests -q` (network-dependent tests self-skip per existing convention).
- `cd frontend && npm run test` (vitest run) and `npm run build` (vite build).
- Grep: `backend/api/routes/search.py` contains a `compose_pinned_page(` call and no longer contains the inline `is_boosted` marking loop; `backend/api/routes/items.py` contains `"/browse"`; `grep -rn "get_pinned_boosted_items\|compose_pinned_page" backend/services/recommendation.py` → empty (Rule 3.2).
- `graphify explain services_boost_get_pinned_boosted_items` → callers remain `search_items()` + tests (no recommendation edge).
- Smoke: `curl -s 'http://localhost:8000/items/browse?category=Mobile%20Phones&limit=3'` returns `{items, total}` with the boosted item first; `curl -s -o /dev/null -w '%{http_code}' 'http://localhost:8000/items/browse'` → 400.

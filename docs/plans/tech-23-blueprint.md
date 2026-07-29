# TECH-23 Blueprint — Inventory Management

**Date:** 2026-07-29
**Parent:** NB-42
**Priority:** HIGH
**Depends On:** TECH-22 (Item.status column, SoldReport model — must be merged first)

---

## Goal

Add a full inventory management interface to the Stores tab: a channel inventory modal with Products/Settings tabs, a product grid with infinite scroll, an editable product panel with status controls, backend CRUD endpoints for channel items, an edit-history audit log, and a tab registry pattern for forward extensibility.

---

## Files to Create

1. `frontend/src/components/ChannelInventory.jsx` — full-page inventory modal shell with tab registry
2. `frontend/src/components/InventoryProductsTab.jsx` — product grid with search, sort, filters, infinite scroll
3. `frontend/src/components/InventorySettingsTab.jsx` — settings tab (pause/resume, remove, stats)
4. `frontend/src/components/ProductEditPanel.jsx` — edit panel for a single product
5. `frontend/src/components/StatusBadge.jsx` — reusable status badge component
6. `frontend/src/hooks/useChannelInventory.js` — hook for fetching, filtering, paginating channel items

## Files to Modify

7. `backend/models.py` — add `ItemEdit` model
8. `backend/schemas.py` — add `ItemUpdateRequest`, `ItemEditResponse`, `ChannelItemsResponse`
9. `backend/api/routes/channels.py` — add `GET /channels/{id}/items` endpoint
10. `backend/api/routes/items.py` — add `PATCH /items/{id}`, `POST /items/{id}/sold`, `POST /items/{id}/relist` endpoints
11. `backend/main.py` — add `ItemEdit` import; add schema migration for `item_edits` table; optionally extract migrations to a dedicated module
12. `frontend/src/pages/StoresPage.jsx` — add inventory state management; integrate ChannelInventory; add onClick to channel cards

---

## Strict Import Map

### New Models (`backend/models.py`) — no new imports needed

The existing imports from sqlalchemy (`Column`, `Integer`, `String`, `Float`, `DateTime`, `ForeignKey`, `Text`, `Boolean`, relationship, func, mapped_column, Base) already cover everything the `ItemEdit` model needs. No new imports required.

### New Schemas (`backend/schemas.py`) — no new imports needed

`BaseModel`, `Optional`, `Dict`, `Any`, `List`, `datetime` are already imported. No new imports required.

### Backend Routes — imports to add

**`backend/api/routes/channels.py` — new imports:**
- `ItemResponse` already importable from `schemas` (line 16: `from schemas import ChannelResponse, ChannelUpsert, OwnerChannelResponse` and line 17: `from schemas import ChannelInfoResponse, ChannelPauseRequest, ChannelActionResponse` — extend line 17 to also import `ChannelItemsResponse`)

**`backend/api/routes/items.py` — new imports:**
- `from schemas import ItemUpdateRequest, ItemEditResponse` (add to line 8)
- `from models import ItemEdit, User` (add to line 7)
- `from services.alerting import process_new_item` (add new import)
- `from pydantic import BaseModel` for request body models
- `import json` for specs comparison
- `Optional` from `typing` (already imported)

**`backend/main.py` — new imports:**
- `from models import ItemEdit` (add to line 8 import block after `from models import Channel, User, Item` — note: main.py imports from models happen indirectly through the route files; the schema migration DDL is added inline, so no direct model import needed for the migration. However, the `Item` model is already importable.)

### Frontend New Files — import sources

All new components import from:
- `react` (useState, useEffect, useCallback, useRef, useMemo)
- `lucide-react` (various icons: ArrowLeft, Search, Filter, SlidersHorizontal, Edit3, DollarSign, CheckCircle, AlertTriangle, RefreshCw, X, Loader2, Package, Settings, Tag, Grid, List, ChevronDown, ChevronUp, Plus, Trash2)
- `../config` → `API_BASE_URL`
- `../constants/taxonomy` → `TAXONOMY`
- `../utils/analytics` → `getAnalyticsHeaders`
- `../components/ItemCard` → `ItemCard` (reuse existing card layout)
- `../components/StatusBadge` → `StatusBadge` (new sibling component)

### Modified StoresPage.jsx — new imports

- `ChannelInventory` from `../components/ChannelInventory` (new)
- The existing imports (`React`, `useState`, `useEffect`, lucide icons, `useOwnerChannels`) all stay unchanged.

---

## Step-by-Step Execution

### STEP 1 — Add `ItemEdit` model (`backend/models.py`)

After the `Item` class definition (after line 207, before the `ItemImage` class), add a new model class:

- Class name: `ItemEdit`
- Table name: `"item_edits"`
- Columns:
  - `id` — Integer, primary_key=True, index=True
  - `item_id` — Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
  - `field` — String, nullable=False (the column name that was changed, e.g., "title", "price", "specs")
  - `old_value` — Text, nullable=True (stringified JSON for specs; null if field was previously null)
  - `new_value` — Text, nullable=True (stringified JSON for specs; null if cleared)
  - `edited_by` — Integer, ForeignKey("users.id"), nullable=False (the user who made the edit)
  - `timestamp` — DateTime(timezone=True), server_default=func.now()
- Relationships:
  - `item = relationship("Item")`
  - `editor = relationship("User")`

### STEP 2 — Add schema migration for `item_edits` table (`backend/main.py`)

In the Phase 3 migrations block (around line 100, after the TECH-21b migration), add a new try/except block:

- Use `conn.execute(text(...))` to run `CREATE TABLE IF NOT EXISTS item_edits` with all columns matching the model definition
- Follow the exact same `with engine.begin() as conn:` and `logger.info(...)` pattern used by lines 69–100
- The DDL should include: `id SERIAL PRIMARY KEY`, `item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE`, `field VARCHAR NOT NULL`, `old_value TEXT`, `new_value TEXT`, `edited_by INTEGER NOT NULL REFERENCES users(id)`, `timestamp TIMESTAMPTZ DEFAULT NOW()`

### STEP 3 — Add new Pydantic schemas (`backend/schemas.py`)

After the existing `ItemResponse` class (around line 99), add:

**`ItemUpdateRequest`:**
- Fields: `title` (Optional[str]), `description` (Optional[str]), `price` (Optional[float]), `category` (Optional[str]), `subcategory` (Optional[str]), `specs` (Optional[Dict[str, Any]])
- All fields default to `None` (unset = no change). Use `exclude_unset` in the endpoint to distinguish between "not provided" and "explicitly set to null"

**`ItemEditResponse`:**
- Fields: `id` (int), `item_id` (int), `field` (str), `old_value` (Optional[str]), `new_value` (Optional[str]), `edited_by` (int), `timestamp` (datetime)
- Config class with `from_attributes = True`

**`ChannelItemsResponse`:**
- This is a wrapper type. Since FastAPI can return `List[ItemResponse]` directly, define this as the return type is simply `List[ItemResponse]`. Add a query parameter model instead:
- **`ChannelItemsParams`** — not a Pydantic model; these are FastAPI query parameters declared directly in the endpoint signature: `limit: int = 20`, `offset: int = 0`, `status: Optional[str] = None`, `sort: Optional[str] = "recent"`, `search: Optional[str] = None`

**`ItemStatusResponse`:**
- Fields: `status` (str), `message` (str)

### STEP 4 — Add `GET /channels/{id}/items` endpoint (`backend/api/routes/channels.py`)

Add a new route at the bottom of the file (after the `remove_channel` function, before the file-end):

- Decorator: `@router.get("/{channel_id}/items", response_model=List[ItemResponse])`
- Function signature: `def get_channel_items(channel_id: int, init_data: str, limit: int = 20, offset: int = 0, status: Optional[str] = None, sort: Optional[str] = "recent", search: Optional[str] = None, db: Session = Depends(get_db))`

**Authentication:**
- Call `_auth_user_from_init_data(init_data, db)` to get the user
- Verify ownership: query Channel by id where `registered_by == user.telegram_id`. If not found, raise 404 "Channel not found".

**Base query:**
- Build a `select(Item).where(Item.channel_id == channel_id, Item.is_active == True)` query

**Filtering (status):**
- If `status == "sold"`: add `.where(Item.status == "sold")` 
- If `status == "reported"`: add a join to SoldReport, filter where sold reports exist for this item (need to think: the status on Item would be `reported_sold`, so just `.where(Item.status == "reported_sold")`)
- If `status == "active"`: add `.where(Item.status == "active")`
- If `status` is None or "all": no status filter

**Search filtering:**
- If `search` is provided: add `.where(Item.title.ilike(f"%{search}%"))` 
- NOTE: The ilike approach is case-insensitive. The `pg_trgm` extension is already enabled, but a simple ilike is sufficient for channel-scoped product counts.

**Sorting:**
- If `sort == "price_asc"`: `.order_by(Item.price.asc())`
- If `sort == "price_desc"`: `.order_by(Item.price.desc())`
- Default (`"recent"` or anything else): `.order_by(Item.created_at.desc())`

**Pagination:**
- Apply `.offset(offset).limit(limit)` to the statement
- Execute with `db.scalars(stmt).all()`

**Return:**
- Return the list of items directly. FastAPI will serialize through `ItemResponse`.

### STEP 5 — Add `PATCH /items/{id}` endpoint (`backend/api/routes/items.py`)

Add a new route after the existing `get_related_items` function:

- Decorator: `@router.patch("/{item_id}", response_model=ItemResponse)`
- Function signature: `def update_item(item_id: int, body: ItemUpdateRequest, init_data: str, db: Session = Depends(get_db))`

**Authentication & ownership verification:**
- The endpoint needs to verify the editing user owns the channel the item belongs to.
- Import `User`, `Channel`, `_auth_user_from_init_data` from channels module — OR define a reusable auth helper.
- Better approach: extract `_auth_user_from_init_data` to a shared auth module. Since that would be a refactor beyond TECH-23 scope, instead duplicate the auth pattern inline:
  - Import `json`, `parse_qs` from `urllib.parse` (already available)
  - Parse `init_data` to extract `tg_id`
  - Lookup `User` by `telegram_id == tg_id`
  - If not found, auto-create User
  - Get the item: `item = db.get(Item, item_id)`; raise 404 if missing
  - Verify ownership: `item.channel.registered_by != user.telegram_id` → raise 403

**Edit history logging helper:**
- Define a nested function `_log_edit(field_name, old_val, new_val)`:
  - Convert `old_val` and `new_val` to strings (use `json.dumps` for dicts like specs)
  - Compare: if `old_val == new_val`, return (skip no-op edits)
  - Create an `ItemEdit` record with `item_id`, `field`, `old_value`, `new_value`, `edited_by`
  - Add to session (but do NOT commit yet — the outer function commits)

**Apply updates (use `exclude_unset` to detect which fields were sent):**
- `update_data = body.model_dump(exclude_unset=True)`
- For each field in `update_data`:
  - If `"title"` in update_data: log edit, then `item.title = body.title`
  - If `"description"` in update_data: log edit, then `item.description = body.description`
  - If `"price"` in update_data: log edit, check if price actually changed (compare float values with tolerance), then `item.price = body.price`
  - If `"category"` in update_data: log edit, then `item.category = body.category`
  - If `"subcategory"` in update_data: log edit, then `item.subcategory = body.subcategory`
  - If `"specs"` in update_data: log edit (serialize both to JSON strings for comparison), then `item.specs = json.dumps(body.specs)` (the Item.specs field stores JSON as string)

**Commit:**
- `db.commit()`
- `db.refresh(item)`

**Re-trigger alert matching (Rule 3.3):**
- If `"price"` in update_data or `"specs"` in update_data: call `process_new_item(db, item.id)` after commit
- This re-runs the alert matching pipeline so buyers with matching alerts get notified

**Return:**
- Return the updated `item`

### STEP 6 — Add `POST /items/{id}/sold` endpoint (`backend/api/routes/items.py`)

- Decorator: `@router.post("/{item_id}/sold", response_model=ItemStatusResponse)`
- Verify ownership (same pattern as STEP 4/5: parse init_data, find user, verify `item.channel.registered_by == user.telegram_id`)
- Set `item.status = "sold"` (Rule 3.5: immediate, authoritative, no confirmation needed — but reversible)
- `db.commit()`
- Return `{"status": "sold", "message": "Item marked as sold"}`

### STEP 7 — Add `POST /items/{id}/relist` endpoint (`backend/api/routes/items.py`)

- Decorator: `@router.post("/{item_id}/relist", response_model=ItemStatusResponse)`
- Verify ownership (same pattern)
- Set `item.status = "active"`
- Delete all `SoldReport` records for this item: `db.execute(select(SoldReport).where(SoldReport.item_id == item_id))` → iterate and delete each
- `db.commit()`
- Return `{"status": "active", "message": "Item re-listed"}`

### STEP 8 — Add `POST /items/{id}/clear-reports` endpoint (`backend/api/routes/items.py`)

- Decorator: `@router.post("/{item_id}/clear-reports", response_model=ItemStatusResponse)`
- Verify ownership (same pattern)
- Delete all `SoldReport` records for this item without changing status (Rule 3.5: for pre-threshold cleanup)
- `db.commit()`
- Return `{"status": item.status, "message": "Reports cleared"}`

### STEP 9 — Create `StatusBadge` component (`frontend/src/components/StatusBadge.jsx`)

A small, reusable component that renders a status badge based on the item's status:

- Props: `status` (string), `indexingPaused` (boolean, optional)
- Logic:
  - No badge if `status === "active"` and `indexingPaused !== true`
  - If `indexingPaused === true`: show amber "Paused" badge regardless of status
  - If `status === "sold"`: show green "Sold" badge
  - If `status === "reported_sold"`: show red "⚠️ Reported" badge
- Styling: consistent with the PAUSED/ACTIVE badges in StoresPage.jsx (rounded-full, small text, colored background)

### STEP 10 — Create `useChannelInventory` hook (`frontend/src/hooks/useChannelInventory.js`)

A new hook following the `useOwnerChannels.js` / `useShop.js` pattern:

**State:**
- `items` (array, default [])
- `loading` (boolean, default false)
- `error` (string or null)
- `hasMore` (boolean, default true)
- `offset` (number, default 0)
- `totalCount` (number, default 0)
- `statusFilter` (string, default "all")
- `sortBy` (string, default "recent")
- `searchQuery` (string, default "")

**Functions:**
- `fetchItems(channelId, reset = false)` — performs `GET /channels/{channelId}/items?limit=20&offset=X&status=Y&sort=Z&search=W` via fetch, with `init_data` and analytics headers (same `getInitData()` pattern from useOwnerChannels). If `reset`: clears items, sets offset to 0. Otherwise appends.
- `fetchMore(channelId)` — calls fetchItems with current offset + 20, increments offset
- `setStatusFilter(val)` — updates filter, resets items
- `setSortBy(val)` — updates sort, resets items
- `setSearchQuery(val)` — updates search, debounced reset (use 400ms setTimeout like useShop)
- `markSold(channelId, itemId)` — `POST /items/{itemId}/sold` with init_data, then refresh
- `relist(channelId, itemId)` — `POST /items/{itemId}/relist` with init_data, then refresh
- `clearReports(channelId, itemId)` — `POST /items/{itemId}/clear-reports` with init_data, then refresh
- `updateItem(channelId, itemId, updateData)` — `PATCH /items/{itemId}` with JSON body, init_data in query param, then refresh

**Return value:** An object with all state and functions.

**Fetch URL pattern:** `${API_BASE_URL}/channels/${channelId}/items?init_data=${encodeURIComponent(initData)}&limit=20&offset=${offset}&status=${statusFilter}&sort=${sortBy}` + optional `&search=${encodeURIComponent(searchQuery)}`

### STEP 11 — Create `InventoryProductsTab` component (`frontend/src/components/InventoryProductsTab.jsx`)

This component renders the Products tab content within the ChannelInventory modal:

**Props:** `channelId`, `onSelectProduct` (callback), `inventory` (the useChannelInventory hook return value)

**Layout (top to bottom):**
1. **Search bar** — text input with Search icon, bound to `inventory.searchQuery`/`inventory.setSearchQuery`
2. **Filter & Sort row** — horizontal row with:
   - Status filter dropdown/chips: "All", "Active", "Sold", "Reported"
   - Sort dropdown: "Most Recent", "Price: Low-High", "Price: High-Low"
3. **Product grid** — scrollable area with CSS grid (2 columns on mobile, matching the explore feed layout):
   - Each product card reuses the `ItemCard` component (same layout as explore feed)
   - Overlaid with `StatusBadge` component
   - onClick → calls `onSelectProduct(item)`
4. **Infinite scroll** — use an IntersectionObserver on a sentinel div at the bottom. When visible and `hasMore` and not loading, call `inventory.fetchMore(channelId)`.
5. **Empty state** — "No products found" message with icon when items.length === 0 and not loading
6. **Loading state** — centered Loader2 spinner
7. **Error state** — error message with retry button

### STEP 12 — Create `InventorySettingsTab` component (`frontend/src/components/InventorySettingsTab.jsx`)

Renders the Settings tab content — mirrors the current channel card actions:

**Props:** `channel` (object with id, username, title, indexing_paused, product_count), `onClose` (callback)

**Content:**
1. **Channel info header** — @username, title, trust_score, review_count
2. **Product count stat** — large number display
3. **Pause/Resume toggle** — calls the parent's `togglePause` function
4. **Remove channel button** — red, opens confirmation dialog, calls `removeChannel` + `onClose`
5. **Stats section (placeholders for TECH-23)** — Views and Clicks show "—" as they need analytics work; product_count is live

**Reuse**: This component can import `useOwnerChannels` directly, or better: receive `togglePause` and `removeChannel` as props from the parent.

### STEP 13 — Create `ProductEditPanel` component (`frontend/src/components/ProductEditPanel.jsx`)

A full-screen panel (slides in from right or replaces the product grid) for editing a single product:

**Props:** `item` (full item object), `channel` (the channel object), `onBack` (callback), `onSave` (callback receiving updated item), `onMarkSold` (callback), `onRelist` (callback), `onClearReports` (callback)

**Layout (top to bottom):**
1. **Header bar** — Back arrow button (calls `onBack`), "Edit Product" title, "View Original Post" link button (external link to Telegram post using channel username + message_id)
2. **Thumbnail image** — displays `item.image_path` or `item.images[0]` as a large preview
3. **Editable fields (scrollable area):**
   - **Title** — text input, pre-filled with `item.title`, maxLength 200
   - **Description** — textarea, pre-filled with `item.description`, 4 rows
   - **Price** — number input in ETB, pre-filled with `item.price`, step 1
   - **Category** — dropdown/select populated from `Object.keys(TAXONOMY)`, pre-selected to `item.category`
   - **Subcategory** — cascading dropdown: options are `TAXONOMY[selectedCategory]` or `[]`, pre-selected to `item.subcategory`. Reset when category changes.
   - **Specs** — dynamic key-value editor:
     - Parse `item.specs`: if it's a string, try `JSON.parse`; fallback to empty object
     - Render each spec as a row: key input + value input + remove button
     - "Add Spec" button to add a new empty row
4. **Status controls section** (below fields, separated by a divider):
   - **Mark as Sold** button — calls `onMarkSold(item.id)`, full-width, green accent
   - **Re-list** button — calls `onRelist(item.id)`, full-width, blue accent (only shown if item.status !== "active")
   - **Clear Reports** button — calls `onClearReports(item.id)`, full-width, amber accent (only shown if item.status === "reported_sold")
5. **Save button** — fixed at bottom, full-width, brand color. Calls `onSave` with the collected form data.

**Form state management:**
- Use `useState` for each field, initialized from `item`
- On save: compile all fields into an updateData object, call `onSave(updateData)`
- Only include fields that changed from original (compare with initial item values) — this is a client-side optimization; the backend also handles no-op detection

**Specs editor details:**
- State: `specsEntries` — array of `{ key: string, value: string }` objects
- On mount: convert `item.specs` (string or object) to array
- On add: push `{ key: '', value: '' }`
- On remove: filter out by index
- On save: convert back to `{ [key]: value }` object, filter out empty keys

### STEP 14 — Create `ChannelInventory` modal component (`frontend/src/components/ChannelInventory.jsx`)

The full-page modal with a tab registry pattern. This is the integration point that wires everything together.

**Props:** `channel` (object), `onClose` (callback)

**State:**
- `activeTab` — string, default `"products"`
- `selectedProduct` — item object or null (null = showing grid, non-null = showing edit panel)

**Tab registry (Rule 5.1 — extensibility pattern):**
Define a constant configuration array at module level:
```
const TAB_REGISTRY = [
  { id: 'products', label: 'Products', icon: Package },
  { id: 'settings', label: 'Settings', icon: Settings },
];
```
To add a new tab in the future (e.g., "Analytics"), simply push a new entry to this array. The modal iterates over TAB_REGISTRY to render tab buttons and conditionally renders the active tab's content.

**Hook usage:**
- Import and call `useChannelInventory()` hook at the top
- Also use `useOwnerChannels` for the settings tab (togglePause, removeChannel)

**Layout:**
1. **Header bar:**
   - Back arrow button (calls `onClose`)
   - Channel title: `@channel.username`
   - Status badge (PAUSED/ACTIVE)
2. **Tab bar:**
   - Render buttons from `TAB_REGISTRY`
   - Active tab has underline indicator (matching BottomNav style)
   - Badge on Products tab showing product_count
3. **Tab content area (fills remaining height):**
   - If `selectedProduct` is set: render `ProductEditPanel` instead of tab content (the edit panel replaces the entire tab area)
   - If `activeTab === "products"`: render `InventoryProductsTab`, passing `channelId={channel.id}`, `onSelectProduct={setSelectedProduct}`, `inventory={inventoryHook}`
   - If `activeTab === "settings"`: render `InventorySettingsTab`, passing `channel={channel}`, `onClose={onClose}`, `togglePause`, `removeChannel`

**Data flow for ProductEditPanel callbacks:**
- `onBack`: set selectedProduct to null (return to grid)
- `onSave(updateData)`: call `inventoryHook.updateItem(channel.id, selectedProduct.id, updateData)`, show success toast via a local state message, set selectedProduct to null
- `onMarkSold(itemId)`: call `inventoryHook.markSold(channel.id, itemId)`, show toast
- `onRelist(itemId)`: call `inventoryHook.relist(channel.id, itemId)`, show toast
- `onClearReports(itemId)`: call `inventoryHook.clearReports(channel.id, itemId)`, show toast

**Toast notification:**
- Local state: `toast` — `{ message: string, type: 'success' | 'error' } | null`
- Displayed as a fixed-position banner at the top of the modal, auto-dismiss after 3 seconds

**Loading/error states:**
- The `inventoryHook` exposes `loading` and `error` — pass these down to `InventoryProductsTab`
- Settings tab has its own loading/error from `useOwnerChannels`

### STEP 15 — Integrate into `StoresPage.jsx`

Modify the existing Stores page to open the ChannelInventory modal when a channel card is tapped:

**New state:**
- `selectedChannel` — null or a channel object (tracks which channel's inventory is open)

**Changes to channel cards:**
- Add `onClick={() => setSelectedChannel(channel)}` to each channel card div (the one at line 100 with `className="bg-white rounded-2xl p-4 shadow-sm..."`)
- Add `cursor-pointer` and `hover:shadow-md` to the card's className for click affordance

**Conditional rendering:**
- At the top of the return (before the channel list view), add:
  - If `selectedChannel` is not null: render `<ChannelInventory channel={selectedChannel} onClose={() => setSelectedChannel(null)} />`
  - The channel list view is hidden when a channel is selected

**Important:** The `StoresPage` component needs to import `ChannelInventory` from `../components/ChannelInventory`.

### STEP 16 — Wire `ItemEdit` into SQLAdmin (optional polish)

In `backend/admin.py`, if an `ItemEditAdmin` view class exists or can be added, register it so the admin dashboard can browse edit history. This step is optional for TECH-23 MVP.

---

## Testing Requirements

### Backend Tests

1. **GET /channels/{id}/items — pagination**
   - Create a channel owned by test user_1, create 25 items for that channel
   - Fetch with limit=10, offset=0 → expect 10 items
   - Fetch with limit=10, offset=10 → expect 10 items
   - Fetch with limit=10, offset=20 → expect 5 items
   
2. **GET /channels/{id}/items — status filter**
   - Create items with status "active", "sold", "reported_sold"
   - Fetch with `?status=sold` → expect only sold items
   - Fetch with `?status=all` → expect all items

3. **GET /channels/{id}/items — ownership check**
   - Attempt to fetch items for a channel not owned by the authenticated user → expect 404

4. **PATCH /items/{id} — successful edit**
   - Update title and price of an item owned by the user → expect 200 with updated values
   - Verify `ItemEdit` records were created for both fields

5. **PATCH /items/{id} — forbidden edit**
   - Attempt to edit an item from a channel not owned by the user → expect 403

6. **POST /items/{id}/sold — mark as sold**
   - Mark an item as sold → expect status "sold"
   - Mark same item as sold again → still "sold" (idempotent)

7. **POST /items/{id}/relist — relist**
   - Relist a sold item → expect status "active"
   - Verify SoldReport records are deleted

8. **POST /items/{id}/clear-reports — clear without relist**
   - Clear reports on a reported_sold item → expect status stays "reported_sold" but reports are gone

9. **Edit history logging**
   - Edit title only → expect 1 ItemEdit record
   - Edit title, price, and specs in one request → expect 3 ItemEdit records (only for fields that actually changed)

10. **Re-trigger alert matching**
    - Edit price of an item → verify `process_new_item` is called
    - Edit only title of an item → verify `process_new_item` is NOT called

### Frontend Tests (manual QA checklist)

11. **Channel card tap → inventory modal**
    - Tap a channel card in Stores tab → ChannelInventory opens
    - Back button returns to channel list (state preserved)

12. **Product grid infinite scroll**
    - Open a channel with 30+ products → scroll down → products load in batches
    - Verify "loading" spinner appears at bottom during fetch

13. **Filters and search**
    - Filter by "Sold" → only sold items shown
    - Search by title fragment → matching items filtered
    - Change sort to "Price: High-Low" → order changes

14. **Product edit panel**
    - Tap a product → edit panel opens
    - Change title and price → Save → values update in grid
    - Verify "View original Telegram post" link is present
    - Verify category dropdown cascades subcategory options

15. **Specs editor**
    - Add a new spec key-value pair → renders in the form
    - Remove a spec → disappears
    - Save → specs persist on re-open

16. **Status controls**
    - Mark as Sold → item shows "Sold" badge in grid
    - Re-list → badge removed, item back to active
    - Clear Reports → reports cleared, item remains in reported_sold status

17. **Settings tab**
    - Switch to Settings tab → pause/resume and remove buttons work
    - Stats display product count correctly
    - Tab state preserved when switching between Products and Settings

18. **Error states**
    - Edit a product from a different channel (manipulated URL) → error toast
    - Network failure during save → error message, form stays open for retry

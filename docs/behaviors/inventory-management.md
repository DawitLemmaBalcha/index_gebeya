# Inventory Management — Store Owner Product Control

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

Channel owners get a full inventory management interface in the Stores tab. From their channel list, they can open a channel's product catalog, edit individual products (specs, category, title, price, status), and manage their listings with full control. The interface is tab-based and designed for future extensibility (boosting, analytics, bulk actions).

---

## Behavioral Rules

### 1. Channel-to-Inventory Navigation

**Rule 1.1 — Tap Channel Opens Inventory Modal**
In the Stores tab, tapping a channel card opens a full-page inventory modal for that channel. The modal replaces the current view — it is not a popup over the Stores tab.

**Rule 1.2 — Modal Tabs**
The inventory modal has two tabs:
- **Products** — searchable, filterable grid of all items indexed from this channel
- **Settings** — pause/resume indexing, remove channel, stats

**Rule 1.3 — Back Navigation**
A back button in the modal header returns to the Stores channel list. The Stores tab state is preserved.

### 2. Products Tab

**Rule 2.1 — Product Grid**
All items from the selected channel displayed in a grid (same card layout as the main explore feed, with status badges overlaid). Items are sortable by: Most Recent, Price High-Low, Price Low-High.

**Rule 2.2 — Status Badges**
Each product card shows its status badge:
- No badge = `active`
- "Sold" = `sold` 
- "⚠️ Reported" = `reported_sold`
- "Paused" = channel-level `indexing_paused`

**Rule 2.3 — Filtering**
Filter by status: All, Active, Sold, Reported. Search within the channel's products by title.

**Rule 2.4 — Infinite Scroll**
The product grid supports infinite scroll — loads more items as the owner scrolls down. Channel-specific pagination endpoint: `GET /channels/{id}/items?limit=20&offset=0`.

### 3. Product Edit Panel

**Rule 3.1 — Tap Product Opens Edit Panel**
Tapping a product in the inventory grid opens the edit panel. This is a focused view for that single product — not a full product detail page.

**Rule 3.2 — Editable Fields**
All fields are editable:
- **Title** — text input, pre-filled with current value
- **Description** — text area, pre-filled
- **Price** — number input in ETB
- **Category** — dropdown from taxonomy
- **Subcategory** — cascading dropdown based on selected category
- **Specs** — dynamic key-value editor (add/remove/edit individual spec pairs)

**Rule 3.3 — Save Behavior**
A "Save Changes" button at the bottom. On save: item updated in-place → `process_new_item` re-triggered for alert matching if price or specs changed → confirmation toast.

**Rule 3.4 — View Original Post**
A persistent link at the top of the edit panel: "View original Telegram post" → opens the post in Telegram.

**Rule 3.5 — Status Controls**
Below the editable fields, status action buttons:
- **Mark as Sold** — immediate, authoritative, no confirmation needed (reversible)
- **Re-list** — resets to `active`, clears all `SoldReport` records
- **Clear Reports** — removes `SoldReport` records without changing status (for pre-threshold cleanup)

### 4. Settings Tab

**Rule 4.1 — Same as Current Stores Functionality**
Pause/Resume indexing. Remove channel (with confirmation modal). Channel stats (product count, views, clicks).

**Rule 4.2 — Preserved During Edit**
Settings tab state is preserved when switching between Products and Settings tabs.

### 5. Forward-Looking Architecture

**Rule 5.1 — Tab Extensibility**
The modal's tab system uses a tab registry pattern. Adding a new tab (e.g., "Analytics" or "Boost") only requires registering a new tab component — no changes to the modal shell.

**Rule 5.2 — Status as Enum**
The `status` field is an enum/string, not a boolean. Adding new statuses (e.g., "boosted", "featured") requires no schema migration beyond extending the enum.

**Rule 5.3 — Edit History**
All edits are logged in an `ItemEdit` table (item_id, field, old_value, new_value, edited_by, timestamp). This supports future audit trails and undo functionality.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Owner tries to edit a product from a channel they don't own | 403 Forbidden |
| Product no longer exists (was deleted by cleanup) | "This product is no longer available" — remove from grid |
| Edit panel open while background cleanup deletes the item | Save returns error: "Product was removed during cleanup." — grid refreshes |
| Owner changes category to invalid value | Dropdown only offers valid taxonomy values — impossible to select invalid |

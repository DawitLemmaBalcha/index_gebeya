# TECH-21 Blueprint — Dedup Redesign + Alert Filter Badges

**Date:** 2026-07-28
**Parent:** NB-40
**Priority:** HIGH

---

## Goal

Replace the edit-in-place dedup behavior with a soft-delete + recreate strategy in ingestion, update the processing DM to acknowledge replacements, and show "Strict Brand" / "Strict Model" filter badges on alert cards.

---

## Files to Modify

1. `backend/models.py` — add `is_active` column to `Item`
2. `backend/main.py` — add schema migration for `items.is_active`
3. `backend/schemas.py` — add `replaced` field to `IngestionResponse`
4. `backend/api/routes/ingestion.py` — soft-delete old item, fall through to create, add `replaced` flag; cleanup dead imports
5. `listener/client.py` — pass `replaced` flag through `send_to_api` response
6. `listener/worker.py` — branch DM edit message on `replaced` flag
7. `frontend/src/pages/AlertsPage.jsx` — render "Strict Brand" / "Strict Model" pills

---

## Strict Import Map

### New/modified imports (no new packages needed):

**ingestion.py — imports to remove:**
- `import time` (line 2) — completely unused, dead import
- `delete` from `from sqlalchemy import select, delete` (line 9) — only used in the edit-in-place gallery cleanup block being removed; `select` stays

**ingestion.py — imports that stay:**
- All other imports unchanged

**models.py — no new imports:**
- `Column`, `Boolean` already imported from sqlalchemy via existing import line

**schemas.py — no new imports:**
- `bool` is a built-in; `Optional` already imported; no changes needed

**client.py — no new imports:**
- Just reads an additional key from `data` dict

**worker.py — no new imports:**
- Just reads `result.get('replaced')` from existing dict

**AlertsPage.jsx — no new imports:**
- `parsePreferences` already defined locally (line 65); no external dependency changes

---

## Step-by-Step Execution

### Step 1 — Add `is_active` to Item model (`backend/models.py`)

In the `Item` class (around line 196, after the `created_at` column definition):
- Add a new column: `is_active` as a `Boolean` with `default=True` and `nullable=False`
- This column will be used for soft-deletion when a duplicate is detected

### Step 2 — Add schema migration (`backend/main.py`)

In the Phase 3 migrations block (around line 78, after the existing `is_active` migration for `channels`):
- Add a new `conn.execute(text(...))` block that runs `ALTER TABLE items ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE`
- Follow the same try/except pattern as the existing TECH-19 migration
- Add a logger.info confirming the migration

### Step 3 — Add `replaced` to IngestionResponse schema (`backend/schemas.py`)

In the `IngestionResponse` class (line 109):
- Add a new field: `replaced: bool = False` below the `error` field
- This field will be serialized in the JSON response so the listener can detect replacement events

### Step 4 — Refactor dedup block in ingestion.py (`backend/api/routes/ingestion.py`)

#### Step 4a — Remove dead imports
- Remove `import time` on line 2
- Change `from sqlalchemy import select, delete` to `from sqlalchemy import select` (remove `delete`)

#### Step 4b — Initialize `was_replaced` flag
- Before the `if visual_vector is not None:` block (around line 138), add a local variable: `was_replaced = False`

#### Step 4c — Replace the edit-in-place block (lines 170–208)
The block currently spans from the `if best_match is not None and best_sim >= 0.98:` condition (line 170) through the `return IngestionResponse(...)` (line 208).

**Replace the entire block (lines 171–208) with:**
- Set `best_match.is_active = False` (soft-delete)
- Set `was_replaced = True`
- Log the match: `logger.info(f"Dedup: soft-deleted item #{best_match.id} (sim={best_sim:.4f}), creating replacement")`
- Remove the `return` statement — execution must fall through to the normal item creation at line 220
- Remove ALL the field-update lines (title, description, price, currency, phone, category, subcategory, specs, image_path, image_vector, original_caption, created_at)
- Remove the gallery-delete-and-recreate block (`db.execute(delete(ItemImage)...)`)
- Remove the `db.commit()`, `db.refresh()`, and `process_new_item()` calls in this block
- The `else:` block (lines 210–218) does NOT need changing — it still runs when no match is found

**Key: Do NOT call `db.commit()` in this block.** Let the soft-delete remain in the session's pending state. It will be committed together with the new item creation at line 249. If the new item creation fails, the exception handler's `db.rollback()` at line 276 will automatically undo the soft-delete — satisfying the error behavior spec: "Old item is restored to active. No data lost."

#### Step 4d — Add `replaced` to the success response (around line 267)
In the `return IngestionResponse(...)` for the normal creation path, add the parameter `replaced=was_replaced` to the constructor call.

### Step 5 — Pass `replaced` through listener client (`listener/client.py`)

In the `send_to_api` function, inside the success branch (around line 19):
- After reading `price = extracted.get('price')`, read `replaced = data.get('replaced', False)`
- Add `"replaced": replaced` to the returned dictionary

### Step 6 — Branch DM edit on `replaced` flag (`listener/worker.py`)

In the DM edit success block (lines 80–91), modify the success branch (currently lines 83–91):

**Before** the existing `if result.get('success'):` check, compute the edit_text:

- If `result.get('replaced')` is truthy:
  - Construct the replacement message: `"✅ Updated: {title} — {formatted_price} ETB\n⚠️ Replaced previous listing. Use different images for different products."`
  - Format the price the same way as before (`{price:.0f} ETB` or "Ask for Price")

- Else (not replaced, normal creation):
  - Use the existing format: `"✅ Indexed: {title} — {price:.0f} ETB"` or `"✅ Indexed: {title} — Ask for Price"`

- Edit the DM with the computed `edit_text`

The failure branch (non-success, lines 92–97) remains unchanged — it still shows the generic error message.

### Step 7 — Show "Strict Brand" / "Strict Model" badges (`frontend/src/pages/AlertsPage.jsx`)

In the "Smart filter toggles" section (lines 161–174), replace the current generic rendering of all preference entries:

**New behavior:**
- Filter `Object.entries(prefs)` to only include entries where the key is `"strict_brand"` or `"strict_model"` AND the value is `true`
- For `strict_brand`, display the label as `"Strict Brand"`
- For `strict_model`, display the label as `"Strict Model"`
- Use the same styling classes (`bg-blue-100 text-blue-700`, `px-2 py-0.5 rounded-lg text-[10px] font-medium`)
- If no strict preferences are enabled (filtered list is empty), render nothing — the wrapping `{Object.keys(prefs).length > 0 && (` guard ensures the container only appears when there are preferences at all

---

## Testing Requirements

### ingestion.py tests:
1. **Soft-delete + create:** Post a duplicate image → verify old item has `is_active=False`, new item has a different `item_id`, and `replaced=True` is returned
2. **No-match path unaffected:** Post a unique image → verify new item created normally, `replaced=False`
3. **Rollback on failure:** Mock new item creation to fail after soft-delete → verify old item remains `is_active=True`
4. **Gallery preservation:** After replacement, verify old item's gallery images still exist in `item_images`

### worker.py tests:
5. **Replacement DM:** Verify `replaced=True` in result produces the "Updated" message with replacement warning
6. **Normal DM:** Verify `replaced=False` produces the existing "Indexed" message unchanged
7. **No DM for unregistered:** Verify replacement DMs are NOT sent to channels without `registered_by`

### AlertsPage.jsx tests:
8. **Strict Brand badge:** Render an alert with `preferences='{"strict_brand":true}'` → verify "Strict Brand" pill appears in blue
9. **Strict Model badge:** Render an alert with `preferences='{"strict_model":true}'` → verify "Strict Model" pill appears
10. **Both badges:** Render with both strict flags → verify both pills appear
11. **No badges:** Render with `preferences='{}'` or false values → verify no pills appear
12. **Malformed JSON:** Render with malformed `preferences` string → verify no crash, empty state handled

### Schema migration test:
13. **Migration applied:** Verify ALTER TABLE runs without error on startup when column already exists (idempotent)
14. **Default value:** Verify existing items get `is_active=True` default after migration

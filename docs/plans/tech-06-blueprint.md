# TECH-06: Post Deduplication via Vector Matching — Implementation Blueprint

**Date:** 2026-07-24
**Parent Ticket:** NB-21
**Goal:** After composite vector generation in the ingestion pipeline, compare the new visual fingerprint against the same channel's recent items. If a near-identical match is found (cosine similarity ≥ 0.98), update the existing item instead of creating a duplicate.

---

## Files to Modify/Create

| Action | File Path                              |
|--------|----------------------------------------|
| MODIFY | `backend/api/routes/ingestion.py`      |

No new files are created. No other backend files require modification.

---

## Strict Import Map

### New imports to add to `backend/api/routes/ingestion.py`

| Import Statement                                      | Purpose                                           |
|-------------------------------------------------------|---------------------------------------------------|
| `from datetime import datetime, timedelta`            | Compute the 30-day cutoff for candidate queries   |
| `from ai_engine.matcher import cosine_similarity`     | Reuse the existing vector comparison function      |
| `from sqlalchemy import delete`                       | Remove stale gallery records on item update        |

### Existing imports already available (no change needed)

- `import numpy as np` — already used for centroid computation
- `from sqlalchemy.orm import Session` — already a dependency
- `from sqlalchemy import select` — already used for channel lookup
- `from models import Item, Channel, ItemImage` — all three already imported
- `from services.alerting import process_new_item` — already imported at line 14
- The `logger` instance is already configured (`logger = logging.getLogger("index_ingestion")`)

### No new exports

The `IngestionResponse` schema (return type of the endpoint) already accepts an `item_id` field. No schema changes are required.

---

## Logic Integration Point

The dedup check must be inserted **after channel resolution** (line 96, where `channel.id` becomes available) and **before item creation** (line 98, where `new_item = Item(...)` is constructed). At this point:

- `visual_vector` (the composite centroid) is already computed (lines 53–55).
- AI extraction data (`ext`) is already available (lines 67–83).
- `channel.id` is resolved (lines 88–96).
- `post.image_path` and `post.album_paths` are still in scope for gallery handling.

The dedup block replaces the current unconditional item creation flow with a conditional: match → update, no-match → create.

**Control flow overview:**

```
Phase 2: Visual Intelligence (vector generation)    [lines 29–62]
Phase 1: AI Extraction Pipeline                     [lines 67–83]
Channel Resolution                                  [lines 88–96]
    ↓
━━━ NEW DEDUP BLOCK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ↓
  visual_vector is not None?
    ├── YES → query candidates → compute similarities → best found?
    │         ├── best_sim >= 0.98 → UPDATE existing item → alert → return
    │         └── best_sim < 0.98  → PROCEED to normal create
    └── NO  → PROCEED to normal create
    ↓
Normal: Create Item                                 [lines 101–127]
Alert trigger                                       [line 143]
```

---

## Step-by-Step Execution

### Step 1: Add new import statements

Add three new imports to the top of `ingestion.py`:
- `from datetime import datetime, timedelta`
- `from ai_engine.matcher import cosine_similarity`
- `from sqlalchemy import delete`

Place them alongside the existing SQLAlchemy import line (`from sqlalchemy import select` → extend to `from sqlalchemy import select, delete`).

---

### Step 2: Insert dedup check after channel resolution

After the channel resolution block (after line 96: `db.flush()`) and before the `# 3. Create Item` comment (line 98), insert a conditional dedup block.

The block structure:

#### 2a. Guard — only run dedup if we have a vector

Begin the dedup block with:
- `if visual_vector is not None:` — items without vectors produce no false matches.

If `visual_vector` is `None`, skip the entire dedup block and fall through to normal item creation.

---

#### 2b. Query candidate items

Inside the guard:

- Compute the cutoff timestamp:
  - `cutoff_date = datetime.utcnow() - timedelta(days=30)`
- Build a SQLAlchemy select statement:
  - Query the `Item` table.
  - Filter: `channel_id == channel.id`.
  - Filter: `created_at >= cutoff_date`.
  - Filter: `image_vector IS NOT NULL`.
- Execute the query and collect results into a list.

Log at DEBUG or INFO level: the number of candidate items being compared.

---

#### 2c. Brute-force comparison loop

- Initialize tracking variables:
  - `best_match = None` (will hold the matched Item ORM object)
  - `best_sim = 0.0`
- Iterate over each candidate item:
  - Convert the candidate's `image_vector` to a Python list. Handle both numpy array (`.tolist()`) and native list cases.
  - Call `cosine_similarity(visual_vector, candidate_vector)`.
  - If the returned similarity > `best_sim`, update `best_sim` and set `best_match = candidate`.

**Optimisation note (for future):** For production with large channel histories, this O(n) linear scan could be replaced with a pgvector `<=>` distance query filtered at the database level. The current brute-force approach is acceptable for channels with modest posting volumes.

---

#### 2d. Match branch — update existing item

If `best_sim >= 0.98`:

1. **Log the match:**
   - `logger.info(f"Dedup: matched item #{best_match.id} (sim={best_sim:.4f})")`

2. **Update item fields** on `best_match`:
   - `best_match.title = getattr(ext, 'title', getattr(ext, 'item_name', 'Unknown Item'))`
   - `best_match.description = getattr(ext, 'description', 'No description')`
   - `best_match.price = getattr(ext, 'price', 0)`
   - `best_match.currency = getattr(ext, 'currency', 'ETB')`
   - `best_match.phone_number = getattr(ext, 'contact_phone', None) or getattr(ext, 'phone_number', None)`
   - `best_match.category = getattr(ext, 'category', 'Uncategorized')`
   - `best_match.subcategory = getattr(ext, 'subcategory', 'General')`
   - `best_match.specs = str(getattr(ext, 'item_metadata', {}))`
   - `best_match.image_path = post.image_path`
   - `best_match.image_vector = visual_vector`
   - **Also update:** `best_match.original_caption = post.text` — ensures the raw caption stays current.

3. **Refresh timestamp:**
   - `best_match.created_at = datetime.utcnow()` — signals that this is a "recently updated" item.

4. **Refresh gallery images:**
   - Delete all existing `ItemImage` records for this item. Use either:
     - `db.execute(delete(ItemImage).where(ItemImage.item_id == best_match.id))`, or
     - Clear the ORM relationship (`best_match.images = []`) relying on `cascade="all, delete-orphan"`.
   - After deletion, insert new gallery records using the same logic as lines 121–125:
     - If `post.album_paths`: iterate and add one `ItemImage(item_id=best_match.id, image_path=path)` per path.
     - Else if `post.image_path`: add a single `ItemImage(item_id=best_match.id, image_path=post.image_path)`.

5. **Persist:**
   - `db.commit()`
   - `db.refresh(best_match)`

6. **Trigger alert matching:**
   - Call `process_new_item(db, best_match.id)` — this re-runs the full 3-stage alert pipeline on the updated item, so a price drop on a repost generates buyer notifications.

7. **Return immediately:**
   - Return `IngestionResponse(status="success", item_id=best_match.id, extracted_data=extraction_data, error=None)`.
   - **Do not fall through** to the normal creation path.

---

#### 2e. No-match branch — log and proceed

If `best_sim < 0.98` (or if no candidates were found at all):

- `logger.info(f"Dedup: new item (best sim={best_sim:.4f})")`
- Do nothing else; the normal item creation code (lines 98–143) executes as before.

If no candidate items existed (empty result set), log: `"Dedup: no candidates found for channel {channel.id}, creating new item."`

---

### Step 3: Verify the normal creation path is unchanged

The existing code block at lines 98–143 (`# 3. Create Item` through `process_new_item(db, new_item.id)`) must remain intact and execute only when the dedup check does NOT return early (i.e., no match found).

The dedup block MUST use an early-return pattern (`return IngestionResponse(...)`) on match so that the existing code is not reached. On no-match, the dedup block exits without returning, and execution falls through to the existing creation code.

---

### Step 4: Edge-case handling

The `@build` agent must ensure the following edge cases are handled:

1. **Candidate with broken vector:** If a candidate's `image_vector` fails to convert to a list (malformed data), catch the exception per-item, log a warning, and skip that candidate. Do not abort the entire dedup loop.

2. **Zero-vector candidates:** The `cosine_similarity` function already handles zero-norm vectors by returning `0.0`. No additional guard needed.

3. **Channel has zero recent items:** The candidate query returns an empty list. Log and proceed to normal creation.

4. **Item with no image_vector in DB:** Already filtered by `image_vector IS NOT NULL` in the query.

5. **Concurrent ingestion race:** Two workers processing posts from the same channel simultaneously could both read the same stale candidate list and both decide "no match," creating two items. This race is acceptable for now (low probability given the serial worker architecture), but the `@build` agent should add a comment acknowledging the race condition and noting that a unique constraint on `(channel_id, image_vector)` with a distance operator (pgvector) could be added in the future.

---

## Testing Requirements

The `@build` agent must implement and verify the following test cases:

### Core Functional Tests

1. **Exact duplicate repost matched:**
   - Ingest a post with image A. Note the item ID.
   - Ingest the same post again (same channel, same image) within 30 days.
   - Assert: a second item is NOT created; the first item's ID is returned; the first item's `created_at` is refreshed; the first item's fields are updated with the new extraction data.

2. **Different image → new item:**
   - Ingest a post with image A.
   - Ingest a post with visually distinct image B from the same channel.
   - Assert: a second, distinct item is created with a new ID.

3. **Different channel → no dedup:**
   - Ingest image A from channel X.
   - Ingest image A from channel Y (different channel).
   - Assert: two separate items are created (one per channel).

4. **Cross-channel isolation:**
   - Verify the candidate query uses `channel_id == channel.id` and does NOT compare against items from other channels.

### Threshold and Similarity Tests

5. **Near-identical image (sim ≥ 0.98) is matched:**
   - Ingest an image, then ingest a slightly modified version (e.g., re-compressed or slight crop) of the same product from the same channel. The composite vector should be very close.
   - Assert: the existing item is updated, not duplicated.

6. **Visually similar but different product (sim < 0.98) creates new item:**
   - Ingest an image of a red iPhone, then an image of a red phone case from the same channel. Their vectors should be similar but below the 0.98 threshold.
   - Assert: two distinct items are created.

### Time-Window Tests

7. **30-day window respected:**
   - Manually set an item's `created_at` to 31 days ago.
   - Ingest the same image from the same channel.
   - Assert: the 31-day-old item is NOT returned by the candidate query; a new item is created.

8. **Edge of window:**
   - Set an item's `created_at` to exactly 29 days ago (within the 30-day window).
   - Ingest the same image.
   - Assert: the match is found and the item is updated.

### Reprocessing Tests

9. **Price drop on repost triggers alert:**
   - Create an active alert that would match the product.
   - Ingest the product at price 10,000 ETB. Confirm a notification is created.
   - Repost the same product at price 5,000 ETB (same image, same channel).
   - Assert: the existing item's price is updated to 5,000; `process_new_item` is called; the alert engine re-evaluates and creates a notification for the price drop.

### Graceful Degradation Tests

10. **No vector available:**
    - Ingest a post with no images (text only).
    - Assert: `visual_vector` is `None`; the dedup block is skipped entirely; a new item is created normally. No crash.
    - Log should not contain any dedup-related messages (since the block is skipped).

11. **Candidate with malformed vector:**
    - Insert a row directly into the `items` table with an intentionally malformed `image_vector` (e.g., a JSON string that is not a valid 512-dim array) for the same channel and within 30 days.
    - Ingest a legitimate post with a valid vector.
    - Assert: the malformed candidate is skipped (with a warning log); the dedup loop continues; a new item is created normally. No crash.

### Logging Tests

12. **Match log format:**
    - On match, verify the log line matches: `Dedup: matched item #<id> (sim=<float>)`

13. **No-match log format:**
    - On no-match, verify the log line matches: `Dedup: new item (best sim=<float>)`

14. **No-candidates log:**
    - When the candidate query returns zero rows, verify the log line: `Dedup: no candidates found for channel <id>, creating new item.`

### Gallery Tests

15. **Gallery refresh on update:**
    - Ingest a post with album_paths = [img1.jpg, img2.jpg].
    - Repost with album_paths = [img1.jpg, img3.jpg] (same vector, different gallery).
    - Assert: the item's `ItemImage` records are replaced; the old gallery entries are deleted; only the new paths exist.

---

## Rollback and Safety Notes

- The dedup logic is purely additive. If it misbehaves (e.g., false negatives creating duplicates), the worst case is temporary duplicates in the catalog — no data loss.
- The existing ingestion flow is preserved verbatim for the no-match path.
- The `INGESTION_WORKER_INTERVAL` serial worker (30s per item) means race conditions on concurrent dedup are extremely unlikely.
- If the dedup ever needs to be disabled, it is isolated to a single block in `ingestion.py` that can be commented out or guarded by a feature flag.

# Post Deduplication — Redesigned

> **Status:** ⚠️ NOT YET IMPLEMENTED  
> **Supersedes:** NB-21 (previous edit-in-place approach)

---

## Overview

When a seller reposts the same product, the system detects it via visual fingerprint matching and creates a fresh listing instead of editing the old one. This ensures alerts fire for price changes and prevents duplicate suppression from blocking legitimate notifications. The seller receives a clear DM explaining what happened and how to avoid unintended replacements.

---

## Behavioral Rules

### 1. Soft-Delete + Recreate

**Rule 1.1 — Detection (unchanged)**
Same as before: cosine similarity ≥ 0.98 against same channel's items from last 30 days = match.

**Rule 1.2 — Soft-delete the old item**
The matched existing item is marked `is_active = False`. It is excluded from search results and feeds but preserved for historical reference. No data is lost.

**Rule 1.3 — Create a new item**
A new item record is created with the new extraction data, new `item_id`, new `created_at`. This new item goes through the normal ingestion pipeline — including alert matching and processing DMs.

**Rule 1.4 — Alert re-trigger works**
Because the new item has a different `item_id`, duplicate suppression doesn't block it. Price drops generate fresh notifications for all matching alerts.

### 2. Seller Notification

**Rule 2.1 — Processing DM acknowledges replacement**
When the replacement item is successfully indexed, the processing DM (the one that starts as "⏳ Processing...") is edited to:

> "✅ Updated: [Title] — [Price] ETB  
> ⚠️ This replaced your previous listing with the same image. If this is a different product, please use a different image for each listing."

**Rule 2.2 — No DM for non-registered channels**
Channels without `registered_by` don't receive any DMs. The replacement happens silently.

### 3. Cleanup

**Rule 3.1 — Old edit-in-place code removed**
The field-update block in `ingestion.py` that edited the existing item's title, price, description, etc. is removed. The dedup flow is now: detect → soft-delete old → create new.

**Rule 3.2 — Gallery cleanup**
The old item's gallery images are NOT deleted. They remain associated with the soft-deleted item for historical reference. The new item gets its own gallery from the repost.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Soft-delete fails (DB error) | Logged, new item still created. Old item remains active — duplicate may appear in search until cleaned up. |
| New item creation fails after soft-delete | Old item is restored to active. No data lost. |
| Seller posts genuinely different product with same image | They get the "updated" DM. They learn to use different images. The new product overrides the old one — this is acceptable, the seller is responsible for unique images per unique product. |

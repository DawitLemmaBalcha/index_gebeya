# Search

> **Status:** ⚠️ NOT YET FULLY IMPLEMENTED (see pending-behaviors.md for gaps)

---

## Overview

Buyers can discover products through three search modes: text search, image search, and category browsing.

---

## Behavioral Rules

### 1. Text Search

**Rule 1.1 — Hybrid Scoring**
When a buyer types a search query, the system computes two scores for every product:
- **Visual Score:** How well the product's image fingerprint matches the fingerprint of the search text. This captures conceptual similarity (e.g., searching "laptop" matches products whose images look like laptops).
- **Text Score:** How similar the product title and description are to the search text using fuzzy matching. This captures exact keyword matches (e.g., "Dell XPS" matches titles containing "Dell").

**Rule 1.2 — Weighting**
The visual score carries 60% weight and the text score carries 40% weight. The combined score determines ranking.

**Rule 1.3 — Strict Top-K Ranking**
Results are returned in descending order by combined score, with no minimum threshold. Even if the best available result has a very low score (e.g., 0.01), it is still shown if it is among the top results. The system trusts that some signal is better than no signal.

**Rule 1.4 — Search Logging**
Every text search is logged as an interaction event, capturing:
- The search query text
- The number of results found
- The buyer's identity (user or session)

**Rule 1.5 — Post-Search Filtering**
After the top results are retrieved, additional filters are applied:
- **Price Range:** Products outside the specified min/max price are removed.
- **Category:** Products not matching the selected category are removed (unless the category is "All").

These filters are applied after ranking, which means a search for "phone" with a max price of 5,000 ETB may return fewer results than requested because high-ranking expensive phones are filtered out.

### 2. Image Search

**Rule 2.1 — Visual-Only Scoring**
When a buyer uploads an image for search, only the visual similarity score is used. Text similarity is entirely excluded (weighted at 0).

**Rule 2.2 — Image Fingerprint Generation**
The uploaded image is converted into a mathematical fingerprint using the same process as product images. This fingerprint is compared against all stored product fingerprints.

**Rule 2.3 — Temporary Image Handling**
The uploaded image is saved temporarily for fingerprint generation and immediately deleted afterward. It is never stored permanently.

**Rule 2.4 — Image Search Logging**
Image searches are logged with the original filename for analytics purposes.

### 3. Category Browsing

**Rule 3.1 — Client-Side Filtering**
Category browsing is not a separate backend operation. The frontend fetches the full feed and filters it locally by category and subcategory. This means:
- A buyer browsing "Electronics → Laptops" sees products from the "For You" feed that happen to match those categories.
- If the feed contains 50 items but only 3 are laptops, the buyer sees only 3 items.

**Rule 3.2 — "Other" Subcategory Handling**
If a buyer selects a category's "Other" subcategory, the system shows products in that main category whose subcategory is not one of the known subcategories for that category, OR whose subcategory is explicitly "Other" or "Uncategorized."

**Rule 3.3 — Subcategory Reset**
When a buyer changes the main category, the subcategory selection resets to "All."

### 4. Related Products

**Rule 4.1 — Visual Similarity**
When viewing a product detail page, "Similar Items" are found by using the product's visual fingerprint as a search query for an image search, excluding the product itself.

**Rule 4.2 — Missing Fingerprint**
If the product has no visual fingerprint (e.g., it was ingested without images), no related products are returned.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Text search query is empty | The search returns results based only on the visual score (which is computed from a zero-vector — effectively random ranking) |
| Uploaded image cannot be processed | A 400 error is returned: "Could not process image" |
| Uploaded image is in an unsupported format | Same as above — no specific format error message |
| Search returns zero results | An empty list is returned with a count of 0 |
| Post-search filters remove all results | An empty list is returned even though the search itself found items |

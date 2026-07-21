# Recommendation Feed ("For You")

> **Status:** ⚠️ NOT YET FULLY IMPLEMENTED (see pending-behaviors.md for gaps)

---

## Overview

The "For You" feed is the default browsing experience for buyers. It adapts to the buyer's interaction history, transitioning from a cold-start trending feed to a personalized mix of session context, category discovery, and trending content.

---

## Behavioral Rules

### 1. Buyer Identity Resolution

**Rule 1.1 — Identity Priority**
When determining whose feed to build, the system checks in this order:
1. **Known User:** If the request carries a valid user identifier, use the buyer's history.
2. **Anonymous Session:** If no user identifier exists but a session identifier is present, use session-level history.
3. **Total Stranger:** If neither identifier is present, return the trending feed (no personalization).

**Rule 1.2 — Session Scope**
A session is identified by a client-generated identifier and spans all browsing activity within that identifier's lifetime. There is no server-side session expiration — the session lives as long as the client keeps the same identifier.

### 2. Buyer Maturity States

The system classifies buyers into three maturity states based on how many distinct products they have interacted with:

**Rule 2.1 — Cold Start (< 3 interactions)**
- The buyer has viewed almost nothing. The system has no signal.
- Feed composition: **100% Trending** (the most popular items in the last 24 hours).

**Rule 2.2 — Explorer (3–10 interactions)**
- The buyer has browsed enough to establish a short-term context but not enough for category-level patterns.
- Feed composition: **70% Session Context + 30% Trending**.

**Rule 2.3 — Regular (> 10 interactions)**
- The buyer has enough history to detect category preferences and long-term interests.
- Feed composition: **40% Session Context + 40% Category Discovery + 20% Trending**.

### 3. Feed Components

#### 3.1 Trending
**Rule 3.1.1 — Popularity Window**
"Trending" is defined as the products with the most unique interactions (views, searches, etc.) in the last 24 hours. Interactions older than 24 hours are not counted.

**Rule 3.1.2 — Fallback to Recent**
If no products have any interactions in the last 24 hours (e.g., a brand-new system), trending falls back to the most recently added products.

#### 3.2 Session Context
**Rule 3.2.1 — Short-Term Window**
Session context is derived from the last 5 products the buyer interacted with during their current session.

**Rule 3.2.2 — Visual Averaging**
The visual fingerprints of those 5 products are averaged together to create a single "context fingerprint." Products visually similar to this fingerprint are returned — excluding the 5 products already viewed.

**Rule 3.2.3 — Empty Context**
If none of the last 5 interacted products have visual fingerprints, no session context results are returned.

#### 3.3 Category Discovery
**Rule 3.3.1 — Top 3 Categories**
The buyer's interaction history is analyzed to find their top 3 most-engaged categories (by count of interactions per category).

**Rule 3.3.2 — Weighted Allocation**
The total discovery budget is split proportionally: if the buyer has 50% of their interactions in "Mobile Phones," 30% in "Electronics," and 20% in "Fashion," those categories receive 50%, 30%, and 20% of the discovery slots respectively. Each category must receive at least 1 slot.

**Rule 3.3.3 — Within-Category Selection**
For each category, an average fingerprint is computed from all of the buyer's interactions in that category. Products within the same category that are visually similar to this average are returned, excluding products the buyer has already interacted with.

**Rule 3.3.4 — No Categories**
If the buyer's interactions cannot be mapped to any categories (e.g., all interactions are searches with no item, or items have no category), category discovery returns nothing.

### 4. Feed Assembly

**Rule 4.1 — Deduplication**
After all components are collected, duplicate products are removed. The first occurrence of a product is kept; subsequent occurrences are discarded.

**Rule 4.2 — Fill to Requested Size**
If deduplication reduces the feed below the requested size, the remaining slots are backfilled from Trending.

**Rule 4.3 — Cap at Limit**
The final feed is capped at the requested limit (default: 20 items).

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| No interaction data at all (new system) | Trending fallback → Recent items fallback |
| Buyer has interactions but all items were deleted | Falls back to Trending |
| Session vector averaging produces all zeros (no visual fingerprints) | No session results are returned; other components fill the gap |
| Requested limit is very high (> available products) | Returns all available products without error |

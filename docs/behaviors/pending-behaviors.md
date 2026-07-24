# Pending Behaviors — Gap Ledger

> **Purpose:** This document maps every known behavioral gap, missing rule, or unhandled edge case in the system. Each entry is a uniquely identified ticket with a concrete user-acceptance criterion.

---

## NB-1: Stop Alert Button Missing alert_id in Notification Response

**Priority:** HIGH
**Affected Features:** Notifications, Alerts
**File(s):** `backend/schemas.py` (NotificationResponse), `listener/notifications.py`

**The Gap:**
When the Notification Poller delivers a match to a buyer, it includes a "Found it / Stop Alert" button. Tapping this button should deactivate the alert that triggered the notification. However, the backend's `NotificationResponse` schema does not include the `alert_id` field. As a result, the poller cannot determine which alert to stop, and the button may not appear or may fail silently.

**User Acceptance Criteria:**
- When a buyer taps "Found it / Stop Alert" on any match notification, the specific alert that triggered that notification is deactivated.
- The notification poller must reliably receive an alert identifier alongside every pending notification.
- The backend must include the `alert_id` in the notification response.

---

## NB-2: Inconsistent Authentication Between Reviews and Alerts

**Priority:** HIGH
**Affected Features:** Reviews, Alerts, Authentication
**File(s):** `backend/api/routes/reviews.py`, `backend/api/routes/alerts.py`

**The Gap:**
Review submissions use HMAC-SHA256 cryptographic verification of the Telegram `initData` string. Alert creation uses a different method: it parses the `initData` as a query string and extracts the user JSON directly, without cryptographic validation. These two paths should use the same, unified authentication approach.

**User Acceptance Criteria:**
- Alert creation and review submission must use identical identity verification logic.
- A single shared verification function should serve both endpoints.
- A buyer authenticated via one method should have the same identity guarantees as the other.

---

## NB-3: Dead Code — Legacy Alert Service

**Priority:** MEDIUM
**Affected Features:** Alerts (no user impact)
**File(s):** `backend/services/alerts.py`

**The Gap:**
The file `services/alerts.py` contains a `check_alerts()` function that performs simple keyword matching and a `notify_user()` stub that prints to console. This was superseded by `services/alerting.py` (the 3-stage pipeline), but the old file remains in the codebase. It may confuse future contributors.

**User Acceptance Criteria:**
- The legacy alert service file is removed or clearly marked as deprecated with a migration note.
- No import or reference to the legacy service remains in any active code path.

---

## NB-4: Image Search Lacks Price and Category Filters

**Priority:** MEDIUM
**Affected Features:** Search
**File(s):** `backend/api/routes/search.py`, `backend/services/search.py`

**The Gap:**
When a buyer performs a text search, they can (in principle) filter by price range and category. When they perform an image search, no such filters are available. A buyer searching by image for a "cheap phone" might get a mix of ₵2,000 phones and ₵200,000 phones with no way to narrow down.

**User Acceptance Criteria:**
- Image search must accept optional price range and category filters, identical to text search.
- Results are post-filtered after visual ranking, consistent with text search behavior.

---

## NB-5: No Pagination on Key Endpoints

**Priority:** MEDIUM
**Affected Features:** Items, Reviews
**File(s):** `backend/api/routes/items.py`, `backend/api/routes/reviews.py`

**The Gap:**
The "Recent Items" endpoint and the "Channel Reviews" endpoint return a fixed or limited number of results with no pagination (no offset or cursor). As the catalog grows, a buyer browsing all items or reading older reviews cannot navigate beyond the first page.

**User Acceptance Criteria:**
- The Recent Items endpoint accepts an offset parameter so the frontend can implement infinite scroll or paginated browsing.
- The Reviews endpoint accepts an offset parameter to load older reviews beyond the initial 10.
- The frontend updates to use these pagination controls.

---

## NB-6: Alert Matching Blocks Ingestion Response

**Priority:** MEDIUM
**Affected Features:** Ingestion, Alerts
**File(s):** `backend/api/routes/ingestion.py` (line 143)

**The Gap:**
After a product is stored, the alert matching engine (`process_new_item`) is called synchronously within the same request. If alert matching is slow (many active alerts, slow LLM Judge calls), the ingestion API response is delayed. The code comment acknowledges this should be a background task but it remains synchronous "for consistency."

**User Acceptance Criteria:**
- The seller/channel submitting a post receives a prompt acknowledgment that their product was ingested.
- Alert matching runs independently after the ingestion response is returned.
- If alert matching fails after the product is stored, the product remains in the catalog regardless.

---

## NB-7: No Rate Limiting on Public Endpoints

**Priority:** HIGH
**Affected Features:** Search, Feed, Items
**File(s):** All route files

**The Gap:**
The search, feed, and item endpoints have no rate limiting. A malicious actor or buggy client could flood these endpoints, degrading service for all buyers and consuming AI provider quotas (search vectorization uses the text embedding model on every request).

**User Acceptance Criteria:**
- A single buyer (identified by session or user ID) cannot exceed a reasonable number of requests per minute on search, feed, or item endpoints.
- Rate-limited buyers receive a clear message asking them to wait, not a cryptic error.
- Legitimate buyer browsing patterns are not affected.

---

## NB-8: Anonymous Buyer Error Messaging for Alerts

**Priority:** LOW
**Affected Features:** Alerts, Frontend
**File(s):** `frontend/src/components/AlertModal.jsx`

**The Gap:**
When an anonymous buyer (not inside Telegram) tries to create an alert from the Mini App, the frontend checks for `window.Telegram?.WebApp?.initData`. If missing, it shows a generic error: "Please open in Telegram to create alerts." However, the same check uses "user_id_placeholder" as a fallback value, which can produce confusing server-side errors instead of a clean client-side rejection.

**User Acceptance Criteria:**
- If the Mini App is opened outside Telegram, the "Create Alert" button is either hidden or clearly disabled with an explanation.
- No placeholder or fake credentials are ever sent to the backend.
- The error message is shown before the buyer fills out the alert form, not after submission.

---

## NB-9: Session-Based Analytics Headers Are Not Validated Server-Side

**Priority:** LOW
**Affected Features:** Analytics
**File(s):** `backend/api/routes/analytics.py`, `frontend/src/utils/analytics.js`

**The Gap:**
Session IDs are generated client-side and trusted by the server without validation. A malicious client could fabricate session IDs to pollute analytics data or impersonate another buyer's session for feed manipulation.

**User Acceptance Criteria:**
- Session identifiers are validated to conform to the expected format (UUID).
- Abnormally short, long, or malformed session IDs are rejected or replaced.
- The system does not rely solely on client-provided identifiers for any security-sensitive operation.

---

## NB-10: Weak Session Context Vectors Produce Empty Recommendations

**Priority:** MEDIUM
**Affected Features:** Recommendation Feed
**File(s):** `backend/services/recommendation.py`

**The Gap:**
The Session Context component of the "For You" feed computes an average fingerprint from the last 5 products the buyer viewed. If any of those products have no visual fingerprint, the component may return nothing — silently. The buyer sees fewer results but has no indication why.

**User Acceptance Criteria:**
- If fewer than 3 of the last 5 viewed products have visual fingerprints, the Session Context component gracefully degrades by using only the available fingerprints.
- The system logs a warning when session context is skipped due to missing fingerprints so operators can diagnose catalog gaps.
- The buyer never sees an empty feed purely because of missing fingerprints; other components fill the gap.

---

## NB-11: No Review Moderation System

**Priority:** MEDIUM
**Affected Features:** Reviews
**File(s):** `backend/api/routes/reviews.py`

**The Gap:**
Reviews are published instantly with no moderation, flagging, or removal mechanism. A malicious buyer could post inappropriate content, spam, or fake reviews with no recourse for the seller or platform operators.

**User Acceptance Criteria:**
- At minimum, a channel owner or platform operator can view all reviews and remove those that violate guidelines.
- Ideally, buyers can flag reviews for review by operators.
- Removed reviews do not affect the Trust Score calculation.

---

## NB-12: Trust Score Does Not Account for Review Quality or Freshness

**Priority:** LOW
**Affected Features:** Reviews
**File(s):** `backend/api/routes/reviews.py`

**The Gap:**
The Trust Score is a pure average of all ratings. It does not account for:
- **Review Freshness:** A channel with 50 reviews from 2 years ago and 1 bad review today still shows a high score. Recent reviews should carry more weight.
- **Reviewer Credibility:** A verified buyer who has reviewed many channels might be more trustworthy than a new account.
- **Statistical Confidence:** A channel with 1 five-star review and a channel with 100 four-star reviews both show ~4.0, but the latter is far more reliable.

**User Acceptance Criteria:**
- Recent reviews (within the last 30 days) carry more weight than older reviews.
- The Trust Score display includes a visual indicator of confidence (e.g., "4.2 based on 3 reviews" vs "4.1 based on 342 reviews").
- The pure average is retained as a fallback until a more sophisticated model is implemented.

---

## NB-13: Notification Delivery Has No Retry Limit

**Priority:** MEDIUM
**Affected Features:** Notifications
**File(s):** `listener/notifications.py`

**The Gap:**
Unlike the ingestion worker (which drops items after 10 retries), the notification poller retries failed deliveries indefinitely every 5 seconds. If a buyer has permanently blocked the bot, their notifications will clog the poller forever, consuming resources and delaying delivery to other buyers.

**User Acceptance Criteria:**
- After a configurable number of failed delivery attempts (e.g., 20 attempts over ~100 seconds), the notification is marked as FAILED and no longer retried.
- The system logs a distinct warning for permanently failed notifications so operators can investigate.
- Buyers who unblock the bot and create a new alert should receive notifications normally for future products.

---

## NB-14: Duplicate Message ID Handling During Ingestion

**Priority:** MEDIUM
**Affected Features:** Ingestion
**File(s):** `backend/models.py`, `backend/api/routes/ingestion.py`

**The Gap:**
The `telegram_message_id` field on items has a unique constraint at the database level, meaning the database will reject a duplicate. However, the ingestion code does not explicitly check for duplicates before attempting to insert. The error handling treats this as a generic failure, potentially triggering unnecessary retries in the worker.

**User Acceptance Criteria:**
- Before processing a post, the system checks whether a product with the same Telegram message ID already exists.
- If it does, the post is acknowledged as "already ingested" and skipped without error.
- The worker does not retry posts rejected due to duplication.

---

## NB-15: Empty Search Query Produces Meaningless Results

**Priority:** LOW
**Affected Features:** Search
**File(s):** `backend/services/search.py`

**The Gap:**
When a buyer submits a text search with an empty query string, the system still computes a visual similarity score (against a zero-vector fingerprint of the empty string). This produces a "ranked" list that is effectively random. The frontend debounce logic should prevent this, but if the backend is called directly with an empty query, the behavior is undefined.

**User Acceptance Criteria:**
- An empty search query returns a clear error: "Please enter a search term."
- The search endpoint validates that the query text is non-empty and at least 1 character long before performing any computation.

---

## NB-16: Worker Queue Is In-Memory (No Crash Recovery)

**Priority:** HIGH
**Affected Features:** Ingestion
**File(s):** `listener/worker.py`, `listener/monitor.py`

**The Gap:**
The ingestion worker queue is an in-memory Python `asyncio.Queue`. If the Listener container crashes or restarts, all queued but unprocessed posts are permanently lost. For a system that ingests content from live Telegram channels — where posts cannot be "replayed" — this means products can silently disappear.

**User Acceptance Criteria:**
- The worker queue persists to disk or uses a durable message broker so that queued posts survive Listener restarts.
- On restart, any unprocessed posts from before the crash are re-queued automatically.
- A post is only removed from the queue after successful ingestion (not before).

---

## NB-17: Product Gallery Inconsistency in API Responses

**Priority:** LOW
**Affected Features:** Items, Frontend
**File(s):** `backend/schemas.py`, `backend/services/search.py`

**The Gap:**
The `ItemResponse` schema has an `images` field with a custom validator that extracts image paths from related objects. However, the search service manually constructs `ItemResponse` objects and only includes the first image (`[row.image_path] if row.image_path else []`). This means search results and feed results may show only one image, while the product detail page (which fetches the item directly) shows the full gallery.

**User Acceptance Criteria:**
- Search results and feed items include all available gallery images, not just the thumbnail.
- The frontend can display multiple images consistently across all views (search results, feed, product detail).

---

## NB-18: Expired Alerts Are Never Permanently Removed

**Priority:** LOW
**Affected Features:** Alerts
**File(s):** `backend/services/alerting.py`, `backend/models.py`

**The Gap:**
Expired alerts are skipped during matching but are never deleted or archived. Over time, the alerts table will grow indefinitely with dead records, slowing down the matching process (which loads all active alerts on every ingestion).

**User Acceptance Criteria:**
- A periodic cleanup process (or a query filter) ensures that expired alerts are not loaded during matching.
- Optionally, alerts older than a certain threshold (e.g., 90 days past expiry) are permanently deleted.
- The matching engine does not degrade in performance as the number of total (including expired) alerts grows.

---

## NB-19: Missing Product Condition and Location in Frontend Display

**Priority:** LOW
**Affected Features:** Frontend
**File(s):** `frontend/src/pages/ProductPage.jsx`

**The Gap:**
The AI extraction pipeline captures the product condition (New, Used, Refurbished) and the seller's location. However, the product detail page does not consistently display these fields. The `ProductModal` component (an older modal view) shows condition and location, but the main `ProductPage` route does not.

**User Acceptance Criteria:**
- Every product detail page displays the product condition prominently.
- Every product detail page displays the seller's location.
- The display is consistent between the modal view (if still used) and the full page view.

---

## NB-20: LLM Judge "Fail-Open" Does Not Distinguish Between Error Types

**Priority:** LOW
**Affected Features:** Alert Matching
**File(s):** `backend/ai_engine/llm_client.py`

**The Gap:**
When the LLM Judge is unavailable (missing API key, network error, timeout, malformed response), the system always "fails open" — it accepts the match. However, a missing API key (configuration error) and a temporary network blip (transient error) are treated identically. The former means ALL matches are accepted without verification; the latter might self-resolve.

**User Acceptance Criteria:**
- If the LLM Judge is configured but temporarily unavailable (timeout, rate limit), fail open and continue.
- If the LLM Judge is permanently misconfigured (missing API key, invalid key), log a critical error and consider whether to fail open or reject all (operator decision).
- At minimum, the distinction is logged clearly so operators can diagnose.

---

## NB-21: Post Deduplication via Vector Matching [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Ingestion
**File(s):** `backend/api/routes/ingestion.py`, `backend/services/alerting.py`

**The Gap:**
When a seller reposts the exact same product (same images, same channel), the system blindly creates a duplicate item. Over time, sellers who repost daily will generate hundreds of duplicate entries, polluting the catalog and wasting ingestion resources.

**User Acceptance Criteria:**
- Before creating a new item, the system compares the new post's visual fingerprint against all items from the same channel posted in the last 30 days using cosine similarity.
- If similarity is ≥ 0.98, the existing item's price, description, and extracted fields are updated with the new data. The timestamp is refreshed. No duplicate is created.
- **When a repost replaces an existing item, the Alert Matching Engine is triggered for the updated item as if it were newly ingested.** This ensures price drops and other changes generate notifications.
- The platform must communicate to sellers that reusing the exact same image replaces the previous listing. Unique images per unique product are expected.
- Sellers with genuinely different products using different images are never affected.

---

## NB-22: Channel and User Profile Photos [IMPLEMENTED]

**Priority:** MEDIUM
**Affected Features:** Channels, Reviews, Frontend
**File(s):** `backend/models.py`, `backend/api/routes/ingestion.py`, `frontend/src/pages/ProductPage.jsx`, `frontend/src/components/ReviewModal.jsx`

**The Gap:**
Product detail pages and review cards currently show letter-avatar placeholders instead of actual photos. Channels have Telegram profile photos that are not fetched or displayed. Users submitting reviews have Telegram profile photos that are not captured from the Mini App's `initData`.

**User Acceptance Criteria:**
- **Channel photos:** On first ingestion of a channel, the system fetches and stores the channel's Telegram `file_id`. A background task re-checks active channels once per day for a changed `file_id`. Photos are served via the bot's `getFile()` method and displayed on product detail pages.
- **User photos on reviews:** At review submission time, the frontend captures `photo_url` from the Telegram Mini App `initData`. If the user has a public photo, it is displayed alongside their review. If not, the existing letter-avatar fallback is used.
- User photos auto-update because they are served directly from Telegram's CDN via the stored URL. Channel photos auto-update within 24 hours of the channel changing them.
- Both photo types gracefully degrade to the letter-avatar placeholder when unavailable.

---

## NB-23: Search Returns No Results (Empty Catalog + Missing Extension) [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Search
**File(s):** `backend/services/search.py`, database

**The Gap:**
The search bar in the frontend appears to not work. There are two potential causes:

1. **Empty catalog:** The database has zero ingested items. Searches technically execute but return empty arrays. From the buyer's perspective, search is "broken" because it never shows results regardless of query.
2. **Missing pg_trgm extension:** The hybrid search SQL uses `similarity()` from PostgreSQL's `pg_trgm` extension. If this extension was not enabled on the database (unlike `vector` which was explicitly enabled during setup), the search query will fail with a SQL error rather than returning results.

**User Acceptance Criteria:**
- The `pg_trgm` extension is enabled on the database alongside the `vector` extension during initial database setup.
- Search returns actual results when items exist in the catalog.
- Until items are ingested, the search endpoint returns a clean empty array (no SQL errors) and the frontend displays a "No items found" message rather than appearing broken.
- Add a startup check or migration that verifies `pg_trgm` is enabled and logs a clear error if it is not.

---

## NB-24: Infinite Scroll with Waterfall Recommendation Mix [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Recommendation Feed, Frontend
**File(s):** `backend/services/recommendation.py`, `backend/api/routes/feed.py`, `frontend/src/hooks/useShop.js`, `frontend/src/components/home/ProductGrid.jsx`

**The Gap:**
The "For You" feed returns a fixed batch of 50 items and stops. Buyers cannot browse deeper into the catalog. The recommendation mix (40% session / 40% discovery / 20% trending for Regular buyers) stays static regardless of scroll depth, never introducing serendipity or exploration.

**User Acceptance Criteria:**

**Infinite Scroll Behavior:**
- The frontend initially loads 20 items from `/feed/foryou`.
- When the buyer scrolls to the bottom of the grid, a loading indicator appears and the next 20 items are fetched by passing an `offset` parameter equal to the number of items already displayed.
- New items are appended to the existing grid without replacing or reordering items already shown.
- Server-side deduplication prevents any item from appearing twice across scroll pages.
- When the backend returns fewer than 20 items (or zero), a "You've seen everything" message is displayed and no further requests are made.

**Waterfall Mix by Scroll Depth (Regular buyers only, >10 interactions):**

| Scroll Depth | Session | Discovery | Trending | Wildcard |
|---|---|---|---|---|
| Page 1 (0–20) | 40% | 40% | 20% | — |
| Page 2 (21–40) | 25% | 45% | 30% | — |
| Page 3 (41–60) | 10% | 50% | 40% | — |
| Page 4+ (61+) | — | 40% | 40% | 20% |

**Wildcard Definition (Page 4+):**
- The wildcard pulls trending items from the buyer's **second-tier categories** — categories they have interacted with but that are not in their top 3. This introduces subtle, non-aggressive serendipity.
- If the buyer has zero second-tier interests (narrow browsing profile or cold start), wildcard falls back to general trending.
- Explorer (<10 interactions) and Cold Start (<3 interactions) states do not receive wildcards — they are still forming their profile.

**Backend Changes:**
- The feed endpoint must accept an `offset` parameter and return items starting from that position.
- The waterfall mix logic must be parameterized by scroll depth (offset / 20 = page number).
- Session context naturally exhausts as scroll depth increases because there are limited items visually similar to the last 5 viewed. Discovery and trending fill the gap.

---

## NB-25: Search Filters on Frontend (Price Range + Category) [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Search, Frontend
**File(s):** `frontend/src/hooks/useShop.js`, `frontend/src/components/home/NavBar.jsx`

**The Gap:**
The backend `SearchQuery` schema already supports `min_price`, `max_price`, and `category` as optional filters. The hybrid search service applies these as post-SQL filters. However, the frontend sends a hardcoded payload of `{ query, limit: 50 }` with no filter fields, and there is no UI for the buyer to specify price ranges or categories during search.

**User Acceptance Criteria:**
- After a buyer types a search query and results appear, a filter bar is displayed below the search input containing:
  - **Min Price** and **Max Price** number inputs (in ETB)
  - **Category** dropdown populated from the taxonomy, defaulting to "All"
- Filters are applied immediately when the buyer changes a value — no "Apply" button needed.
- Clear visual feedback when filters are active (e.g., count of active filters, highlighted chips).
- The `handleTextSearch` function passes `min_price`, `max_price`, and `category` to the backend alongside the query text.
- Sort by price or date is explicitly excluded from this ticket (see UF-7).

---

## NB-26: Missing Database Indexes — Vector (HNSW) and Text (GIN) [IMPLEMENTED]

**Priority:** CRITICAL
**Affected Features:** Search, Recommendation Feed
**File(s):** `backend/models.py`, `backend/services/search.py`, `backend/services/recommendation.py`

**The Gap:**
The hybrid search and recommendation engine both rely on vector similarity and text similarity. Neither has a database index. This means every search performs a full table scan — PostgreSQL loads every row's 512-dimensional vector and computes cosine distance sequentially. Text similarity via `pg_trgm` also scans the entire `items` table.

**Performance degradation by item count:**

| Items | Current (no index) | With indexes |
|---|---|---|
| 1,000 | ~0.05s | ~0.001s |
| 10,000 | ~0.5s | ~0.003s |
| 40,000 | ~2s | ~0.005s |
| 100,000+ | ~5s (unusable) | ~0.01s |

**The Fixes Required:**

1. **Vector Index (HNSW):** Add an HNSW index on `image_vector` using `vector_cosine_ops`. HNSW is the best default — O(log n) queries with ~99% recall, sub-millisecond even at millions of vectors. The column definition in SQLAlchemy must include the index directive, and the database migration must create it.

2. **Text Index (GIN):** Add a GIN index on the concatenated title + description columns using `gin_trgm_ops`. This accelerates the `similarity()` calls in the search WHERE clause and the lexical scoring computation. Without it, the text similarity scans every row every time.

**User Acceptance Criteria:**
- Searching with 10,000+ items in the catalog returns results in under 100ms.
- The recommendation feed (which also uses vector distance queries) returns in under 100ms.
- The pgvector extension (already enabled) and pg_trgm extension (see NB-23) are prerequisites — both indexes require their respective extensions.
- The HNSW index build is a one-time cost at migration time. Subsequent inserts are indexed incrementally.
- Both indexes are defined in the SQLAlchemy model so they are created automatically during `Base.metadata.create_all()` or documented for manual creation.

---

## NB-27: Channel & Group Bot Onboarding [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Listener, Channels
**File(s):** `listener/main.py`, `backend/models.py`, new handler module

**The Gap:**
There is no onboarding flow for channel/group owners. The bot silently discovers channels during ingestion. Owners have no way to know the bot is working, no instructions for how to add it, and no feedback when the bot's status changes. Channels auto-discovered during ingestion have no ownership metadata.

**User Acceptance Criteria:**
- `/addchannel` command returns clear step-by-step instructions for adding the bot as admin to a channel or group.
- When the bot is added as admin to a public channel/group, the owner receives a confirmation DM and the channel is registered with `registered_by` set to their Telegram ID.
- Private channels/groups (no @username) are rejected with a clear DM explaining the requirement.
- When added as a regular member (not admin), the owner receives a DM instructing them to re-add as admin.
- When the bot is demoted from admin to member, the owner receives a DM warning that ingestion is paused.
- When the bot is removed entirely, the owner receives a DM confirming their listings are no longer being updated.
- Re-adding the bot as admin immediately resumes ingestion with no manual resync.
- Every status transition is idempotent — no stale state, no manual commands needed.

---

## NB-28: Taxonomy Restructuring — Granular Main Categories [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** AI Classification, Frontend, Visual Hints
**File(s):** `backend/ai_engine/prompts.py`, `frontend/src/constants/taxonomy.js`, `frontend/src/components/CategoryChips.jsx`

**The Gap:**
The current taxonomy uses broad main categories (e.g., "Mobile Phones & Tablets" as one category, "Electronics" covering laptops, "Fashion" covering everything from clothing to shoes). This makes browsing imprecise — a buyer looking for laptops has to dig into "Electronics → Laptops & Computers." A buyer looking for shoes has to navigate "Fashion → Men's Shoes" or "Fashion → Women's Shoes." The taxonomy should have granular, consumer-facing main categories like other e-commerce platforms.

Additionally, the `CategoryChips.jsx` component has an inline copy of the taxonomy instead of importing from the shared constants file — a DRY violation that makes future taxonomy changes error-prone.

**User Acceptance Criteria:**
- The taxonomy is restructured to the locked structure defined in `docs/behaviors/taxonomy.md`:
  - "Mobile Phones & Tablets" split into "Mobile Phones" and "Tablets" as separate main categories
  - "Laptops & Computers" promoted from Electronics subcategory to its own main category
  - "Fashion" split into "Men's Fashion" and "Women's Fashion" as separate main categories
  - "Shoes" added as a standalone main category
  - All existing subcategories reassigned to their appropriate new main categories
- The frontend taxonomy in `taxonomy.js` matches the backend taxonomy in `prompts.py` exactly.
- `CategoryChips.jsx` imports from `taxonomy.js` instead of maintaining its own inline copy.
- The AI prompt dynamically incorporates the new taxonomy — no prompt text needs manual updating.
- The visual hints index rebuilds from the new taxonomy on API startup.
- All frontend components (CategoryBar, NavBar, SearchFilters, useShop) work with the new taxonomy without code changes since they read dynamically.

---

## NB-29: Slow Back Navigation — Feed Re-Fetches Unnecessarily [IMPLEMENTED]

**Priority:** HIGH
**Affected Features:** Frontend
**File(s):** `frontend/src/hooks/useShop.js`, `frontend/src/pages/Home.jsx`

**The Gap:**
When a buyer opens a product detail page and then navigates back to the home page, the entire feed is re-fetched from the backend. This causes a 10+ second delay before the product grid reappears. The feed data should be cached in memory so back navigation is instant — the feed only re-fetches when the buyer explicitly refreshes or pulls to refresh.

**User Acceptance Criteria:**
- Navigating from a product detail page back to the home page restores the feed instantly (no loading spinner, no re-fetch).
- The feed data persists in React state across route changes — it is not cleared when the buyer navigates away.
- The feed only re-fetches when the buyer performs an explicit refresh action (pull-to-refresh or a manual refresh button).
- Search results and visual search results are cleared when navigating back (these are transient query states).

---

## NB-30: No Visual Feedback During Search [IMPLEMENTED]

**Priority:** MEDIUM
**Affected Features:** Search, Frontend
**File(s):** `frontend/src/hooks/useShop.js`, `frontend/src/components/home/ProductGrid.jsx`

**The Gap:**
When a buyer types a search query, there is a 600ms debounce before the search fires, and then additional network latency before results appear. During this entire window, the UI shows no change — the product grid still displays the previous feed items or nothing at all. The buyer has no indication that their search is being processed. The `isSearchingText` state already exists in the hook but is never wired to the UI.

**User Acceptance Criteria:**
- As soon as the buyer begins typing (before the debounce fires), the product grid shows a skeleton loading state or spinner.
- The loading state persists through the debounce window and network fetch until results arrive.
- When results arrive, the loading state is replaced with results (or a "no results" message).
- The loading state is distinct from the infinite scroll loading spinner — the buyer can tell the difference between "searching" and "loading more feed items."

---

## NB-31: Long Category Names Overflow on Item Cards [IMPLEMENTED]

**Priority:** LOW
**Affected Features:** Frontend
**File(s):** `frontend/src/components/ItemCard.jsx`

**The Gap:**
On product cards, the category label is displayed in a chip with `max-w-[50%]` and `line-clamp-1`. Long category names like "Home, Appliances & Furniture" overflow the chip and bleed into the card background or get clipped mid-word. The text should truncate cleanly with an ellipsis.

**User Acceptance Criteria:**
- Category names on product cards that exceed the available width are truncated with an ellipsis ("Home, Applianc...").
- The truncated text does not overflow its container or bleed into adjacent elements.
- The full category name is visible on the product detail page (already the case — this is only a card-level fix).

---

## NB-32: Share Button Replaced with Mobile Navigation Bar on Product Page [IMPLEMENTED]

**Priority:** MEDIUM
**Affected Features:** Frontend
**File(s):** `frontend/src/pages/ProductPage.jsx`

**The Gap:**
The product detail page has a non-functional share button in the header that does nothing. Buyers who want to share can already navigate to the original Telegram post. Instead of the share button, the product page header should include the same navigation elements as the home page — a search bar and category menu — so buyers can search or browse without returning to the home screen.

**User Acceptance Criteria:**
- The share button is removed from the product detail page header.
- The product detail page header includes a search bar (same as the home page NavBar search).
- The product detail page header includes a hamburger menu or category selector for quick category browsing.
- The back arrow is preserved and remains functional.
- The header is sticky at the top of the page during scroll.
- Search from the product page behaves identically to search from the home page — it navigates to the home page with the search results pre-populated, or shows results in a dropdown/overlay on the product page.

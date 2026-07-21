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

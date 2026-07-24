# Technical Backlog

> Generated from `docs/behaviors/pending-behaviors.md` gap tickets.
> Each TECH ticket maps to one or more NB behavioral tickets.

---

## TECH-06 — Post Deduplication via Vector Matching

**Parent:** NB-21
**Priority:** HIGH
**Affected Files:**
- `backend/api/routes/ingestion.py` — add dedup check before item creation
- `backend/services/alerting.py` — trigger `process_new_item` on price-updated items
- `backend/ai_engine/matcher.py` — reuse existing `cosine_similarity()` function

**Description:**
When a seller reposts the same product (identical images, same channel), the system currently creates a duplicate item. Instead, the new post's visual fingerprint should be compared against the same channel's recent items. If the vectors match (cosine similarity ≥ 0.98), update the existing item rather than creating a new one. This also triggers alert matching so price drops generate notifications.

**Technical Work:**
1. After generating the composite visual vector in the ingestion pipeline, compare it against all items from the same channel posted in the last 30 days.
2. Use `cosine_similarity()` from `ai_engine/matcher.py` for comparison.
3. If a match is found (≥ 0.98):
   - Update the existing item's `title`, `description`, `price`, `currency`, `category`, `subcategory`, `specs`, `phone_number`, `image_path`, and `image_vector` with the new extraction data.
   - Refresh `created_at` to the current time (signals "recently updated").
   - Call `process_new_item(db, existing_item.id)` to re-trigger alert matching.
   - Return the updated item ID (not a new ID).
4. If no match found: create a new item as normal (existing flow).
5. Log the decision at INFO level: "Dedup: matched item #123 (sim=0.992)" or "Dedup: new item (best sim=0.45)".

**Acceptance Criteria:**
- [ ] Reposting the exact same image from the same channel updates the existing item instead of creating a duplicate
- [ ] Price changes on reposts trigger alert matching for the updated item
- [ ] Genuinely different products (different images) are never merged
- [ ] Only items from the last 30 days from the same channel are compared (performance)
- [ ] The dedup check runs AFTER vector generation but BEFORE database insertion
- [ ] Existing items without image vectors are skipped during comparison

---

## TECH-07 — Channel and User Profile Photos

**Parent:** NB-22
**Priority:** MEDIUM
**Affected Files:**
- `backend/models.py` — add `photo_file_id` to Channel model
- `backend/api/routes/ingestion.py` — fetch channel photo on first encounter
- `backend/api/routes/reviews.py` — capture `photo_url` from initData
- `listener/bot_ui.py` or new module — daily background task for channel photo refresh
- `frontend/src/pages/ProductPage.jsx` — display channel photo
- `frontend/src/components/ReviewModal.jsx` — display user photo on reviews

**Description:**
Product pages and review cards show letter-avatar placeholders. Add real photos: channel profile pictures fetched via Telegram Bot API, and user profile photos captured from the Mini App's initData during review submission.

**Technical Work:**

**Channel Photos:**
1. Add `photo_file_id` column (String, nullable) to the `Channel` model.
2. In the ingestion route, after resolving/creating a channel, check if `photo_file_id` is None. If so, call the Telegram Bot API (`getChat`) via the listener to fetch the channel's photo. Store the `big_file_id`.
3. Add a background task in the listener that runs once per day: fetch all active channels, call `getChat` for each, and update `photo_file_id` if it changed.
4. Add a new API endpoint `GET /channels/{channel_id}/photo` that calls `getFile` via the bot to get a download URL, then streams or redirects to it.
5. Frontend: on the product detail page, use `{API_BASE_URL}/channels/{channel.id}/photo` as the `src` for the channel avatar image instead of the letter placeholder.

**User Photos:**
1. In the review submission route, extract `photo_url` from the parsed initData `user` object (Telegram includes this for users with public photos).
2. Store it on the `Review` record (add `user_photo_url` column, nullable String).
3. Include it in the `ReviewResponse` schema.
4. Frontend: in the `ReviewModal` component, display the photo as an `<img>` with the letter-avatar as fallback.

**Acceptance Criteria:**
- [ ] Channel profile photo appears on product detail pages for channels that have one
- [ ] Channel photo updates within 24 hours when the channel changes their profile picture
- [ ] Channels without a photo show the existing letter-avatar fallback
- [ ] User profile photo appears next to reviews for users with public Telegram photos
- [ ] Users without public photos show the existing letter-avatar fallback
- [ ] User photos auto-update because they are served from Telegram's CDN
- [ ] The photo endpoints do not slow down product page loading

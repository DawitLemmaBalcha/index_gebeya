# Index Gebeya — Context & Domain Model

> **Living Document** — Last updated: Phase 3 (Alert Engine + Recommendation Feed)

---

## 1. What Is This System?

**Index Gebeya** is a Telegram-native e-commerce aggregator for the Ethiopian market. It monitors Telegram channels that post items for sale, enriches those products with AI-powered classification and visual understanding, and presents them to buyers through a Telegram Mini App and a companion Bot.

The system has three primary user-facing surfaces:
- **The Telegram Bot** (`@SuqListenerDevBot`) — for creating alerts, receiving match notifications, and launching the store.
- **The Mini App (Web Frontend)** — a React app embedded in Telegram for browsing, searching, and reviewing sellers.
- **The Ingestion Listener** — an invisible background worker that monitors partner channels and feeds products into the catalog.

---

## 2. Domain Entities (The Business Layer)

### 2.1 Channel (Seller)

A **Channel** represents a Telegram channel or group that posts items for sale.

| Property | Meaning |
|----------|---------|
| Username | The Telegram handle (e.g., `@phone_shop_addis`) |
| Title | Display name of the channel |
| Trust Score | A 0.0–5.0 rating derived from buyer reviews |
| Review Count | Total number of reviews received |
| Verified Status | A manual flag indicating the channel has been vetted |

**Key Rule:** A channel is created automatically the first time a post from that channel is ingested. It starts with a neutral trust score of 2.5.

### 2.2 Item (Product)

An **Item** is a single product extracted from a Telegram post. It is the core inventory unit.

| Property | Meaning |
|----------|---------|
| Title | A concise product name (AI-generated, 5–8 words) |
| Original Caption | The raw text from the Telegram post |
| Description | A cleaned, professional summary (AI-generated, 2–3 sentences) |
| Price | Numeric value in Ethiopian Birr (ETB) |
| Category / Subcategory | Classified using the Jiji Ethiopia taxonomy |
| Specs | Structured key-value pairs (e.g., RAM, Storage, Color) |
| Phone Number | Contact for the seller, extracted from the post |
| Image Paths | Gallery of product images (one thumbnail + full album) |

**Key Rule:** Every item carries a **Visual Fingerprint** (an AI-generated vector embedding) derived from its images. This enables visual similarity search and image-based product matching.

### 2.3 User (Buyer)

A **User** is a buyer identified by their Telegram account.

| Property | Meaning |
|----------|---------|
| Telegram ID | The unique numeric Telegram identifier |
| First Name / Username | From Telegram profile |

**Key Rule:** Users are created automatically on their first action (creating an alert, submitting a review, or any authenticated API call). There is no explicit registration flow.

### 2.4 Alert (Saved Search)

An **Alert** is a buyer's standing search — "notify me when you find this kind of product."

| Property | Meaning |
|----------|---------|
| Query Text | What the buyer is looking for (e.g., "iPhone 13 Pro") |
| Max Price | Optional cap in ETB; blank means "any price" |
| Preferences | Smart toggles: Strict Brand Match, Strict Model Match |
| Best Opportunity Score | The highest match score ever achieved for this alert (the "high water mark") |
| Expiry | Alerts automatically expire 14 days after creation |
| Status | Active or Inactive (soft-deleted) |

**Key Rules:**
- An alert's query text is converted into a vector embedding at creation time for similarity matching.
- Alerts do not match against items that exceed their max price (if one is set).
- An alert's "high water mark" prevents notification fatigue — ring-tier matches below the best-ever score are suppressed.
- Alerts expire 14 days after creation to prevent stale searches.

### 2.5 Notification (Alert Dispatch)

A **Notification** is a queued message waiting to be delivered to a buyer's Telegram DM.

| Property | Meaning |
|----------|---------|
| Match Tier | Either "bullseye" (strong match) or "ring" (opportunity match) |
| Match Score | A numerical score representing similarity strength |
| Status | PENDING (not yet sent), SENT (delivered), or FAILED |

**Key Rule:** Once a notification is successfully delivered to the buyer's Telegram DM, it is acknowledged and marked as SENT to prevent duplicate delivery.

### 2.6 Review (Seller Rating)

A **Review** is a buyer's rating and optional comment for a channel.

| Property | Meaning |
|----------|---------|
| Rating | 1 to 5 stars |
| Comment | Optional text feedback |

**Key Rules:**
- Each buyer may submit exactly **one review per channel**. Attempting a second review is rejected.
- When a review is submitted, the channel's Trust Score is recalculated as the average of all its ratings, and its Review Count is updated.
- Reviews require cryptographic verification of the buyer's Telegram identity.

### 2.7 User Interaction (Analytics Event)

A **User Interaction** is a recorded behavior — a view, a search, an alert creation, etc. It feeds the recommendation engine.

| Property | Meaning |
|----------|---------|
| Interaction Type | e.g., "view_item", "search", "image_search", "create_alert" |
| Item ID | The product involved (if applicable) |
| Metadata | Arbitrary contextual data (e.g., search query text) |

**Key Rules:**
- Interactions can be tied to a known user or an anonymous session.
- Interactions are logged asynchronously (background tasks) to avoid slowing down the user experience.
- The analytics endpoint is intentionally named `/activity` to avoid triggering browser ad-blockers.

---

## 3. Core Business Processes

### 3.1 Product Ingestion (Telegram → Catalog)

1. A Telegram channel posts a message (text, photo, or album).
2. The **Listener** captures the post, downloads images, and buffers albums (waiting briefly for all images in a media group to arrive).
3. The post is queued into a **Serial Worker** that processes one item every 30 seconds (rate-limited to respect the AI provider constraints).
4. The Worker sends the post to the **Backend** for parsing.

**AI Enrichment Pipeline:**
- Images are vectorized using a vision model (CLIP), and all album images are averaged into a single composite vector.
- The composite vector is compared against a pre-built **Visual Taxonomy Index** to guess which product categories the image "looks like" — these become "visual hints."
- The post text (and visual hints) is sent to an LLM (primary: Groq Llama 3.1, fallback: Gemini 2.0 Flash Lite) for structured extraction: title, description, price, category, subcategory, condition, location, contact phone, and specs.
- The resulting item is stored with its visual vector and all extracted data.

### 3.2 Alert Matching (Ingestion → Notification)

The Alert Engine is a **3-Stage Synchronous Pipeline** that fires immediately after a new item is stored:

**Stage 1 — Speed Pass (Identity Check):**
- Both the alert query and the item title are normalized (stripped of spaces, punctuation, and casing).
- If they match exactly (and the query has more than 3 characters), the match is instantly confirmed. No further checks needed.

**Stage 2 — Hybrid Matcher (Candidate Generation):**
- The alert's query vector and the item's image vector are compared using cosine similarity.
- The alert query text and the item title are compared using fuzzy string matching.
- These two scores are weighted equally (50/50) to produce a final score.
- If the score is below 0.55, the item is rejected. Otherwise, it proceeds to Stage 3.

**Stage 3 — LLM Judge (Verification):**
- The item title and alert query are sent to an LLM with a persona determined by the alert's preferences:
  - **Strict Model Match:** Rejects different models or generations (e.g., "iPhone 13" ≠ "iPhone 12").
  - **Strict Brand Match:** Accepts any model from the same brand, but rejects different brands.
  - **Loose / Category Match:** Accepts any brand as long as the product type matches (e.g., any blender, any laptop). Rejects accessories when the user wants the main product (e.g., rejects "phone case" when user wants "phone").
- If the LLM rejects the match, processing stops.

**Dispatch Rules:**
- **Bullseye** matches always trigger a notification.
- **Ring** matches only trigger if their score is within 5% of the alert's best-ever score (the high water mark). This prevents notification fatigue.

**Expiry Check:** Before any matching begins, expired alerts are silently skipped.

**Price Gate:** Items above the alert's max price are rejected before any similarity computation.

### 3.3 Notification Delivery (Backend → Telegram DM)

1. The **Notification Poller** (a background task in the Listener) checks the backend every 5 seconds for PENDING notifications.
2. For each pending notification, it formats a Telegram message with the item title, price, match tier emoji (🎯 for bullseye, ⭕ for ring), and a "Stop Alert" button.
3. The message is sent via Telegram DM to the buyer.
4. On success, the notification is acknowledged (marked SENT).
5. If a buyer clicks "Stop Alert," that alert is deactivated immediately.

### 3.4 Recommendation Feed ("For You")

The **For You** feed adapts to the buyer's maturity level:

| State | Condition | Mix Ratio |
|-------|-----------|-----------|
| **Cold Start** | < 3 interactions | 100% Trending (items with most views in 24h) |
| **Explorer** | 3–10 interactions | 70% Session Context + 30% Trending |
| **Regular** | > 10 interactions | 40% Session Context + 40% Category Discovery + 20% Trending |

**Feed Components:**
- **Session Context:** Items visually similar to the last 5 items the buyer viewed during this session.
- **Category Discovery:** Items visually similar to the buyer's top 3 most-viewed categories, weighted by interest level.
- **Trending:** Items with the highest interaction count in the last 24 hours.
- **Fallback:** If no interaction data exists, the feed shows the most recent items.

### 3.5 Search

The system supports three search modes:
- **Text Search:** A hybrid approach combining semantic (vector) similarity and lexical (text) similarity, weighted 60/40. Results are ranked by combined score and returned in strict top-K order (no threshold floor — even low-scoring results appear if they're the best available).
- **Image Search:** The buyer uploads a photo; the system vectorizes it and returns visually similar items. Text similarity is excluded (weight is 0).
- **Category Browse:** Items are filtered client-side by category and subcategory.

### 3.6 Seller Trust & Reviews

- Any buyer can rate any channel from 1 to 5 stars, with an optional comment.
- A buyer may only review a given channel once.
- The channel's Trust Score is the average of all its reviews, recalculated on each new review.
- Review submission requires cryptographic Telegram identity verification (HMAC-SHA256 of the Mini App initData).

---

## 4. AI Provider Strategy

The system uses a **Hybrid Router** with rate limiting:

| Provider | Model | Role | Rate Limit |
|----------|-------|------|------------|
| Groq | Llama 3.1 8B Instant | Primary: text extraction, LLM verification | ~27 RPM (2.2s interval) |
| Gemini | 2.0 Flash Lite | Fallback/Backup for text extraction | ~4 RPM (15s interval) |
| CLIP (Local) | ViT-B-32 | Image vectorization, visual taxonomy hints | On-demand, no limit |

**Fail-Open Strategy:** If the LLM Judge is unavailable during alert matching, the system defaults to accepting the match (fail-open) to avoid missing opportunities for buyers.

---

## 5. Taxonomy

The system enforces a strict taxonomy based on Jiji Ethiopia's category structure. Categories and subcategories are defined in a single dictionary shared by the AI prompts, the visual taxonomy index, and the frontend. The AI is instructed never to invent categories — unfamiliar items are classified as "Other → Uncategorized."

The taxonomy covers: Mobile Phones & Tablets, Electronics, Vehicles, Property, Home/Appliances/Furniture, Fashion, Health & Beauty, Commercial & Tools, Sports/Arts/Outdoors, Babies & Kids, Animals & Pets, Agriculture & Food, Services, and Other.

---

## 6. Service Topology (High-Level)

```
Telegram Channels ──→ Listener (Bot) ──→ Worker Queue ──→ Backend (API) ──→ Database
                          │                      │              │
                    Buyer DMs ←── Notification     │     AI Engines (Groq / Gemini / CLIP)
                          │         Poller ←───────┘
                          │
                    Buyer Commands (/start, /alert, /myalerts)
                          │
                          └──→ Mini App (Frontend) ←──→ Backend (Search, Feed, Reviews, Alerts)
```

**Four Docker Services:**
1. **Database** — PostgreSQL with pgvector extension for vector similarity operations.
2. **Backend (API)** — FastAPI serving all REST endpoints: ingestion, search, items, reviews, alerts, notifications, analytics, and feed.
3. **Listener** — The Telegram Bot. Handles channel monitoring (ingestion), buyer commands (/start, /alert, /myalerts), alert conversation flow, and notification delivery.
4. **Frontend** — React (Vite) served as the Telegram Mini App. Provides browsing, search (text + image), product detail pages, alert creation, and seller reviews.

---

## 7. Key Design Decisions

1. **Alerts expire after 14 days.** Prevents accumulating stale searches and conserves matching resources.
2. **High Water Mark on alerts prevents notification fatigue.** Ring-tier matches below the best-ever score are suppressed.
3. **The ingestion worker is serial and rate-limited (30s/item).** Respects AI provider rate limits and keeps the system predictable.
4. **Anonymous sessions are supported.** Buyers can browse without Telegram authentication; a session ID is generated client-side.
5. **Trust scores are pure averages.** No Bayesian weighting or review age decay (current state).
6. **Fail-open on LLM Judge unavailability.** Prefer noisy notifications over missed opportunities.
7. **Visual taxonomy hints are pre-computed at startup.** Avoids per-request latency during ingestion.

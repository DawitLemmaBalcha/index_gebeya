# Product Ingestion

> **Status:** ⚠️ NOT YET FULLY IMPLEMENTED (see pending-behaviors.md for gaps)

---

## Overview

The system ingests products from Telegram channel posts, enriches them with AI-powered understanding, and stores them in the catalog for browsing and alert matching.

---

## Behavioral Rules

### 1. Post Capture

**Rule 1.1 — Channel Posts Only**
The system only processes messages posted in Telegram channels, not private chats or groups where the bot is a member. Direct messages from buyers are handled by the bot command system, not ingestion.

**Rule 1.2 — Empty Post Rejection**
If a channel post contains no text (no caption) and no photo, it is silently ignored. Posts must have at least one of these to proceed.

**Rule 1.3 — Album Buffering**
When a channel sends multiple photos as a media group (album), the system does not process each photo individually. Instead, it buffers all images in the group and flushes them as a single item after a brief waiting period (2 seconds). The first image becomes the thumbnail; all images are stored as the gallery.

**Consequence:** If a seller posts an album with a single caption on the first image, and the buffer timer expires before all images arrive, the album is processed with whatever images have been collected so far. The remaining images are lost to that item.

### 2. Ingestion Worker

**Rule 2.1 — Serial Processing**
Products are processed one at a time, in the order they were captured. A new product does not begin processing until the previous one completes (success or final failure).

**Rule 2.2 — Fixed Pacing Interval**
After each product is processed (whether success or failure), the worker pauses for a fixed interval (default: 30 seconds) before pulling the next item from the queue.

**Rule 2.3 — Retry with Limit**
If a product fails to be processed by the backend (e.g., the API is temporarily down), the worker retries the same product up to a maximum number of attempts (default: 10). Between each retry, it waits the full pacing interval.

**Rule 2.4 — Dead Letter Handling**
If a product exhausts all retry attempts without success, it is permanently dropped. The worker logs this as a "dead letter" and moves to the next item.

### 3. AI Enrichment

**Rule 3.1 — Visual Fingerprint Creation**
Every product image is converted into a mathematical fingerprint (vector embedding). If the post contains multiple images, the fingerprints of all images are averaged together to produce a single composite fingerprint representing the item.

**Rule 3.2 — Visual Hints from Taxonomy**
The composite fingerprint is compared against a pre-computed index of all known product categories. The system identifies the top 3 categories the image "looks like" and includes these hints in the AI extraction prompt.

**Consequence:** If an image is ambiguous (e.g., a phone case that looks like a phone), the visual hints may be misleading. The AI is instructed to treat hints as suggestions, not ground truth.

**Rule 3.3 — LLM Routing**
The product text (and visual hints, if available) is sent to the primary AI provider (Groq) for structured extraction. If the primary provider fails or returns empty, the system falls back to the secondary provider (Gemini).

**Rule 3.4 — Strict Taxonomy Enforcement**
The AI must classify every product using only the predefined Jiji Ethiopia taxonomy. It is forbidden from inventing new categories or subcategories. If a product does not fit any specific subcategory, it must use "Other" for that main category. If it fits no main category at all, it must use "Other → Uncategorized."

**Rule 3.5 — Extraction Field Requirements**
The AI must extract: a concise title (5–8 words), a cleaned description (2–3 sentences without contact info), a numeric price, the currency (default ETB), category and subcategory from the taxonomy, the product condition, the seller's location, a contact phone number, and structured specifications (key-value pairs like RAM, Storage, Color, Model, Mileage).

### 4. Channel Resolution

**Rule 4.1 — Auto-Creation**
If a post arrives from a Telegram channel that the system has never seen before, a new channel record is created automatically with:
- Username set to the channel's handle (without `@` or `https://t.me/`)
- Title set to the channel's handle
- Trust Score initialized to 2.5 (neutral)
- Not verified

**Rule 4.2 — Deduplication by Message ID**
Each ingested product is tied to its original Telegram message ID. If the same message ID is ingested twice (e.g., due to a retry mechanism or listener restart), the system should detect and reject the duplicate.

### 5. Post-Ingestion Trigger

**Rule 5.1 — Automatic Alert Matching**
After a product is successfully stored, the Alert Matching Engine is immediately triggered for that product. It checks the new item against every active alert in the system.

**Consequence:** If the alert matching process is slow, it blocks the ingestion response from completing. The product will still have been stored, but the API caller waits for matching to finish.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| AI extraction fails entirely | The ingestion is rolled back (product is not stored) and an error is returned |
| Image download fails | The product is still created, but without images or visual fingerprint |
| Channel username cannot be parsed | The system uses a cleaned version of whatever identifier is available |
| Worker queue is empty | The worker waits indefinitely for new items |
| A single image in an album fails to download | Only successfully downloaded images are included in the album |

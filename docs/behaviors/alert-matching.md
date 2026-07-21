# Alert Matching

> **Status:** ⚠️ NOT YET FULLY IMPLEMENTED (see pending-behaviors.md for gaps)

---

## Overview

The Alert Matching Engine compares every newly ingested product against all active buyer alerts, using a 3-stage pipeline to determine whether the buyer should be notified.

---

## Behavioral Rules

### 1. Alert Lifecycle

**Rule 1.1 — Automatic Expiry**
Every alert expires 14 days after it is created. Once expired, it is never matched against new products, even if the buyer does not manually deactivate it.

**Rule 1.2 — Soft Deletion**
When a buyer deactivates an alert (via the /myalerts command or the "Stop Alert" button on a notification), the alert is marked as inactive but is not removed from the system. It can be viewed historically but will never trigger new notifications.

**Rule 1.3 — Query Vectorization at Creation**
When a buyer creates an alert, their text query (e.g., "iPhone 13 Pro") is immediately converted into a mathematical fingerprint (vector). This fingerprint is stored with the alert and used for all future matching — it is never recomputed, even if the underlying AI model is updated.

### 2. Pre-Check Gates (Before Any Matching)

**Rule 2.1 — Expiry Gate**
Before any matching computation begins, the system checks whether the alert has expired. Expired alerts are silently skipped. The buyer does not receive a notification that their alert expired.

**Rule 2.2 — Price Gate**
If the alert has a maximum price and the product has a listed price, and the product price exceeds the alert's maximum, the product is rejected immediately. No similarity computation is performed.

**Rule 2.3 — No-Price Product Handling**
If a product has no listed price (the seller did not include one in the post), it passes the price gate regardless of the alert's max price setting. The rationale: "call for price" items might still be within budget.

**Rule 2.4 — Missing Alert Vector**
If an alert somehow has no stored vector fingerprint (e.g., due to a creation error), it is skipped during matching.

### 3. Stage 1 — Speed Pass (Identity Check)

**Rule 3.1 — Normalized Exact Match**
Both the alert query text and the product title are stripped of all spaces, punctuation, and capitalization. If the cleaned alert query appears anywhere within the cleaned product title, and the alert query is more than 3 characters long, the match is instantly confirmed.

**Example:** Alert "iPhone 13" matches product "iPhone 13 Pro Max 256GB" because "iphone13" is contained within "iphone13promax256gb".

**Rule 3.2 — Short Query Protection**
If the alert query is 3 characters or fewer after normalization, the speed pass is disabled. This prevents false matches like "USB" matching "business" because "usb" appears in "business".

**Consequence of Speed Pass:** The match skips Stage 2 and Stage 3 entirely. The product is immediately dispatched for notification.

### 4. Stage 2 — Hybrid Matcher (Candidate Generation)

**Rule 4.1 — Dual Similarity Computation**
The system computes two scores:
- **Visual Similarity:** How mathematically close the product's image fingerprint is to the alert's query fingerprint.
- **Text Similarity:** How similar the product title is to the alert query using fuzzy string matching.

**Rule 4.2 — Equal Weighting**
The two scores are combined equally (50% visual, 50% text) to produce a single match score between 0.0 and 1.0.

**Rule 4.3 — Tier Classification**
- Score ≥ 0.82: **Bullseye** — strong match, proceed to Stage 3.
- Score ≥ 0.55: **Ring** — moderate match, proceed to Stage 3.
- Score < 0.55: **Miss** — rejected, processing stops.

### 5. Stage 3 — LLM Judge (Verification)

**Rule 5.1 — Persona Selection by Alert Preferences**
The LLM Judge adopts one of three verification personas based on the alert's smart filters:

**Strict Model Match (strict_model = true):**
- Rejects the match if the product is a different model, generation, or variant than what the alert specifies.
- Example: Alert "iPhone 13" → rejects "iPhone 12" and "iPhone 14". Only accepts "iPhone 13" variants.

**Strict Brand Match (strict_brand = true):**
- Accepts any model from the specified brand, but rejects different brands entirely.
- Example: Alert "iPhone 13" → accepts "iPhone 12", "iPhone 14". Rejects "Samsung Galaxy".

**Loose / Category Match (both false, the default):**
- Accepts any brand as long as the product type matches the intent.
- Rejects accessories when the buyer wants the main product (e.g., "phone" → rejects "phone case").
- Rejects parts when the buyer wants the complete product (e.g., "laptop" → rejects "laptop screen").

**Rule 5.2 — Fail-Open**
If the LLM Judge is unavailable (API down, timeout, missing credentials), the system assumes the match should be accepted. This prioritizes notifying the buyer over perfect precision.

### 6. Dispatch Decision

**Rule 6.1 — Bullseye Always Dispatches**
Any match that reaches the Bullseye tier (score ≥ 0.82) is always dispatched for notification, regardless of the alert's history.

**Rule 6.2 — High Water Mark Suppression**
The system tracks each alert's best-ever match score (the "high water mark"). A Ring-tier match is only dispatched if its score is within 5% of the high water mark.

**Rationale:** If a buyer's best-ever match was 0.91, a new match at 0.56 is likely noise and should be suppressed. But if their best-ever was 0.57, a 0.56 match is worth showing.

**Rule 6.3 — High Water Mark Update**
Whenever a Bullseye match is confirmed, and its score exceeds the alert's current high water mark, the high water mark is updated. Ring matches never update the high water mark.

### 7. Notification Creation

**Rule 7.1 — PENDING Status**
When a match is confirmed, a notification is created with status PENDING. It waits in the system's "mailbox" to be delivered by the Notification Poller.

**Rule 7.2 — Alert Last Triggered Timestamp**
The alert's "last triggered at" timestamp is updated to the current time whenever a notification is created for it.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Product has no visual fingerprint | The product is skipped for alert matching entirely |
| Alert has no stored vector | The alert is skipped |
| LLM Judge returns an invalid response | Fail-open: the match is accepted |
| LLM Judge times out | Fail-open: the match is accepted |
| No AI credentials configured | Stage 3 is skipped entirely (all matches proceed) |

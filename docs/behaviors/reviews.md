# Seller Reviews & Trust

> **Status:** ⚠️ NOT YET FULLY IMPLEMENTED (see pending-behaviors.md for gaps)

---

## Overview

Buyers can rate sellers (channels) on a 1–5 star scale with optional comments. These ratings contribute to the channel's Trust Score, which is visible to all buyers on product detail pages.

---

## Behavioral Rules

### 1. Review Submission

**Rule 1.1 — Identity Verification**
Before a review is accepted, the buyer's Telegram identity must be cryptographically verified. This ensures the buyer is who they claim to be and that the review is not fabricated.

**Rule 1.2 — Auto-Registration**
If the buyer does not yet exist in the system (first-time reviewer), their account is created automatically using their Telegram profile information (first name, username, Telegram ID).

**Rule 1.3 — One Review Per Channel Per Buyer**
Each buyer may submit exactly one review for a given channel. If a buyer attempts to submit a second review for the same channel, the submission is rejected with the message: "You have already reviewed this seller."

**Rule 1.4 — Rating Range**
Ratings must be between 1 and 5 stars inclusive. The frontend enforces that a rating is selected before submission.

**Rule 1.5 — Optional Comment**
Comments are optional. A buyer may submit a rating without any text.

### 2. Trust Score Calculation

**Rule 2.1 — Simple Average**
A channel's Trust Score is the arithmetic mean (simple average) of all its review ratings. It is recalculated every time a new review is submitted for that channel.

**Example:** If a channel has three reviews rated 5, 3, and 4, its Trust Score is (5+3+4)/3 = 4.0.

**Rule 2.2 — Review Count**
The Review Count is the total number of reviews a channel has received. It is updated alongside the Trust Score.

**Rule 2.3 — No Weighting or Decay**
The current system does not apply any weighting (e.g., verified buyer reviews count more) or time decay (e.g., older reviews matter less). All reviews contribute equally, regardless of when they were submitted or who submitted them.

### 3. Review Visibility

**Rule 3.1 — Product Detail Page**
When a buyer views a product, they see:
- The channel's Trust Score (formatted to one decimal place, e.g., "4.2 / 5.0").
- The channel's Review Count in parentheses.
- The most recent reviews (up to 10), each showing the rating stars and optional comment.
- Reviewer identity is displayed as "Verified User" (actual usernames are not shown).

**Rule 3.2 — Review Order**
Reviews are displayed in reverse chronological order (most recent first), limited to 10.

### 4. Review Moderation

**Rule 4.1 — No Moderation**
There is currently no review moderation system. All reviews are published immediately upon submission. There is no mechanism to report, flag, or remove inappropriate reviews.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Buyer submits without Telegram authentication | Review is rejected with "Please open in Telegram to rate" |
| Buyer submits duplicate review | Rejected with "You have already reviewed this seller" |
| Channel does not exist | The review fails (no specific error for this edge case) |
| Cryptographic verification fails | Rejected with "Authentication Failed" |
| Rating is outside 1–5 range | Not explicitly validated server-side |

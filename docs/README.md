# Index Gebeya — Documentation

## Structure

```
docs/
├── README.md                          # You are here
└── behaviors/
    ├── ingestion.md                   # Product Ingestion from Telegram channels
    ├── alert-matching.md             # 3-Stage Alert Matching Pipeline
    ├── notifications.md              # Notification Delivery to Buyers
    ├── recommendation-feed.md        # "For You" Personalized Feed
    ├── search.md                     # Text, Image, and Category Search
    ├── reviews.md                    # Seller Reviews & Trust Score
    ├── analytics.md                  # User Interaction Tracking
    ├── authentication.md             # Buyer Identity & Auth Methods
    └── pending-behaviors.md          # Gap Ledger (NB-1 through NB-20)
```

## What These Documents Are

Each file in `behaviors/` describes **business rules from the user's perspective** — what happens when a buyer searches, how an alert matches, what the notification looks like, etc. These are **not** technical specifications. They use no jargon about databases, endpoints, or code structures. They are written in plain business language so that any stakeholder (product manager, designer, QA, new engineer) can understand exactly how the system is supposed to behave.

Every behavioral rule is framed as:
- **State:** What condition must exist.
- **Action:** What the user or system does.
- **Consequence:** What happens as a result.

## How to Use These Documents

- **Onboarding:** Read `CONTEXT.md` first for domain terminology and system topology. Then read the behavior documents relevant to your area.
- **Feature Design:** When proposing a new feature, check the relevant behavior document to understand the current rules. Update the document as part of the implementation.
- **QA / Testing:** Each behavior document serves as a test plan. Every rule should have a corresponding test case.
- **Bug Triage:** If a behavior doesn't match the documented rule, it's a bug. If the behavior is intentional but undocumented, the document is the bug.

## The Gap Ledger

`pending-behaviors.md` tracks every known behavioral gap — missing rules, unhandled edge cases, and incomplete features. Each entry has:
- A unique ID (e.g., NB-1)
- A priority (HIGH / MEDIUM / LOW)
- The affected feature areas
- A concrete user-acceptance criterion

When a gap is resolved, its entry should be removed from the ledger and the resolved behavior should be documented in the appropriate behavior file.

## Related Documents

- **`CONTEXT.md`** (repository root): Domain model, terminology, service topology, and key design decisions.
- **`AGENTS.md`** (repository root): Instructions for the AI engineering swarm.

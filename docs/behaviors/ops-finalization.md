# Ops Finalization — Diagnose & Act (NB-55..NB-60)

> **Status:** ⚠️ NOT YET IMPLEMENTED (locked design, 2026-08-08 — see pending-behaviors.md NB-55..NB-60)

---

## Overview

The ops console's four stub sections (Catalog, Trust & Moderation, Users, Alerts & Notifications) are finalized as **action centers — not admin browsers**. The governing principle, locked with the operator:

> **sqladmin edits rows; the ops console diagnoses and acts.** Anything that reduces to "edit a row in table X" is rejected. What remains is: things that compute, things that diagnose, and things that make the engine act.

This supersedes `ops-console.md` §10 (the "deferred until pain is real" contract) — the pain is real, the direction is locked, and the stubs become four real surfaces plus a seller-side quality loop.

**The second locked principle — quality management belongs to the sellers.** The operator does NOT reclassify items or fix data by hand. The owner edit loop gives quality control to the people who know the product; the admin *watches* (Quality Events) and *enforces* (Radar + ban), never does.

---

## 1. The Owner Quality Loop

**Rule 1.1 — The Indexed/Updated DM carries the item.** When an item is indexed (or dedup-replaced), the channel owner's DM shows the item's **image, specification summary, and description** — the full picture, not just the title line — followed by two buttons: **Edit** and **Boost**.

**Rule 1.2 — The buttons are doors, not systems.** Both buttons deep-link into the web app — never a Telegram DM editing flow:
- **Edit** → the product edit panel in the seller's inventory (`/stores/{channelId}/{itemId}` — the same deep-link infrastructure the boost button already uses).
- **Boost** → the existing boost section (unchanged).
The owner edits with the existing, already-beautiful inventory UI. No new Telegram surface.

**Rule 1.3 — Category edits re-trigger the pipeline.** Today `update_item` re-runs alert matching only when price/specs change. A category/subcategory correction — the whole point of quality management — must ALSO re-trigger: category browse is server-side now, so the item must move in the catalog immediately and matching must re-evaluate it. (The edit panel's existing save path gains the category-change trigger.)

**Rule 1.4 — Channels without an owner get no DM** (`registered_by` is null) — their items fall to the Radar's anomaly detection instead. The loop is not universal; the enforcement layer covers the gap.

**Rule 1.5 — Edits are immediate.** An owner's correction applies instantly. No review state, no admin approval — they own the channel, it's their listing. The Radar (price anomalies, report spikes) is the abuse backstop.

---

## 2. Quality Events (the monitoring-not-doing layer)

**Rule 2.1 —** The ops console shows a **Quality Events** stream: every owner correction — category changed, price changed, title/description edited — as a live feed entry: *"Owner corrected category on item #952 (Other → Mobile Phones)"*.

**Rule 2.2 — Actionable visibility.** Each event carries a **Revert** action (restores the prior value, flags the owner for the Radar's watchlist). Events are not a passive audit log — they end in a verb. (This is the audit discipline the operator rejected for its own sake, re-homed as: *what the owners did, that you can act on.*)

**Rule 2.3 —** Event source: the existing `ItemEdit` history (TECH-23 already records one record per changed field) — surfaced and aggregated, not a new logging system.

---

## 3. The Ban Primitive

**Rule 3.1 — One flag, enforced at the seams.** A single `banned` boolean on User (reversible — no deletion, no destruction, evidence stays).

**Rule 3.2 — Banned buyers:** cannot create alerts, cannot submit reviews, cannot report items as sold. Existing active alerts pause; existing reviews stay visible (historical evidence) but the user can't act.

**Rule 3.3 — Banned sellers:** their channels pause indexing (no new items ingested) and their items **hide from browse/search/feed** (excluded at query time — never deleted). The channel row and items remain in the DB for evidence.

**Rule 3.4 — Enforcement points (the seams):** alert creation (`create_alert`), review submission, sold-report submission, ingestion (channel-level check), and browse/search/feed item queries. One check function, five call sites — the seam is the enforcement.

**Rule 3.5 — Unban is instant and restores everything** (alerts resume, items reappear, indexing resumes).

---

## 4. The Anomaly Radar

**Rule 4.1 — The platform finds its own problems.** A computed problem list, refreshed on load, each entry with severity + one-click resolution:

| Detection | Computed from | Resolution verb |
|---|---|---|
| **Dead-chat buyers** | Notification delivery failures (the "Chat not found" class) | Retry / Resolve / (cancel pending) |
| **Judge-error spikes** | `JUDGE_ERROR_COUNT` delta over a window | "Pause matching" kill action / dismiss |
| **Report spikes** | SoldReport counts at/near the threshold | View item → clear reports / dismiss |
| **Scam-pattern channels** | Low trust + price outliers (vs category median) + high report rate — the composite watchlist | Pause indexing / **Ban owner** / dismiss |
| **Price anomalies** | 0 ETB items, ≥10x category median | Hide item / dismiss |

**Rule 4.2 — Action chaining is a hard rule.** Every anomaly ends in at least one one-click verb. An anomaly with no action is just another sqladmin table — rejected.

**Rule 4.3 —** The Radar is the admin's daily driver: open `/ops` → see what's wrong → act. No hunting through tables.

---

## 5. Engine Diagnostics ("why did this happen?")

**Rule 5.1 — Per-item decision traces.** Search an item → the full alert-engine trace: how many active alerts were evaluated, and the stage-by-stage outcome for each — rejected at price gate, missed the 0.55 threshold, passed to the LLM judge (approved/rejected/errored), suppressed by high-water-mark, throttled, dedup-suppressed, dispatched.

**Rule 5.2 — Drill-down.** Any alert in the trace expands to its full story: score components, tier, judge verdict, suppression reason. This is the debugging surface for the entire matching engine — it cannot exist in sqladmin (the engine's decisions are computed, not stored).

**Rule 5.3 —** Source: the matching pipeline's existing logs/stages — the trace is reconstructed from the evaluation path, not new instrumentation where avoidable (the blueprint will decide the honest minimal source — likely a replay of the pipeline against the item with the same inputs).

---

## 6. Engine Actions ("make the system do things")

**Rule 6.1 —** A consolidated action surface for behavior-triggering verbs:
- **Re-run alert matching** for a specific item (after a fix/reclassification)
- **Retry a failed notification delivery**
- **Re-process a stuck ingestion post**
- **Trigger reconciliation now** (already in Payments — consolidated reference)
- **Trigger photo-refresh now**

**Rule 6.2 —** Every action: confirm dialog, audit row, immediate result feedback. Idempotent where the underlying operation is.

---

## 7. Users Tab (reframed)

**Rule 7.1 —** Lookup by telegram id / username → one screen: their reviews (with rating distribution), alerts, subscriptions, boosts, recent interactions — **visualized** (counts, mini-charts), not raw rows.

**Rule 7.2 —** Actions: **Ban / Unban** (the primitive, §3), pause-all-alerts. No row editing.

**Rule 7.3 —** The "delete user" cascade stays in sqladmin (destructive DB surgery); the console's Users tab is diagnosis + the ban lever.

---

## 8. Items Tab (reframed)

**Rule 8.1 —** Analytics, not rows: views-over-time per item, price distribution per category (histogram), per-channel performance (items, views, reports). All data exists (`user_interactions`, items, channels) — the pain is real because sqladmin cannot chart anything.

**Rule 8.2 —** The misclassification workbench is REJECTED (the owner loop §1 replaces it). The Items tab is pure visualization + the Radar's per-item drill-through.

---

## 9. Build Order (locked)

1. **Owner Edit DM loop + category re-trigger + Quality Events** (cheapest, highest daily value — changes the seller experience immediately; the foundation the Radar watches)
2. **The Anomaly Radar** (the admin's daily driver; ends in Engine Actions + Ban)
3. **Engine Diagnostics** (the deep-debugging tool)
4. **Users + Items reframed** (the analytics surface — least urgent, built last)

The shell never changes (ops-console.md Rule 1.6) — the four stubs become these surfaces; the tab labels update once.

---

## 10. Behavior Doc Cross-References

- Ops console shell/auth/audit/settings: `ops-console.md`
- ItemEdit history (Quality Events source): `inventory-management.md`, `dedup-redesign.md`
- Judge tri-state + counters (Radar detection source): `alert-matching.md` (NB-20)
- Owner DM infrastructure (Edit/Boost buttons): `processing-store-management.md`, `monetization.md` §5

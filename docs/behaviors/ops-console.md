# Platform Ops Console — `/ops`

> **Status:** ✅ IMPLEMENTED (2026-08-06, commits 93fe8c6..29a7376 on feat/ops-console, QA APPROVED)

---

## Overview

The **Platform Ops Console** is a standalone admin web page at `indexgebeya.cfd/ops` — **not** to be confused with sqladmin (`/admin`, the raw database UI). sqladmin edits *rows*; the console runs *operations*: curated views with joined context, one-click actions, health signals, settings control, and an audit trail. Anything the console would do that is "edit a row in table X" is out of scope — sqladmin already does that.

The console is **platform-wide**, not monetization-only. Every operational control needed in production lives here, organized into ten sections in a tabbed shell. The shell is the product; sections are features that slot in. Nothing is ever bolted on — the shell is built once with all ten sections scaffolded.

**Locked decisions (2026-08-06):**
- Route: `/ops` (same React app as the Mini App, but a standalone web page — NOT the Telegram Mini App bundle)
- Auth: existing admin credentials (username/password → session), **single admin role**; the auth seam carries a role field from day one so multi-role (viewer/operator/superadmin) is a config change later, never a rebuild
- No raw DB editing anywhere in the console
- No per-section separate auth — one console login, sections are navigation
- No role UI complexity in v1
- One shared audit wrapper, one shared settings model, one component kit across all sections

---

## 1. The Shell

**Rule 1.1 — Route and host.** The console lives at `/ops` in the existing frontend React app, served by the same containers as the Mini App. It is a full standalone page: no bottom navigation, no Telegram embed. Access is admin-only.

**Rule 1.2 — Layout.** Left rail navigation listing all ten sections. Section = route + module. Every section uses the shared component kit: table, empty-state, confirm-dialog, toast, inline-edit — no per-section bespoke UI patterns.

**Rule 1.3 — Auth seam.** Login with the existing admin credentials (`ADMIN_USERNAME`/`ADMIN_PASSWORD`). Session-based, same auth backend family as sqladmin but a **separate session namespace** (a console login must not grant sqladmin, and vice versa — scope is explicit). The session token carries a `role` field internally (always `admin` in v1) so the permission check is `has_role(session, "admin")` — future roles change data, not code.

**Rule 1.4 — One audit wrapper.** Every mutation from any section goes through a single audit helper that writes an `audit_log` row: `{admin_user, action, section, entity_type, entity_id, before, after, created_at}`. Sections cannot bypass it — the helper is the only mutation path the console exposes. Audit rows are never deleted (retention: keep indefinitely; volume is tiny).

**Rule 1.5 — One settings model.** A typed KV table `admin_settings` + a settings registry `(key, type, current_value, source: db|env, description)`. Every operational knob in the platform surfaces here. The registry powers the "effective config" view: for each key, show the live value and whether it comes from the DB or an env default.

**Rule 1.6 — All ten sections scaffolded from day one.** The nav shows all ten sections; unimplemented ones render a "Coming soon" stub. A visible roadmap, zero restructuring later. Sections may ship in any order; the shell never changes shape.

**Rule 1.7 — Read-mostly by design.** Views dominate; mutations are deliberate, confirmed actions. No inline row-editing of raw data.

---

## 2. The Section Map

| # | Section | Scope |
|---|----------|-------|
| 1 | Overview | Service/bot/worker health, scheduler runs, AI failover, star balance, pending payments |
| 2 | Catalog | **Actions only** (deferred): re-run alert matching, batch reclassify, price-anomaly scan. No row editing (sqladmin). |
| 3 | Trust & Moderation | **Actions only** (deferred): spike detection, watchlist, resolution workflows. No row editing (sqladmin). |
| 4 | Users | **Actions only** (deferred): footprint view, grant/revoke subscription, pause-all-alerts. No row editing (sqladmin). |
| 5 | Alerts & Notifications | **Actions only** (deferred): engine health, LLM judge fail rate, mailbox retry, delivery-failure queue. No row editing (sqladmin). |
| 6 | Monetization | Boost pricing + demand context, feature toggles, subscription settings, revenue dashboard, boost moderation, test tools |
| 7 | Payments | Star ledger, balance, reconciliation run-now, refunds |
| 8 | Settings & Flags | All operational knobs as live toggles + effective-config view |
| 9 | Audit | Every console mutation, who/when/before-after |
| 10 | Support Toolkit | Test boosts/subscriptions, payment-webhook simulator, deep-link generator |

**Rule 2.1 — The sqladmin boundary.** Sections 2–5 may only contain operations sqladmin cannot perform: joined context, health signals, engine actions, workflow resolution. Any screen that reduces to "edit row in table X" is rejected in design review.

**Rule 2.2 — Build order.** Shell first; then Section 1 (Overview, full), Section 6 (Monetization), Sections 8 + 9 (Settings & Audit — the foundations), Section 7 (Payments), Section 10 (Support Toolkit). Sections 2–5 are built only when the operational pain is real, as action centers.

---

## 3. Section 1 — Overview (full implementation)

**Rule 3.1 — Service health.** For each service (api, listener, frontend, db): up/down, uptime, restart count. Data from a new lightweight `/ops/health` endpoint that probes the services (and, where available, container status via the Docker socket or a heartbeat table).

**Rule 3.2 — Bot health.** Telegram connection state (from the listener), update processing lag, handler error rate over the last hour.

**Rule 3.3 — Ingestion worker.** Queue depth (pending posts), items processed in the last hour, current rate-limit headroom, AI-provider status (Groq/Gemini/CLIP) and any failover events in the last 24h.

**Rule 3.4 — Schedulers.** For each background job (daily cleanup, star reconciliation, photo refresher): last run time, last success time, last error. Requires a `scheduler_runs` table written by the jobs themselves (instrumentation gap to close — the jobs currently only log).

**Rule 3.5 — Money signals.** Star balance (via `getMyStarBalance`), count of pending/unfulfilled payments (reconciliation gap).

**Rule 3.6 — Freshness.** Health data refreshes automatically (poll interval ≤ 30s). Stale data is labeled with its age, never silently shown as current.

---

## 4. Section 6 — Monetization

### 4.1 Boost pricing (the core)

**Rule 4.1.1 — Prices move from env to database.** `BOOST_PRICE_STARS` becomes a DB table `boost_prices (category, subcategory, price_stars, updated_at, updated_by)`, PK `(category, subcategory)`. `constants.py` values become the **seed defaults** — on startup, any missing rows are seeded from the env defaults (so a fresh deploy starts sensible). `get_boost_price` reads the DB (with a small in-process cache, invalidated on edit). **Admin edits take effect instantly — no restart.**

**Rule 4.1.2 — Full table model.** Every subcategory gets an explicit price (~100 rows). Effective price for an item = `boost_prices[item.subcategory]`; items with no subcategory row fall back to their category row if present, else the `Other` floor. "What you see is what it costs" — no inheritance logic beyond the documented fallback chain.

**Rule 4.1.3 — The pricing table UI.** Grouped by category (accordion). Each row: `Subcategory | Price (Stars) | Active boosts | Boosts this week`. Inline price edit with confirm. Bulk actions: **"Set category"** (one price → all its subcategories), **"+N%" across category**, **"Reset to floor"**.

**Rule 4.1.4 — Demand context.** Active-boost counts and this-week boost counts per category/subcategory come from the `boosts` table joined to items. This is the data-driven manual pricing loop (monetization.md Rule 2.3): see under-priced demand, adjust, instantly live.

**Rule 4.1.5 — Price changes never disturb in-flight purchases.** An invoice is fixed at creation (the payload carries the order id, not the price). Editing a price mid-flight affects only new invoices. No refunds or adjustments for already-paid boosts.

### 4.2 Feature toggles

**Rule 4.2.1 — Instant kill switches.** `MONETIZATION_ENABLED` and per-feature toggles (boost purchases, subscription purchases, credit boosts) become `admin_settings` DB flags. Flipping them takes effect immediately — no env edit, no restart. Current env-based behavior (503s + UI hide) is preserved exactly; only the source of the flag changes.

### 4.3 Subscription settings

**Rule 4.3.1 — Visible and editable:** alerts-only price, all-in-one price, extra-alert allowance, monthly boost credit — as live DB settings with the same instant-effect rule.

### 4.4 Revenue dashboard

**Rule 4.4.1 —** Stars earned (from the `getStarTransactions` ledger), active subscriptions, active boosts, expiring-soon list (next 24h). All real data, no estimates.

### 4.5 Boost moderation

**Rule 4.5.1 —** Curated list of active boosts: item, channel, source (paid/credit), ends-at, price paid. Action: **end boost early** (for abuse/errors), which writes an audit row and invokes the existing `end_boost_for_item` behavior. No refund logic in v1 (monetization.md Rule 6.1: no refunds).

### 4.6 Test tools (shared with Section 10)

**Rule 4.6.1 —** Grant a test boost to an item, grant/revoke a test subscription for a user — one-click, clearly labeled "TEST", audit-logged. This replaces the sqladmin row-insert dance from UAT.

---

## 5. Section 8 — Settings & Flags

**Rule 5.1 — The registry.** Every operational knob: monetization flags, alert cap, banner threshold, boost rotation minutes, retention days, LLM fail-open policy — surfaced by the settings registry (§1.5). Each shows: description, live value, source (db/env).

**Rule 5.2 — Edit rules.** DB-sourced knobs are editable with confirm + audit. Env-sourced knobs are shown read-only with "requires deploy to change" labeling — the console never lies about whether an edit took effect.

**Rule 5.3 — Effective-config view.** One screen: the full current configuration, DB overrides on top of env defaults, source-labeled. This is the "what is actually live right now" answer.

---

## 6. Section 9 — Audit

**Rule 6.1 —** A read-only list of every console mutation: admin, action, section, entity, before/after, timestamp. Filterable by section and admin. No edits, no deletes, no export in v1 (export is a future nicety).

---

## 7. Section 7 — Payments

**Rule 7.1 —** Star transaction ledger (from `getStarTransactions`), current balance, last reconciliation run + result.

**Rule 7.2 — Reconciliation run-now.** Button to trigger the existing daily reconciliation immediately, with its result displayed.

**Rule 7.3 — Refunds.** List recent payments; refund action via `refundStarPayment` for a specific `telegram_payment_charge_id`, with confirm + audit. Marked as an operator tool with a warning dialog.

---

## 8. Section 10 — Support Toolkit

**Rule 8.1 — Test boosts & subscriptions.** One-click grant (clearly labeled TEST, audit-logged). No payment required.

**Rule 8.2 — Payment-webhook simulator.** Trigger a synthetic `successful_payment` fulfillment for a given charge id and payload — the exact flow the listener would call, without Telegram. This replaces hours of sqladmin fiddling and is the primary UAT tool for the monetization stack.

**Rule 8.3 — Deep-link generator.** Build Mini App links to any item/channel (`/stores/{channelId}/{itemId}`, item pages) for support handoffs.

**Rule 8.4 — Safety.** All simulator/grant actions require explicit confirmation and write audit rows; they never touch real Telegram payments.

---

## 9. Instrumentation gaps (must be closed for Section 1)

- `scheduler_runs` table — the daily jobs write last-run/last-success/last-error (cleanup, reconciliation, photo refresher)
- Listener heartbeat — a periodic row/endpoint the Overview can read
- Worker queue depth — the ingestion worker reports its pending count

---

## 10. Deferred sections (2–5) — boundary contract

Built only when operational pain is real, and ONLY as action centers per Rule 2.1. No tickets are opened until the need exists. The nav stubs stay until then.

---

## 11. Behavior Doc Cross-References

- Monetization pricing/toggles/revenue rules: `monetization.md` (Rules 1.3, 2.2, 2.3 amended by §4 of this doc — prices are DB-first now)
- Boost lifecycle (end-early moderation): `monetization.md` §6
- Alert cap, banner threshold, retention: `alert-guardrails.md`, `monetization.md` §7
- LLM judge fail rate surfacing: `alert-matching.md` (NB-20 stays open; this console surfaces it)

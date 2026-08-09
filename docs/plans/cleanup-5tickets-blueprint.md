# Cleanup — Five-Ticket Execution Blueprint (TECH-39, NB-17, NB-18, NB-19, NB-20)

**Date:** 2026-08-08
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture
**Branch:** `feat/cleanup-5tickets` (created by @build before step 1; NO intermediate commits — 4 atomic commits on QA approval)

---

## 1. Architecture Context

Five tickets, grouped into four packages. NB-17 + NB-19 are ONE data-flow slice (extraction → storage → display); NB-18 closes as **already-implemented (superseded by TECH-25)** with evidence only; NB-20 is an observability upgrade that changes no user-visible match behavior.

| Package | Tickets | Commit message | Dependency category |
|---|---|---|---|
| 1 | TECH-39 | `refactor: useRefetchOnActivation hook + AddChannelButton dedup (TECH-39)` | Frontend-only, zero runtime-behavior change |
| 2 | NB-17 + NB-19 | `feat: persist and expose item condition/location; gallery consistency (NB-17/19)` | Backend additive columns + frontend display; depends on nothing |
| 3 | NB-18 | `docs: close NB-18 as superseded by TECH-25 (evidence)` | Docs-only (ledger) |
| 4 | NB-20 | `feat: LLM judge tri-state — distinguish fail-open from rejection (NB-20)` | Backend; isolated seam |

**Package 3 has no code.** The deliverable is a verification checklist (below) + the ledger update. If verification had found a residual gap, it would be folded here — it did not (evidence in §5.3 and §6.3).

---

## 2. The New Interfaces

### Package 1 — `useRefetchOnActivation` + `AddChannelButton`

**Hook contract** — new file `frontend/src/hooks/useRefetchOnActivation.js`:

- Exports `useRefetchOnActivation(active, fn)` — a thin wrapper over a single effect: whenever `active` becomes truthy, call `fn()`; hidden tabs never fetch.
- Exact deps semantics: `[active, fn]`. Consequences the contract documents:
  - **fn MUST be stable** — call sites pass a `useCallback` (or a hook-returned stable function). If `fn` changes identity while `active` is true, the effect re-runs and calls `fn` again — that is the intended "deps changed" behavior, not a bug, but it means the call site controls refetch frequency through `fn`'s identity.
  - **Mount-with-active fetches once** — mount with `active=true` runs the effect on first render, calling `fn()` once (identical to the current `if (active) getStatus()` effects).
  - **Hidden → active transition refetches** — flipping `active` false→true calls `fn()`.
  - **Active→active re-renders do not refetch** — while `fn` identity is stable.
- Implementation shape: import `useEffect` from `react`; return nothing.

**CTA component contract** — new file `frontend/src/components/AddChannelButton.jsx`:

- Exports a default component rendering the `<a>` deep-link button to `https://t.me/IndexGebeyaBot?start=addchannel` with `target="_blank"` and `rel="noopener noreferrer"`.
- Props: `label` (string, default `"Add Channel"`) and `className` (string, optional override of the anchor's classes).
- Default classes (preserve exactly, from StoresPage): `flex items-center gap-1.5 px-3 py-2 bg-brand-600 text-white rounded-xl text-xs font-medium hover:bg-brand-700 transition-colors shrink-0`.
- Icon: `PlusCircle` from `lucide-react`, `size={14}`.
- Accessible name must equal the `label` prop so `getByRole('link', { name: ... })` assertions keep resolving.
- Only the ANCHOR is extracted. The surrounding cards (differing containers/copy in StoresPage vs MonetizationHub) stay inline — they are not duplicated fragments.

### Package 2 — Item `condition`/`location` + gallery consistency

**Backend persistence:**
- `Item` (SQLAlchemy) gains two nullable scalar `String` columns, inserted immediately after `specs` (models.py line 208): `condition` and `location`. Additive; no default; NULL means "not extracted".
- No `ItemImage`/`specs` changes — condition/location are scalar columns.

**API surface (architect's locked call — verified viable):**
- `ItemResponse` (schemas.py) gains `condition: Optional[str] = None` and `location: Optional[str] = None`.
- **NOT** on `ItemBase`/`ItemCreate`: the create surface does not exist (verified: `ItemCreate` is defined at schemas.py:68 but has zero usages anywhere in `backend/`; ingestion constructs the ORM directly). Keeping them off `ItemBase` avoids implying an API create path can set them.

**Gallery consistency (the NB-17 fix):**
- Single source of truth: `images` is ALWAYS populated with the full gallery on every item-bearing route; `image_path` stays as the backward-compat thumbnail. This matches the frontend consumer contract (verified — see §6.4).

### Package 3 — (no new interfaces)

### Package 4 — `JudgeVerdict` tri-state + ops observability

**`backend/ai_engine/llm_client.py`:**
- New module-level enum `JudgeVerdict` with exactly three members: `APPROVED`, `REJECTED`, `ERRORED`.
- `verify_match_with_llm(item_title, alert_query, preferences)` — signature unchanged (return type changes from `bool` to `JudgeVerdict`). Exact branch mapping (current lines verified):
  - no API key (line 17-19) → `ERRORED` (today: `True`)
  - 200 + valid JSON + `match: true` (line 106) → `APPROVED`
  - 200 + valid JSON + `match: false` → `REJECTED`
  - 200 + valid JSON + missing `match` key (line 103 `result.get("match", False)`) → **`REJECTED`** — preserve today's fail-closed behavior exactly; NB-20 must not change match outcomes (see §6.2). Document this decision in a comment.
  - 200 + JSON parse failure / non-dict payload → `ERRORED` (today: exception → `True`; same dispatch outcome, better signal)
  - non-200 (line 107-109) → `ERRORED`
  - any exception (line 111-113) → `ERRORED`

**`backend/services/alerting.py`:**
- New module-level observability surface (no DB): `JUDGE_ERROR_COUNT = 0` (int) and `JUDGE_ERROR_LAST_TS = None` (UTC `datetime` or None).
- The judge call site (line 108) becomes a three-way branch:
  - `REJECTED` → log `🛑 LLM Rejected: ...` and `continue` (identical to today's False path).
  - `ERRORED` → log `⚠️ LLM Judge errored — fail-open: ...` (distinct severity), increment `JUDGE_ERROR_COUNT`, set `JUDGE_ERROR_LAST_TS = datetime.now(timezone.utc)`, then FALL THROUGH to dispatch (Rule 5.2 fail-open — identical dispatch outcome to today's True path).
  - `APPROVED` → log `✅ LLM Approved: ...` (the existing line 114) and proceed.
- Use enum identity (`is`) comparisons against `JudgeVerdict` members.

**`backend/api/routes/ops_health.py`** — the `ingestion.ai_providers` signal (lines 186-189, currently `_signal("unavailable", ...)` and literally annotated "NB-20 is the future surface") becomes a real value:

- Shape: `{status: "ok", value: {"llm_judge_error_count": int, "llm_judge_error_last_ts": ISO-string-or-null}, source: "alerting.JUDGE_ERROR_COUNT / JUDGE_ERROR_LAST_TS", note: "LLM judge fail-open observability (NB-20); groq/gemini health probes remain out of scope"}`.
- Module-level import of the two counters from `services.alerting` (plain values — no circular-import risk: alerting imports models/constants/subscriptions, never routes).

---

## 3. Strict Import Map (additive-only, per file)

### Package 1 (frontend)

| File | Adds | Exact import statements |
|---|---|---|
| `frontend/src/hooks/useRefetchOnActivation.js` (NEW) | `useEffect` | `import { useEffect } from 'react'` |
| `frontend/src/pages/AlertsPage.jsx` | the hook | `import { useRefetchOnActivation } from '../hooks/useRefetchOnActivation';` (existing `useEffect` import stays — still used by the lazy-load effect at lines 41-46) |
| `frontend/src/pages/StoresPage.jsx` | the hook; `useCallback` | `import { useRefetchOnActivation } from '../hooks/useRefetchOnActivation';` and add `useCallback` to the existing `react` import on line 1 |
| `frontend/src/components/AddChannelButton.jsx` (NEW) | `PlusCircle` | `import { PlusCircle } from 'lucide-react';` (component uses no other modules) |
| `frontend/src/pages/StoresPage.jsx` | the component | `import AddChannelButton from '../components/AddChannelButton';` |
| `frontend/src/pages/MonetizationHub.jsx` | the component | `import AddChannelButton from '../components/AddChannelButton';` |

Removals: StoresPage/MonetizationHub drop `PlusCircle` from their lucide-react import ONLY if no other usage remains in the file (StoresPage keeps `PlusCircle` — verified unused elsewhere in StoresPage → remove it there; MonetizationHub — verify and remove if unused after extraction).

### Package 2 (backend)

| File | Adds | Exact import statements |
|---|---|---|
| `backend/models.py` | none (columns use existing `Column`, `String` — already imported line 1) | — |
| `backend/main.py` | none (uses existing `text`) | — |
| `backend/api/routes/ingestion.py` | none (constructor args only) | — |
| `backend/schemas.py` | none (`Optional` already imported) | — |
| `backend/services/search.py` | `ItemImage`, `defaultdict` | `from models import ItemImage` and `from collections import defaultdict` |
| `backend/tests/test_item_condition_location.py` (NEW) | per house test pattern | `from models import Item, ItemImage, Channel, User`; `from schemas import ItemResponse`; `from unittest.mock import patch`; route-level tests follow the `test_items_browse.py` TestClient pattern |

### Package 3

| File | Adds |
|---|---|
| `docs/behaviors/pending-behaviors.md` | none (edits the NB-18 entry only) |

### Package 4 (backend)

| File | Adds | Exact import statements |
|---|---|---|
| `backend/ai_engine/llm_client.py` | `Enum` | `from enum import Enum` (module already imports `os, json, logging, httpx`) |
| `backend/services/alerting.py` | `JudgeVerdict` | extend the existing line-12 import: `from ai_engine.llm_client import verify_match_with_llm, JudgeVerdict` |
| `backend/api/routes/ops_health.py` | the two counters | `from services.alerting import JUDGE_ERROR_COUNT, JUDGE_ERROR_LAST_TS` |
| `backend/tests/test_llm_judge.py` (NEW) | per house pattern | `from ai_engine.llm_client import verify_match_with_llm, JudgeVerdict`; `from unittest.mock import patch` |
| `backend/tests/test_alert_pipeline.py` | `JudgeVerdict` | `from ai_engine.llm_client import JudgeVerdict` (for the updated spy) |
| `backend/tests/test_ops_health.py` | none (assertions updated in place) | — |

---

## 4. Execution Steps

### Package 1 — TECH-39 (commit 1)

1. Create `frontend/src/hooks/useRefetchOnActivation.js` per the §2 contract. No other logic in the file.
2. AlertsPage: replace the effect at lines 36-38 with `useRefetchOnActivation(active, getStatus)` placed in the same location. `getStatus` is already a stable `useCallback` (verified useSubscription.js lines 24-50, `[]` deps) — the contract holds without wrapping.
3. StoresPage: replace the effect at lines 33-37 with a wrapped stable callback + the hook:
   - Add `const refetchSubscriptionStatus = useCallback(() => { if (hasBeenFetched) getStatus(); }, [hasBeenFetched, getStatus]);`
   - Add `useRefetchOnActivation(active, refetchSubscriptionStatus)`.
   - **Decision (documented):** the `hasBeenFetched` gate stays at the call site via the wrapper, NOT in the hook signature — the hook stays a one-parameter primitive; the wrapper reproduces the current semantics exactly: effect fires when `hasBeenFetched` flips false→true (wrapper no-ops if hidden, fires if active) and on activation (wrapper fires because the gate is already true). Deps-equivalence verified against the current `[active, hasBeenFetched, getStatus]` effect.
4. Create `frontend/src/components/AddChannelButton.jsx` per the §2 contract.
5. StoresPage: swap the two inline anchors — owner-view CTA (lines 383-391, label "Add Channel") and zero-channel CTA (lines 539-547, label "Add Channel") — for `<AddChannelButton />` with default label. The surrounding `bg-brand-50` cards and their copy stay untouched.
6. MonetizationHub: swap the two inline anchors — Boost tab (lines 142-150, label "Add Channel/Group") and All-in-One tab (lines 326-334, label "Add Channel/Group") — for `<AddChannelButton label="Add Channel/Group" className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white rounded-xl text-xs font-medium hover:bg-brand-700 transition-colors" />` (preserves that site's exact classes). The surrounding gray cards stay untouched.
7. **Locked scope statement (from the architect):** StoresPage (553L) and MonetizationHub (502L) are NOT force-split in this ticket — the CTA dedup + hook extraction are the valuable, low-risk parts; splitting is separate-ticket territory (QA may raise it later). The ledger entry's "file sizes reduced or documented as intentional" acceptance is met by the extraction + this documented decision.
8. Tests per §5.1. Full frontend suite green.

### Package 2 — NB-17 + NB-19 (commit 2)

**Backend:**
1. models.py: add the two columns after `specs` (line 208), before `# Media` comment.
2. main.py: new idempotent migration block following the exact house pattern (see TECH-21/22 blocks, main.py lines 152-194 — `with engine.begin() as conn:` + `ALTER TABLE items ADD COLUMN IF NOT EXISTS condition VARCHAR` and the same for `location`, wrapped in try/except with a warning log).
3. ingestion.py: in the `Item(...)` constructor (lines 205-220), add `condition=getattr(ext, 'condition', None),` and `location=getattr(ext, 'location', None),`. Verified: `ext` is the DataWrapper over the extraction dict (lines 80-86), and the extraction dict carries `condition`/`location` per prompts.py lines 87-88 (groq_client.py:63 returns the raw parsed JSON; gemini_client.py:53 likewise). The `getattr` default is the graceful path when the AI omits them.
4. schemas.py: add the two `Optional[str] = None` fields to `ItemResponse` (architect's call — see §2).
5. **The gallery fix** in `services/search.py` — this is the only inconsistent surface (evidence in §6.4):
   - In `_execute_search_sql` (line 14), add `i.condition, i.location,` to the SELECT list (after `i.specs,` line 46) so the manual ItemResponse construction carries them (NB-19's search surface).
   - Add `condition=row.condition, location=row.location,` to the `ItemResponse(...)` constructor (lines 135-154).
   - After the loop, batch-enrich `images`: collect the built item ids; query `ItemImage` rows for all of them in ONE statement; for each item set `images` = its `ItemImage.image_path` list, falling back to `[row.image_path] if row.image_path else []` when an item has no `ItemImage` rows (legacy items). Replace the current line-149 single-image construction (`images=[row.image_path] if row.image_path else []`) with the post-loop enrichment so the scored SQL stays untouched (it is load-bearing).
6. No changes to items.py / feed.py / channels.py item routes — verified they serialize ORM items through `ItemResponse.model_validate`, and the `images` field_validator (schemas.py lines 100-111) extracts every `ItemImage.image_path` from the relationship (handles ORM list; dict/str list items already handled).

**Frontend:**
7. `ItemCard.jsx` — **NO change required** (verified: line 122 renders `{item.condition || 'Used'}`; line 155 renders `{item.location || 'Addis Ababa'}`). The backend slice makes these show real data; document this in the commit message.
8. `ProductPage.jsx` — two minimal additive displays (this page currently renders NEITHER — verified):
   - Location: a small line `📍 {item.location}` inserted in the right-column card directly below the price row (after line 372, before the TECH-22 status badge block at 374). Render it ONLY when `item.location` is truthy (hidden when absent).
   - Condition: a spec-style row/chip at the top of the "Specifications" card (after line 332's heading, before the `Object.entries(parsedSpecs)` grid at 333) — a labeled value row reading `{item.condition || 'Used'}`. Minimal, additive, matches the existing grid styling.
9. Tests per §5.2. Full backend + frontend suites green.

### Package 3 — NB-18 closure (commit 3)

1. Run the §5.3/§6.3 verification checklist; record results in the commit message.
2. Edit `docs/behaviors/pending-behaviors.md` NB-18 entry (line 17-19) to:

   `## NB-18: [CLOSED — superseded by TECH-25] Expired Alerts Are Never Permanently Removed`

   with the body: `*(Closed 2026-08-08. TECH-25 (commit f774c2c) fully covers this: cleanup Phase 4 purges expired/deleted alerts after ALERT_RETENTION_DAYS with notification cascade; the expiry gate deactivates expired alerts at match time so matching never loads them; the alerts UI never lists inactive alerts. Evidence: test_tech25.py purge tests. See docs/plans/cleanup-5tickets-blueprint.md §5.3.)*`

3. No code changes. Do NOT mark `[IMPLEMENTED]` — it was superseded, not freshly implemented.

### Package 4 — NB-20 (commit 4)

1. llm_client.py: add `JudgeVerdict` enum + remap the five branches per §2. Keep the existing log lines; add the missing-key REJECTED decision comment.
2. alerting.py: add the two module counters; rewrite the call-site branch per §2 (REJECTED → skip; ERRORED → fail-open + counters + distinct log; APPROVED → proceed).
3. ops_health.py: replace the hardcoded `ai_providers` "unavailable" signal with the real-value signal per §2.
4. Update `backend/tests/test_alert_pipeline.py` judge_spy (lines 109-111) to return `JudgeVerdict.APPROVED` (it currently returns `True` — with enum-identity comparisons it would be treated as a rejection). The line-82 spy (raises) is untouched.
5. Update `backend/tests/test_ops_health.py` (lines 137-144): `ai_providers` now asserts status `"ok"` and `value.llm_judge_error_count` present.
6. New `backend/tests/test_llm_judge.py` per §5.4. Full backend suite green.

---

## 5. Testing Strategy

### 5.1 Package 1 (TECH-39)

New `frontend/src/__tests__/useRefetchOnActivation.test.jsx` (vitest + @testing-library/react `renderHook`/`act`):
- **Mount-active fetches once:** renderHook with `active=true`, stable fn → fn called exactly once.
- **Activation refetches:** start hidden (`active=false`), flip true → second call; flip false→true again → third call.
- **Hidden never fetches:** mount hidden, re-render hidden → zero calls.
- **Stable deps, no loop:** re-render with same `active` and same fn identity → no additional calls; changing fn identity while active → one additional call (documents the contract).

Existing tests stay green (the preservation contract):
- `AlertsPage.test.jsx` "stale allowance is replaced when the tab is hidden and shown again" (line 408) — exact fetch-count assertions (0 → 1 → 1 → 2) must pass unchanged.
- `StoresPage.test.jsx` "does not fetch status while the tab is hidden; refetches on activation" (line 225) — must pass unchanged (proves the wrapper preserves the `hasBeenFetched` gate).
- CTA tests pass unchanged: `StoresPage.test.jsx` lines 192-218 and `MonetizationHub.test.jsx` lines 423-447 assert `getByRole('link', {name: 'Add Channel'/'Add Channel/Group'})` + href — preserved by the label/className props.
- Add explicit `AddChannelButton.test.jsx` cases: default label + href + target/rel; custom label; custom className passthrough.

### 5.2 Package 2 (NB-17/19)

New `backend/tests/test_item_condition_location.py` (house patterns: `db_session` fixture from conftest; TestClient pattern from test_items_browse.py for routes; ingestion route driven with patched `ai_engine.extract_product_info` + `vectorize_image` like test_ingestion_dedup.py):
- **Ingestion persists condition/location:** patched extraction dict carrying `condition: "Used"`, `location: "Addis Ababa, Bole"` → POST the parse route → Item row has both; second case: extraction dict WITHOUT the keys → both NULL (graceful).
- **ItemResponse serializes them:** `ItemResponse.model_validate(orm_item)` → fields present and correct.
- **Search surface carries them + full gallery:** seed item with `image_path` + 2 `ItemImage` rows → `perform_hybrid_search` response items have `images` == the 2 gallery paths (in order) and correct `condition`/`location`; legacy item (no ItemImage rows) → `images == [image_path]`.
- **Gallery consistency parametrized over routes:** seed one item (2 gallery images). For each of `GET /items/recent`, `GET /items/browse?category=...`, `GET /items/{id}`, `GET /search?q=...` assert every returned item's `images` equals the full gallery (not the 1-image singleton). (`/items/{id}/related` and `/items/foryou` are exercised via their service seams; their serialization path is the same ORM route as recent/browse — cover if cheap, otherwise note in the test file.)

Frontend:
- `ItemCard.test.jsx`: add a case rendering `condition: 'New'` from the API → badge shows "New" (not the 'Used' fallback); `location: 'Bole'` → line shows "Bole".
- `ProductPage.test.jsx`: item with `location` → the `📍 ...` line renders; item without `location` → hidden; condition row renders `item.condition` and falls back to "Used".

### 5.3 Package 3 (NB-18 evidence — no new tests)

Verification checklist (all pre-verified; @build re-runs and records):
1. `services/cleanup.py` Phase 4 (lines 135-164): purges `deleted_at < now-ALERT_RETENTION_DAYS` OR `expires_at < now-ALERT_RETENTION_DAYS`, guarded by `ALERT_RETENTION_DAYS > 0`; notifications cascade via the TECH-25 FK.
2. Matching never loads expired alerts: alerting.py line 62 loads `is_active == True` only, and the expiry gate (lines 154-166) deactivates expired alerts at match time.
3. UI never shows them: `list_my_alerts` (alerts.py lines 76-82) filters `is_active == True`.
4. Tests proving it: `test_tech25.py` — `test_purge_skips_active_alerts`, `test_purge_protects_paused_alerts`, `test_purge_removes_deleted_alerts_after_retention`, `test_purge_removes_expired_alerts_after_retention`, `test_retention_disabled_at_zero`, plus `test_pending_notifications_never_purged`.
5. NB-18's three acceptance criteria map 1:1: "periodic cleanup or query filter" → Phase 4 + is_active-only matching; "older than threshold permanently deleted" → ALERT_RETENTION_DAYS purge; "matching engine does not degrade" → both of the above.
6. Residual-gap check: purged alerts' notifications cascade (handled); no UI dead-row surface (alerts.py:82); **no residual gap → NB-18 closes as superseded, no new mini-ticket.**

### 5.4 Package 4 (NB-20)

New `backend/tests/test_llm_judge.py` (mock `httpx.Client` — patch `ai_engine.llm_client.httpx.Client`; no-key case via monkeypatching `ai_engine.llm_client.GROQ_API_KEY` — note it is captured at module import, so patch the module attribute, not the env var):
- 200 + `{"match": true}` → APPROVED
- 200 + `{"match": false}` → REJECTED
- 200 + `{}` (missing key) → REJECTED (preserves today's fail-closed outcome)
- 200 + invalid JSON body → ERRORED
- 500 → ERRORED
- no key → ERRORED
- transport exception/timeout → ERRORED

Orchestrator behavior (extend test_alert_pipeline.py or in the new file, patching `services.alerting.verify_match_with_llm`):
- REJECTED → no Notification created; counters unchanged.
- ERRORED → Notification created (fail-open) AND `JUDGE_ERROR_COUNT` incremented AND `JUDGE_ERROR_LAST_TS` set.
- APPROVED → Notification created; counters unchanged.
- Update the existing `test_hybrid_ring_without_speed_pass_invokes_judge` spy to return `JudgeVerdict.APPROVED`.

Ops health: `test_ops_health.py` updated — `ingestion.ai_providers` is `"ok"` with `value.llm_judge_error_count` an int; the `sources_are_never_fabricated` test updated to match the new shape.

---

## 6. Rollout Notes

### 6.1 Migration & data backfill (Package 2)
- Two additive nullable columns (`condition VARCHAR`, `location VARCHAR`) via the idempotent startup migration — safe on fresh and legacy DBs; no backfill. Existing rows keep NULL.
- Graceful degradation verified: ItemCard badge falls back to `'Used'` (line 122); ItemCard location line falls back to `'Addis Ababa'` (line 155, existing design); the NEW ProductPage location line is hidden when absent; search surfaces carry NULL until re-ingestion. New extractions populate real values from day one.

### 6.2 Judge tri-state behavior change (Package 4)
- **No user-visible match-outcome change:** REJECTED keeps skipping (today's False), ERRORED keeps fail-opening (today's True), APPROVED dispatches (today's True). The single documented exception is the missing-`match`-key case, which today fail-CLOSES (False) and is mapped to REJECTED to preserve outcomes. Only logging granularity and the ops counter change.
- The ops Overview gains a real `llm_judge_error_count` on the existing `ai_providers` signal (which was pre-annotated as the NB-20 surface) — no frontend OpsOverview change required unless it already renders `value` generically (it renders signal values generically — no change).
- Note for ops: the counter is process-local (resets on API restart); acceptable for v1 observability per the architect — no DB table.

### 6.3 Ledger wording (Package 3)
- NB-18: `[CLOSED — superseded by TECH-25]` (NOT `[IMPLEMENTED]` — supersession, not fresh implementation). Exact wording in §4 Package 3 step 2.

### 6.4 Verification evidence (drift/context the builder relies on)
- **NB-17 gallery inconsistency (confirmed exactly as the original ledger states):** `services/search.py` line 149 — `images=[row.image_path] if row.image_path else []` — affects `/search` and `/items/{id}/related` (both route through `_execute_search_sql`). All other item routes (`/items/recent` line 86-96, `/items/browse` 106-153, `/items/{id}` 156-188, `/items/foryou` via `build_feed`, `/channels/{id}/items`) serialize ORM items and get the full gallery through the `images` field_validator. Frontend consumers all prefer `images` over `image_path` (ProductPage 69-72/320, ItemCard 92, ProductEditPanel 322, ProductGrid/LandingPage) — the API-side fix is the correct end of the seam.
- **NB-19 (frontend side):** ItemCard already renders condition (line 122) and location (line 155); ProductModal renders both (lines 55, 63); ProductPage renders neither — the ticket's exact complaint.
- **NB-20 callers:** production caller is exactly one — `alerting.py` line 108. Tests mock the name at the `services.alerting` seam (test_alert_pipeline.py 82, 116). Return-type change is safe with the two test updates in §5.4.
- **Ops signal shape:** `_signal(status, value, source, note)` dict; `ingestion.ai_providers` currently `unavailable`/None/None with the NB-20 note (ops_health.py 186-189).

---

## 7. Acceptance Gates (QA)

1. Package 1: hook + AddChannelButton unit tests pass; AlertsPage/StoresPage activation tests unchanged-green; both pages wired to the hook; 4 CTA sites render via the component with preserved href/classes.
2. Package 2: ingestion persists condition/location (incl. missing-key NULL path); ItemResponse exposes them; search/related responses carry full gallery + condition/location; parametrized route consistency test green; ProductPage renders location (conditional) + condition.
3. Package 3: ledger updated; evidence checklist recorded in the commit message; no code delta.
4. Package 4: judge tri-state unit tests green; orchestrator per-verdict tests green; ops health `ai_providers` carries the counter; full backend regression green (116 baseline + new tests); full frontend suite green.

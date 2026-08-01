# Architecture Deepening Blueprint — Alert Matching Pipeline

**Date:** 2026-08-01
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture (LANGUAGE.md vocabulary in force)

**Goal:** Give the alert matching pipeline a single, explicit set of match semantics — containment-based Speed Pass living only in `backend/ai_engine/matcher.py`, an explicit deterministic-match signal on `MatchResult`, search configuration relocated to its home module `backend/constants.py`, and the dead alpha matcher deleted — so the 3-stage orchestration in `backend/services/alerting.py` hides the whole pipeline behind an unchanged external interface.

---

## 1. Architecture Context

### Modules involved

| Module | File | Current state |
|--------|------|---------------|
| `matcher.py` | `backend/ai_engine/matcher.py` (96 lines) | Match semantics: `MatchTier`, `MatchResult`, `normalize_string()`, `cosine_similarity()`, `evaluate_match()` — plus 3 misplaced search-config constants. |
| `alerting.py` | `backend/services/alerting.py` (325 lines) | Deep orchestrator `process_new_item()` (226-line monolith, graph degree 17) + `create_alert()` + private helpers `_normalize`, `_create_system_notification`, `_dispatch_notification`. |
| `constants.py` | `backend/constants.py` (73 lines) | Established configuration home (`_get_config` guardrail wrapper). |
| `search.py` | `backend/services/search.py` (209 lines) | Hybrid search; consumes the 3 search constants from the wrong module. |
| `alerts.py` | `backend/services/alerts.py` (49 lines) | Dead alpha matcher; zero incoming graph edges; zero callers. |
| `llm_client.py` | `backend/ai_engine/llm_client.py` (113 lines) | True-external LLM judge `verify_match_with_llm(item_title, alert_query, preferences) -> bool`; fail-open. |

### The friction being solved (four defects)

1. **Divergent duplicated Speed Pass semantics.** `alerting.py` defines `_normalize()` (lines 25–31) byte-identical to `matcher.normalize_string()` (lines 42–46). Worse, `process_new_item()` Stage 1 uses `norm_query == norm_title` (exact equality) while `evaluate_match()` uses `norm_query in norm_title` (containment). `docs/behaviors/alert-matching.md` Rule 3.1 (lines 42–45) mandates **containment** ("iphone13" within "iphone13promax256gb") and line 50 states the consequence: Speed Pass skips Stage 2 and Stage 3 entirely. Today, containment-only matches fall through to Stage 2, earn BULLSEYE 1.0 from the matcher's speed pass, then **still invoke the LLM judge** — a wasted LLM call and a risk of false rejection of a deterministic match. The interface of `evaluate_match` hides whether a match is deterministic — callers cannot tell.
2. **Dead alpha matcher.** `services/alerts.py::check_alerts()` references `alert.search_query`, a field that does not exist on the current `Alert` model (`query_text` is the real field). Zero callers anywhere (repo-wide grep confirms only self-references; graph shows zero incoming edges). It fails the deletion test — delete it entirely.
3. **Misplaced search config.** `matcher.py` lines 14–17 define `SEMANTIC_WEIGHT`, `LEXICAL_WEIGHT`, `DEFAULT_RESULT_LIMIT` (with a "⚠️ RESTORED CONSTANTS (Required by search.py)" comment) consumed by `search.py` lines 91–92, 152, 197. Search configuration living inside the alert matcher module is a wrong seam — config belongs in `constants.py`, the established config home.
4. **No locality for deterministic-match detection.** Match decisions are inferred from the `reason` string ("Speed Pass (Exact Normalized Match)") instead of an explicit signal.

### Dependency categories (DEEPENING.md)

| Target | Category | Strategy |
|--------|----------|----------|
| `matcher.py` | **In-process** (pure computation: `re`, `numpy`, `difflib`, in-memory) | Always deepenable. Merge the Speed Pass semantics here as the single home; test through `evaluate_match` directly. No adapter needed. |
| `alerting.py` | **Local-substitutable** (SQLAlchemy `Session`) | Deepen the orchestrator with **internal seams only** (private helpers, not exported). Test across the external interface `process_new_item(db, item_id)` with the isolated test DB stand-in (`suq_test_db`, wired by `backend/tests/conftest.py`). No port at the external interface. |
| `verify_match_with_llm` | **True external** (Groq HTTP) | Already an injected port at the seam — `alerting.py` imports the name at module level and tests mock `services.alerting.verify_match_with_llm`. Two adapters exist (production HTTP, test mock) → real seam already in the right place. **No new seam; keep as-is.** |

---

## 2. The New Interfaces

### A. `backend/ai_engine/matcher.py` — single home of match semantics

`MatchResult.__init__` gains one optional constructor parameter:

```python
def __init__(self, tier: MatchTier, score: float, reason: str, speed_pass: bool = False):
```

- **Attribute:** `self.speed_pass` — explicit deterministic-match signal.
- **Backward compatible:** existing callers that construct `MatchResult(tier, score, reason)` positionally keep working — the only external constructor today is `backend/tests/test_tech20.py:487` (`MatchResult(MatchTier.RING, 0.65, "Mock Ring")`); `backend/debug_alerts.py` only calls `evaluate_match`, never constructs.
- **Invariant (must hold for every return path):** `speed_pass=True` ⟹ `tier == MatchTier.BULLSEYE and score == 1.0`. All other returns carry `speed_pass=False` (the default).

`evaluate_match()` keeps its exact signature and ordering:

```python
def evaluate_match(item_vector, alert_vector, item_price, alert_max_price, item_title, alert_query_text=None) -> MatchResult
```

- The containment speed-pass branch (currently lines 76–77: `len(norm_query) > 3 and norm_query in norm_title`) returns `MatchResult(MatchTier.BULLSEYE, 1.0, "Speed Pass (Exact Normalized Match)", speed_pass=True)`.
- Price hard filter, hybrid score, and tier classification are untouched.

**Exports unchanged:** `normalize_string`, `cosine_similarity`, `MatchTier`, `MatchResult`, `evaluate_match` all remain exported from this module. `SEMANTIC_WEIGHT`, `LEXICAL_WEIGHT`, `DEFAULT_RESULT_LIMIT` are **no longer exported here** (see C).

**Usage example (what callers gain):** a caller can now branch on the signal instead of parsing the reason string — "if `not result.speed_pass`: the match is probabilistic, ask the judge; else the match is deterministic, dispatch immediately." `alerting.py` is the only consumer that branches; `debug_alerts.py` and the search modules are unaffected.

**What the implementation hides behind the seam:** normalization (junk-stripping), the >3-char short-query protection (behavior doc Rule 3.2), containment semantics (Rule 3.1), the deterministic signal, and the tier classification — all in one place (**locality**).

### B. `backend/services/alerting.py` — the deep orchestrator, internal seams only

**External interface UNCHANGED** (callers `backend/api/routes/ingestion.py::parse_telegram_post`, `backend/api/routes/items.py::update_item`, `backend/services/item_status.py::update_item`, and the test suite cross it):

```python
def process_new_item(db: Session, item_id: int) -> None
def create_alert(db: Session, user: User, query_text: str, max_price: Optional[float], preferences: Dict) -> Alert
```

**Per-alert flow inside `process_new_item` (the new orchestration):**

1. **Pre-check gates** — private helper `_precheck_gates(db, alert, item, now_utc) -> bool` (True = skip this alert). Reproduces today's expiry gate (deactivate + `_create_system_notification` with `system_expiry` DM + logs) and price gate (logs, no-price pass) exactly. *Note: the session is required because the expiry branch writes the system DM; the locked signature `_precheck_gates(alert, item, now_utc)` was amended with `db` as first parameter — see drift report.*
2. **Single matching computation** — exactly one `evaluate_match(item_vector=item_vec, alert_vector=alert_vec, item_price=item.price, alert_max_price=alert.max_price, item_title=item.title, alert_query_text=alert.query_text)` call per alert. `evaluate_match` is now the ONLY matching computation in the pipeline; the Stage-1 identity branch and `_normalize` are gone.
3. **Miss gate** — `result.tier == MatchTier.MISS` → log and `continue`.
4. **Conditional judge** — if `not result.speed_pass`: load `preferences = json.loads(alert.preferences) if alert.preferences else {}`, invoke `verify_match_with_llm(item.title, alert.query_text, preferences)`, and on rejection log and `continue`. If `result.speed_pass`: **skip the judge entirely** (the intended behavior change).
5. **Dispatch decision** — private helper `_dispatch_decision(result, alert) -> bool`: BULLSEYE always dispatches and updates `best_opportunity_score` (high water mark) when higher; RING dispatches only when `result.score >= alert.best_opportunity_score - RING_TOLERANCE`.
6. **Guardrails** — private helper `_apply_guardrails(db, alert, item, result, now_utc, should_notify) -> bool`: ring-only throttle against `NOTIFICATION_THROTTLE_SECONDS` and `alert.last_triggered_at` (bullseye bypasses), then dedup suppression (dedup-replacement channel-hour rule via `Notification`/`Item`; normal same-alert-same-item rule). Returns the final decision.
7. **Dispatch + counters + auto-pause** — on final `should_notify`: increment `matches_found`, log "MATCH CONFIRMED" with `result.tier.value`, set `alert.last_triggered_at = now_utc`, call `_dispatch_notification(db, alert.user_id, alert.id, item, result)`, then private helper `_apply_auto_pause(db, alert, item)` — match counters (skipped for dedup replacements), `bullseye_matches` increment, bullseye-limit pause (priority) then total-limit pause, each with its `system_pause` DM via `_create_system_notification`.

**Rules for the private (internal) seams:** they are NOT exported, NOT imported by tests, and NOT named in the external interface. Keep their boundaries minimal; the observable behavior of `process_new_item` must be identical to today's EXCEPT for the intended fix in step 4. Preserve all existing log statements and their messages. `_create_system_notification` and `_dispatch_notification` remain as-is. The dead `tier_value` fallback literal `'SPEED_PASS'` (lines 197, 240 — already unreachable, since `result` was always assigned) is dropped; `tier_value = result.tier.value` is always valid under the new flow.

**What the implementation hides behind the seam (leverage):** the entire pipeline — gates, single match, conditional judge, dispatch decision, guardrails, counters, auto-pause — sits behind the two-function external interface. Callers and tests exercise the whole pipeline by calling `process_new_item(db, item_id)` with a real Session (**the interface is the test surface**).

### C. `backend/constants.py` — configuration home

Add three constants in a new "--- Search ---" group, using the established `_get_config` guardrail pattern (defaults and env-var names identical to today's matcher.py values):

```python
SEMANTIC_WEIGHT: float = _get_config("SEARCH_SEMANTIC_WEIGHT", 0.6, float)
LEXICAL_WEIGHT: float = _get_config("SEARCH_LEXICAL_WEIGHT", 0.4, float)
DEFAULT_RESULT_LIMIT: int = _get_config("SEARCH_RESULT_LIMIT", 20, int)
```

Update the module docstring's "Consumed by" list to add `- backend/services/search.py` (the existing `backend/ai_engine/matcher.py` entry stays valid — matcher still consumes the tier thresholds). No new imports: `os`, `logging`, `typing.Any/Union`, `_get_config` are already present.

### D. `backend/services/search.py`

One import-line change only (see §3). No other edits; the three constants are consumed identically at lines 91–92, 152, 197.

### E. `backend/services/alerts.py` — deleted

The module fails the deletion test: it hides nothing, has no callers, and references a nonexistent model field. Delete the entire file.

---

## 3. Strict Import Map

| File | Removed | Added | Kept |
|------|---------|-------|------|
| `matcher.py` | `import os` (line 1 — unused after the constants move); the 3 search-constant definitions (lines 14–17) | — (plus `speed_pass: bool = False` parameter on `MatchResult.__init__`) | `import re`, `import numpy as np`, `from enum import Enum`, `from typing import List, Dict, Optional, Tuple`, `from difflib import SequenceMatcher`, `from constants import TIER_1_THRESHOLD, TIER_2_THRESHOLD` |
| `alerting.py` | `import re` (line 3 — only used by `_normalize`); `_normalize` (lines 25–31); STAGE-1 block (lines 117–146, incl. the `else:` header at 145 and its log at 146); lazy `from models import Notification as Notif, Item as Itm` (line 213); `'SPEED_PASS'` fallback literals (lines 197, 240) | — (module-level `Notification`/`Item` already imported on line 10 — reuse them, drop the aliases) | lines 1–2, 4–21 exactly as today, minus line 3: `import json`, `import logging`, `from datetime import datetime, timedelta, timezone`, `from sqlalchemy.orm import Session`, `from sqlalchemy import select, func`, `from typing import List, Dict, Optional`, `import numpy as np`, `from models import Alert, Item, User, Notification`, `from ai_engine.matcher import evaluate_match, MatchTier`, `from ai_engine.vector_client import vectorize_text`, `from ai_engine.llm_client import verify_match_with_llm`, and the `from constants import (...)` block with all six names |
| `constants.py` | — | `SEMANTIC_WEIGHT`, `LEXICAL_WEIGHT`, `DEFAULT_RESULT_LIMIT` (see §2C) + docstring line | everything existing |
| `search.py` | `from ai_engine.matcher import SEMANTIC_WEIGHT, LEXICAL_WEIGHT, DEFAULT_RESULT_LIMIT` (line 12) | `from constants import SEMANTIC_WEIGHT, LEXICAL_WEIGHT, DEFAULT_RESULT_LIMIT` (same position, line 12) | everything else |
| `services/alerts.py` | entire file | — | — |

**CRITICAL patch-target preservation (test_tech20.py compatibility):** these names MUST keep resolving as module-level names in `services.alerting` — no renaming, no late/conditional imports:

- `services.alerting.evaluate_match` (patched at test_tech20.py:490)
- `services.alerting.NOTIFICATION_THROTTLE_SECONDS` (patched at test_tech20.py:491, 588)
- `services.alerting.MAX_BULLSEYE_BEFORE_PAUSE` (patched at test_tech20.py:673, 763)
- `services.alerting.MAX_MATCHES_BEFORE_PAUSE` (patched at test_tech20.py:762)

**New test module `backend/tests/test_alert_pipeline.py` — exact imports required:**

```python
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import select, func
from models import Alert, Item, User, Channel, Notification
from services.alerting import process_new_item
from ai_engine.matcher import MatchTier, MatchResult
from ai_engine.vector_client import vectorize_text
```

(The test suite's `conftest.py` puts `backend/` on `sys.path`, so top-level absolute imports are the repo convention. The `db_session` fixture from `conftest.py` provides a fresh truncated schema against the isolated `suq_test_db` — use it; it is the modern house pattern, already used by `test_auth.py`, `test_owner_dm.py`, `test_item_status.py`.)

---

## 4. Execution Steps

**Step 0 — Branch.** Create and switch to a new feature branch (e.g., `arch/alert-pipeline-deepening`) before writing any code. No intermediate commits; only the final atomic commit at Step 12, and only after @qa approval.

**Step 1 — Delete the dead module.** Delete `backend/services/alerts.py`. Nothing imports it (verified: only self-references; graph shows zero incoming edges). Do not create a replacement.

**Step 2 — Edit `backend/constants.py`.** Add the three search constants (§2C) in a new "--- Search ---" section after the existing "--- Matching ---" group, and add `- backend/services/search.py` to the docstring's "Consumed by" list. Do not touch anything else.

**Step 3 — Edit `backend/ai_engine/matcher.py`.**
- Remove `import os` (line 1) and the three search-constant definitions + their "RESTORED CONSTANTS" comment (lines 10–17).
- Add `speed_pass: bool = False` as the final parameter of `MatchResult.__init__`; assign `self.speed_pass = speed_pass`.
- In `evaluate_match`, the containment speed-pass return (line 77) passes `speed_pass=True`. All other `MatchResult` returns keep the default (False).
- Keep `normalize_string`, `cosine_similarity`, `MatchTier`, `evaluate_match` exactly as-is.

**Step 4 — Edit `backend/services/search.py`.** Swap the line-12 import per §3. Nothing else changes.

**Step 5 — Edit `backend/services/alerting.py`.**
- Remove `import re` (line 3); remove `_normalize` (lines 25–31); remove the STAGE-1 identity-check block (lines 117–146), leaving the stage-2 body (vector prep at 111–115 stays; MISS gate, judge, dispatch decision, guardrails, counters, auto-pause remain).
- Restructure the per-alert loop per §2B steps 1–7, adding the private helpers `_precheck_gates(db, alert, item, now_utc)`, `_dispatch_decision(result, alert)`, `_apply_guardrails(db, alert, item, result, now_utc, should_notify)`, `_apply_auto_pause(db, alert, item)` with the exact responsibilities listed in §2B.
- **Behavior-change callout (QA grades this):** containment speed passes now skip the LLM judge — aligning with `docs/behaviors/alert-matching.md` Rule 3.1 (lines 42–45) and its "Consequence of Speed Pass" clause (line 50: skip Stage 2 and Stage 3 entirely). Previously a containment match ran through stage 2, earned BULLSEYE 1.0, and still invoked the judge. Everything else in `process_new_item` must be observably identical to today.
- Move the lazy `from models import Notification as Notif, Item as Itm` out of the dedup branch (line 213) by reusing the module-level `Notification` and `Item` (drop the `Notif`/`Itm` aliases).
- Keep the module-level import block exactly as mapped in §3 — patch targets MUST keep resolving.
- Keep `create_alert`, `_create_system_notification`, `_dispatch_notification`, the outer try/except with its "❌ Alert Orchestrator Failed" log, and the final `db.commit()` + "🏁 Item Processing Complete" log unchanged.

**Step 6 — Create `backend/tests/test_alert_pipeline.py`** with the imports in §3, using the `db_session` fixture, and the following test coverage (interface-level first, unit-level second):

- *Interface tests through `process_new_item(db, item_id)` (the test surface):*
  - **a. Containment speed pass skips the judge.** Alert `query_text="iPhone 13"` (vectorized), item title `"iPhone 13 Pro Max 256GB Black"` with price ≤ max_price. Patch `services.alerting.verify_match_with_llm` with a spy whose invocation raises `AssertionError("LLM judge must not be called on speed pass")`. Assert exactly 1 `Notification` is created with `match_tier == "bullseye"` for the alert+item pair.
  - **b. Hybrid match without speed pass invokes the judge.** Patch `services.alerting.evaluate_match` to return `MatchResult(MatchTier.RING, 0.65, "mock", speed_pass=False)`; patch `services.alerting.verify_match_with_llm` with a spy returning `True`. Assert the judge spy was called once and exactly 1 `Notification` is created.
- *Unit tests through `evaluate_match` (empty vectors, `None` prices to bypass the hard filters):*
  - c. Containment: query `"iPhone 13"`, title `"iPhone 13 Pro Max 256GB Black"` → `speed_pass is True`, `tier == MatchTier.BULLSEYE`, `score == 1.0`.
  - d. Exact normalized equality: query `"iPhone 13"`, title `"iPhone 13"` → `speed_pass is True`.
  - e. Short query protection: query `"usb"`, title `"business"` → no speed pass (`speed_pass is False`); with empty vectors the hybrid score lands below TIER_2 → `tier == MatchTier.MISS`.
  - f. Hybrid below TIER_2: unrelated query/title pair → `MatchTier.MISS` with `speed_pass is False`.
- *Backward compatibility:*
  - g. `MatchResult(MatchTier.RING, 0.65, "x").speed_pass is False`.

  No old shallow-module tests need deletion: there are none for `_normalize`/Stage-1 (verified — `test_tech20.py` tests only through `process_new_item`).

**Step 7 — Run the new tests.** `pytest backend/tests/test_alert_pipeline.py -v` (host venv; `conftest.py` redirects to `suq_test_db` at localhost:5433) or in-container `docker compose exec backend pytest tests/test_alert_pipeline.py -v`.

**Step 8 — Regression: `test_tech20.py` must pass UNCHANGED.** `pytest backend/tests/test_tech20.py -v` (same run convention). The patch targets in §3 are the contract; any failure means a patch target broke.

**Step 9 — Full regression.** Run the entire backend suite: `pytest backend/tests/ -q` from the repo root (or `docker compose exec backend pytest tests/ -q` per repo convention). Every test that passed before this change must pass unchanged.

**Step 10 — Verification commands.**
- Compile check (in the backend venv/container — the host python lacks numpy, so do NOT run this on the bare host; the repo's import convention is top-level, not `backend.`-prefixed):
  - `cd backend && python -c "import services.alerting, ai_engine.matcher, services.search, constants; print('OK')"` — or `docker compose exec backend python -c "import services.alerting, ai_engine.matcher, services.search, constants; print('OK')"`.
- Grep assertions (must return nothing):
  - `grep -rn "_normalize" backend/` — no `_normalize` remains.
  - `grep -rn "services.alerts\|check_alerts" backend/ listener/` — no imports/callers of the deleted module.
  - `grep -n "SEMANTIC_WEIGHT\|LEXICAL_WEIGHT\|DEFAULT_RESULT_LIMIT" backend/ai_engine/matcher.py` — no search constants remain in matcher.
  - `grep -n "import os" backend/ai_engine/matcher.py` — `os` removed.
  - `grep -rn "from ai_engine.matcher import SEMANTIC_WEIGHT" backend/` — import swap complete in search.py.

**Step 11 — Refresh the graph.** Run `graphify update .` so the AST graph reflects the deepened cluster (AGENTS.md housekeeping).

**Step 12 — Atomic commit (after @qa approval, per AGENTS.md).** Stage only the touched files — `backend/services/alerts.py` (deleted), `backend/constants.py`, `backend/ai_engine/matcher.py`, `backend/services/search.py`, `backend/services/alerting.py`, `backend/tests/test_alert_pipeline.py` (new). Commit message:

```
refactor: deepen alert-matching pipeline — single speed-pass semantics, delete dead alpha matcher, move search config to constants
```

Never push unless explicitly instructed by the human administrator.

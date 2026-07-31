# Architecture Deepening Blueprint — Identity, Owner DMs, Item Status

**Date:** 2026-07-28
**Status:** Immutable — @build executes exactly this
**Skill:** improve-codebase-architecture (LANGUAGE.md vocabulary in force)

---

## 1. Architecture Context

### Friction being solved

Three clusters of shallow modules fail the **deletion test** (complexity reappears across N callers when the module is deleted):

**A. Telegram identity verification — duplicated 4×**
| Location | Module | Interface |
|----------|--------|-----------|
| `backend/api/routes/items.py:28` | `_auth_user_from_init_data(init_data, db)` | parse "user=", get-or-create User, raise 403 |
| `backend/api/routes/channels.py:125` | `_auth_user_from_init_data(init_data, db)` | byte-identical to items.py |
| `backend/api/routes/alerts.py:17` | `get_current_user(init_data, db, x_internal_service)` | same + internal listener bypass |
| `backend/api/routes/reviews.py:20` | `validate_telegram_data(init_data)` | HMAC-SHA256 crypto verification |

Four callers each carry a near-identical ~40-line implementation. The interface a caller must learn (which helper, which error message, whether internal bypass exists) is nearly as complex as the implementation — **shallow**. Three distinct behaviors exist at this seam: external Mini App auth, internal listener bypass, cryptographic review verification.

**B. Owner DM delivery — duplicated 2×**
| Location | Module | Transport |
|----------|--------|-----------|
| `backend/api/routes/items.py:75` | `_send_owner_dm(db, channel_id, message)` | async `httpx.AsyncClient` |
| `backend/services/cleanup.py:30` | `_send_cleanup_dm(channel_id, message)` | sync `httpx.post`, own `SessionLocal` |

Same domain concept (notify the channel owner via Telegram Bot API), two drifted implementations. The seam is **real** — two adapters already exist (async route context, sync background thread).

**C. Item status-transition business rules embedded in route handlers**
`backend/api/routes/items.py` is 484 lines, mixing read endpoints (stats, recent, detail, related) with write endpoints (report, relist, sold, clear-reports, update). The business rules — report threshold check, status flip, edit-history logging, alert re-trigger — have no **locality**; they live inside HTTP handlers and cannot be tested across a seam without spinning up FastAPI.

### Dependency categories (DEEPENING.md)

| Target | Category | Strategy |
|--------|----------|----------|
| A. auth | Local-substitutable | SQLAlchemy `Session` is in-process testable. Merge 4 copies into 1 module; test through its interface with a test DB. |
| B. owner_dm | True external (Telegram Bot API) | Deep module takes `BOT_TOKEN` + transport as injectable; routes use async adapter, cleanup thread uses sync adapter. Two adapters = real seam. |
| C. item_status | Local-substitutable | Business rules over `Session`; alert re-trigger via `process_new_item` (in-process). Test through the interface. |

---

## 2. The New Interfaces

### A. `backend/services/auth.py`

```python
def authenticate(
    init_data: str,
    db: Session,
    x_internal_service: Optional[str] = None,
) -> User:
    """
    Resolve a Telegram identity to a User record.
    - If x_internal_service == "index-listener" and init_data.isdigit(): internal bypass.
    - Else: require "user=" in init_data, parse JSON, get-or-create User.
    Raises HTTPException(403) on failure. Auto-registers unknown users.
    """

def verify_init_data(init_data: str) -> dict:
    """
    HMAC-SHA256 cryptographic verification of Mini App initData (reviews).
    Raises HTTPException(500) if BOT_TOKEN missing, HTTPException(401) on invalid signature.
    Returns the parsed user dict.
    """
```

**Invariants:** identical behavior to the four current implementations. Error messages preserved exactly (alerts.py's "Restricted: Alerts can only be managed from inside the Telegram Mini App." becomes the generic auth failure message only in the non-bypass path — see note in Step 4).

### B. `backend/services/owner_dm.py`

```python
async def send_owner_dm(db: Session, channel_id: int, message: str) -> None:
    """Async adapter — for route handlers. Best-effort, never raises."""

def send_owner_dm_sync(channel_id: int, message: str) -> None:
    """Sync adapter — for the cleanup background thread. Opens its own SessionLocal."""
```

**Invariants:** channel lookup, `registered_by is None` early return, missing `BOT_TOKEN` warning, HTTP-status check, warning-only failure logging. Preserved from both current implementations.

### C. `backend/services/item_status.py`

```python
def report_sold(db: Session, item_id: int, user: User) -> dict:
    """Create SoldReport (one per user per item). At CROWDSOURCE_SOLD_THRESHOLD, flip status to 'reported_sold', notify owner."""

def relist_item(db: Session, item_id: int, user: User) -> dict:
    """Owner-only. Clear SoldReports, reset status to 'active'."""

def mark_sold(db: Session, item_id: int, user: User) -> dict:
    """Owner-only. Set status to 'sold'."""

def clear_reports(db: Session, item_id: int, user: User) -> dict:
    """Owner-only. Delete SoldReports without changing status."""

def update_item(db: Session, item_id: int, user: User, payload: "ItemUpdateRequest") -> Item:
    """Owner-only. Apply field changes, log ItemEdit history, re-trigger process_new_item if price/specs changed."""
```

**Invariants:** ownership checks (user must own the channel via `registered_by`), one-report-per-user-per-item, threshold logic, edit-history one record per changed field. Route handlers become thin adapters — the HTTP surface (request/response schemas) is unchanged.

---

## 3. Strict Import Map

### New module: `backend/services/auth.py`

**Imports required:**
```python
import json
import hmac
import hashlib
import os
from typing import Optional
from urllib.parse import parse_qs, unquote
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from models import User
```

**Moved from `items.py`:** `_auth_user_from_init_data` body (lines 28-73). After move, items.py **removes** imports `parse_qs` and keeps `json` (still used elsewhere? verify — if unused, keep it: strict rule is do not remove fields/imports unless instructed; but these route files will have dead imports after extraction. Instruction to @build: remove ONLY the imports that become unused BY the extraction (parse_qs from items.py, channels.py, alerts.py; hmac/hashlib/unquote from reviews.py), keep everything else).

**Moved from `channels.py`:** `_auth_user_from_init_data` body (lines 125-165). channels.py keeps `Header` import (used for `x_internal_service` param at line 219).

**Moved from `alerts.py`:** `get_current_user` body (lines 17-75). The internal-bypass branch (`is_internal = x_internal_service == "index-listener"`) folds into `authenticate()`'s `x_internal_service` parameter.

**Moved from `reviews.py`:** `validate_telegram_data` body (lines 20-52) and its module-level `BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")` (line 18). reviews.py gains `from services.auth import verify_init_data`.

**Call-site replacements:**
- `items.py`: `from services.auth import authenticate` → replace `_auth_user_from_init_data(init_data, db)` calls with `authenticate(init_data, db)`
- `channels.py`: same import → replace 4 call sites (lines 181, 256, 314, 403)
- `alerts.py`: `from services.auth import authenticate` → replace 5 call sites (lines 89, 138, 151, 190, 242), passing `x_internal_service` through
- `reviews.py`: `from services.auth import verify_init_data` → replace 1 call site (line 29)

### New module: `backend/services/owner_dm.py`

**Imports required:**
```python
import os
import logging
import httpx
from sqlalchemy.orm import Session
from models import Channel
from database import SessionLocal

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logger = logging.getLogger("index_owner_dm")
```

**Moved from `items.py`:** `_send_owner_dm` body (lines 75-99) → becomes `send_owner_dm`. items.py removes now-unused `httpx` import if nothing else uses it (verify: items.py uses httpx only in `_send_owner_dm` — remove). items.py **keeps** `BOT_TOKEN` module-level only if used elsewhere (verify: used only in `_send_owner_dm` — move it to owner_dm.py, remove from items.py).

**Moved from `cleanup.py`:** `_send_cleanup_dm` body (lines 30-57) → becomes `send_owner_dm_sync`. cleanup.py removes `httpx` import and its `BOT_TOKEN` line. cleanup.py keeps `SessionLocal` import only if still used (verify: `run_daily_cleanup` uses it — keep).

**Call-site replacements:**
- `items.py`: `from services.owner_dm import send_owner_dm` → replace `await _send_owner_dm(db, channel_id, msg)` with `await send_owner_dm(db, channel_id, msg)`
- `cleanup.py`: `from services.owner_dm import send_owner_dm_sync` → replace `_send_cleanup_dm(channel_id, message)` calls

### New module: `backend/services/item_status.py`

**Imports required:**
```python
import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from fastapi import HTTPException
from models import Item, Channel, SoldReport, ItemEdit, User
from services.alerting import process_new_item
from constants import CROWDSOURCE_SOLD_THRESHOLD
```

**Moved from `items.py`:** bodies of `report_item_as_sold` (203-276), `relist_item` (277-322), `update_item` (323-428), `mark_item_sold` (429-457), `clear_item_reports` (458-484). The `_send_owner_dm` usage inside these moves to `send_owner_dm` import.

**items.py retains:** `get_stats`, `get_recent_items`, `read_item`, `get_related_items` — the read endpoints — plus thin versions of the write endpoints that delegate to `item_status`. items.py's schemas imports (`SoldReportCreate`, `SoldReportResponse`, `ItemUpdateRequest`, `ItemStatusResponse`) stay (the route signatures need them). items.py keeps `Notification` import ONLY if still used (verify: report flow referenced it — after extraction, check; remove if unused).

**ALERTS NOTE (alerts.py):** the current `get_current_user` raises "Restricted: Alerts can only be managed from inside the Telegram Mini App." for non-internal, non-"user=" inputs. The merged `authenticate()` must preserve this exact message (not the generic "Authentication Failed") so the alert-module behavior is unchanged. Encode as: in the external path, if "user=" not in init_data → raise 403 "Restricted: Alerts can only be managed from inside the Telegram Mini App."; other failures → "Authentication Failed".

---

## 4. Execution Steps

1. **Create `backend/services/auth.py`** — assemble from the 4 sources per the interface spec. Preserve exact error messages (see ALERTS NOTE). Add module docstring explaining the three behaviors at this seam.

2. **Create `backend/services/owner_dm.py`** — assemble `send_owner_dm` (async, from items.py) and `send_owner_dm_sync` (sync, from cleanup.py). Both best-effort with warning-only logging.

3. **Create `backend/services/item_status.py`** — extract the 5 write-endpoint bodies from items.py into the 5 functions. Preserve ALL logic: threshold check, ownership check, one-report-per-user, ItemEdit logging, alert re-trigger. Route handlers delegate.

4. **Modify `backend/api/routes/items.py`** — remove `_auth_user_from_init_data` and `_send_owner_dm`; import `authenticate`, `send_owner_dm`, and the 5 item_status functions; replace bodies of write endpoints with delegation calls; remove dead imports (`parse_qs`, `httpx`, `BOT_TOKEN` if unused).

5. **Modify `backend/api/routes/channels.py`** — remove `_auth_user_from_init_data`; import `authenticate`; replace 4 call sites. Keep `Header` and `parse_qs` ONLY if still used elsewhere (verify).

6. **Modify `backend/api/routes/alerts.py`** — remove `get_current_user`; import `authenticate`; replace 5 call sites passing `x_internal_service`. Remove dead `parse_qs` import if unused.

7. **Modify `backend/api/routes/reviews.py`** — remove `validate_telegram_data` and module-level `BOT_TOKEN`; import `verify_init_data`; replace 1 call site. Remove dead imports (`hmac`, `hashlib`, `unquote`, `os` if only used for BOT_TOKEN).

8. **Modify `backend/services/cleanup.py`** — remove `_send_cleanup_dm`; import `send_owner_dm_sync`; replace call sites. Remove dead `httpx` import and `BOT_TOKEN`.

9. **Tests** — delete old unit tests that target the removed per-file helpers (search for `test_auth`, `test_review_photos` auth-related, `test_tech23` update/relist — those that assert through route behavior stay, they test the interface). Create `backend/tests/test_auth.py` testing through `authenticate()` and `verify_init_data()`: external path, internal bypass path, missing user, crypto pass, crypto fail, missing token. Create `backend/tests/test_owner_dm.py` with a mocked httpx transport (monkeypatch): owner exists + sends, no registered_by + no call, missing token + no call, HTTP error + warning. Create `backend/tests/test_item_status.py` asserting observable outcomes: report threshold flip, one-report-per-user, relist clears, non-owner 403, edit history record count, alert re-trigger on price change.

10. **Regression** — run the full existing suite (`pytest backend/tests/`). All previously-passing tests must pass unchanged (the HTTP surface and schemas are untouched).

11. **Verify** — `python -c "import backend.api.routes.items, backend.api.routes.channels, backend.api.routes.alerts, backend.api.routes.reviews, backend.services.cleanup"` compiles clean; `grep` confirms no duplicate `_auth_user_from_init_data` / `get_current_user` / `validate_telegram_data` / `_send_owner_dm` / `_send_cleanup_dm` remain outside the new modules.

12. **Commit** — atomic commit: `refactor: deepen identity, owner-DM, and item-status modules — 4 auth copies → 1, 2 DM copies → 1, 5 status rules → service module`.

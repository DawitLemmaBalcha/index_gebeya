# TECH-01 & TECH-02 Implementation Blueprint

**Date:** 2026-07-23
**Tickets:** TECH-01 (pg_trgm extension), TECH-02 (HNSW + GIN indexes)
**Status:** Ready for @build

---

## Goal

Enable PostgreSQL extensions (`vector` and `pg_trgm`) via automated startup code, add HNSW vector and GIN text indexes to the `items` table, and restructure the startup sequence so extensions are guaranteed available before table creation. All index definitions live in a single location: Phase 3 of `startup_event()`.

---

## Files to Modify

1. `backend/database.py` — Add `ensure_db_extensions(engine)` helper function
2. `backend/main.py` — Remove module-level `create_all()`, restructure `startup_event()` into 4 phases

**`backend/models.py` is NOT modified.** No `__table_args__`, no `Index` imports, no changes of any kind.

No new files. No shell scripts. No Alembic. No docker-compose changes.

---

## Strict Import Map

### New imports into `backend/database.py`

- `from sqlalchemy import text` — used inside `ensure_db_extensions()` to execute raw DDL
- `import logging` — add `logger = logging.getLogger(__name__)` below existing imports

### New imports into `backend/main.py`

- `from sqlalchemy import text` — used in startup event Phase 3 for index DDL
- `from database import ensure_db_extensions` — the new helper from Step 1

### Functions moved

- `Base.metadata.create_all(bind=engine)` — **removed** from module-level (currently line 31 of `main.py`), **moved** into `startup_event()` Phase 2

### Existing imports in `main.py` — preserved

- `from database import engine, Base` — kept; `engine` used in startup event; `Base` used in Phase 2
- All router imports, logging setup, middleware config — untouched

---

## Step-by-Step Execution

### Step 1 — Add `ensure_db_extensions()` to `backend/database.py`

Add a new function at the bottom of `backend/database.py`, after the `get_db` generator, with the following signature and behavior.

**Function name:** `ensure_db_extensions(engine)`

**Parameters:**
- `engine` — the SQLAlchemy `Engine` instance defined in the same module

**Behavior:**
1. Open a connection context using `engine.begin()` — this handles commit on success, rollback on exception, and auto-close of the connection.
2. Inside the context, execute two raw SQL statements via `conn.execute(text(...))`:
   - `CREATE EXTENSION IF NOT EXISTS vector`
   - `CREATE EXTENSION IF NOT EXISTS pg_trgm`
3. Both statements are idempotent — safe to run on every container start.
4. Log a message at INFO level indicating extensions were enabled or already existed.
5. If either statement raises an exception, catch it, log a WARNING with the exception details, and let execution continue. The app should not crash if the database is temporarily unavailable during startup.
6. The function returns `None` — it either succeeds or logs a warning and continues.

**New import needed at top of `database.py`:**
- `from sqlalchemy import text`

**Add logger near the top of `database.py`:**
- `import logging` (likely already imported implicitly, but add it explicitly)
- `logger = logging.getLogger(__name__)` below the `Base = declarative_base()` line

---

### Step 2 — Remove the module-level `create_all()` call in `backend/main.py`

Delete line 31:
```python
Base.metadata.create_all(bind=engine)
```

This line currently executes at Python import time, before the FastAPI app is even constructed and before any startup event fires. It must not remain at module scope because extensions (Phase 1) must run before any DDL that might reference them.

Everything else at module scope in `main.py` stays unchanged — the logging setup, the `EndpointFilter`, the `app = FastAPI(...)` instantiation, the media mount, the CORS middleware, all router includes, and the health-check root endpoint.

---

### Step 3 — Add new imports to `backend/main.py`

At the top of `main.py`, in the existing import block, add these two lines:

- `from sqlalchemy import text`
- `from database import ensure_db_extensions`

Place them near the existing `from database import engine, Base` line (line 7) for logical grouping.

---

### Step 4 — Expand `startup_event()` with a 4-phase initialization sequence

Replace the body of the `startup_event()` function (currently lines 49-54) with the following ordered sequence. Each phase is a discrete block with its own logging.

---

**Phase 1 — Enable PostgreSQL extensions**

Call `ensure_db_extensions(engine)` inside a `try/except`. On success, log at INFO level. On failure, log at WARNING level and continue.

This must run FIRST. The GIN index in Phase 3 requires the `pg_trgm` extension to exist, and `create_all()` in Phase 2 may reference `vector` type if tables are being created fresh.

---

**Phase 2 — Create tables**

Call `Base.metadata.create_all(bind=engine)`.

- On a **fresh deploy** (no tables exist), this creates every table in the metadata: `users`, `user_interactions`, `alerts`, `notifications`, `channels`, `reviews`, `items`, `item_images`.
- On an **existing deploy**, this is a no-op for every table — PostgreSQL's `CREATE TABLE IF NOT EXISTS` semantics skip tables that already exist.
- Because `models.py` has NO index metadata (no `__table_args__` on `Item` containing `Index` objects), this call creates **tables only, zero indexes**. Indexes are exclusively the responsibility of Phase 3.

Log at INFO level on success.

---

**Phase 3 — Create indexes** (SINGLE SOURCE OF TRUTH)

Open a connection via `engine.begin()` and execute exactly two `CREATE INDEX IF NOT EXISTS` statements as raw DDL. **This is the one and only location where index definitions exist in the entire codebase.**

Statement 1 — HNSW index on `image_vector`:
```
CREATE INDEX IF NOT EXISTS ix_items_image_vector_hnsw
ON items USING hnsw (image_vector vector_cosine_ops)
```

Statement 2 — GIN trigram index on concatenated title + description:
```
CREATE INDEX IF NOT EXISTS ix_items_text_search
ON items USING gin ((coalesce(title, '') || ' ' || coalesce(description, '')) gin_trgm_ops)
```

Both are wrapped in individual `conn.execute(text(...))` calls. Each is idempotent because of `IF NOT EXISTS`.

**Behavior on different deploy states:**

- **Fresh deploy:** Phase 2 created the `items` table (empty). Phase 3 creates both indexes from scratch. The `IF NOT EXISTS` is satisfied because the indexes don't exist yet.
- **Existing deploy (indexes missing):** Phase 2 skipped the `items` table (already exists). Phase 3 creates both indexes. This is the one-time upgrade path.
- **Existing deploy (indexes present):** Phase 2 skipped the table. Phase 3 encounters `IF NOT EXISTS`, detects the indexes already exist, and skips creation. Zero overhead on restart.
- **Restart:** Same as "indexes present" — no-ops across all phases.

**There is no second code path, no model-level fallback, and no `__table_args__` to synchronize.** If the index definition ever needs adjustment (e.g., changing HNSW parameters), the developer edits exactly one `CREATE INDEX IF NOT EXISTS` statement.

Log each index creation (or skip) at INFO level:
- On creation: `"Created index: <name>"`
- On skip: `"Index already exists: <name>"`

Wrap Phase 3 in a `try/except` inside the `engine.begin()` block. On failure, log a WARNING and continue. The app should not crash because indexes are missing — queries will still work (just slowly), and the admin can address the issue without downtime.

---

**Phase 4 — Initialize taxonomy index** (existing behavior, preserved)

Keep the existing `try/except` block exactly as-is:
- `initialize_taxonomy_index()`
- `logger.info("✅ Visual Taxonomy Index Initialized")` on success
- `logger.error(f"❌ Failed to init Taxonomy Index: {e}")` on failure

This runs LAST because it may query database tables that depend on extensions and indexes being in place. In practice, the taxonomy index is in-memory (CLIP embeddings for category names) and does not directly depend on database indexes, but the ordering is principled: all database infrastructure is ready before any service that touches the database.

---

**Error handling for the entire startup event:**

Each phase has its own `try/except`. No single failure blocks subsequent phases. The app always reaches Phase 4 (taxonomy init) even if Phase 1, 2, or 3 fails. This is deliberate — the app should serve requests even with degraded search performance, rather than refusing to start.

**Logging output on a healthy startup:**
```
✅ Database extensions enabled (vector, pg_trgm)
✅ Database tables verified/created
Created index: ix_items_image_vector_hnsw
Created index: ix_items_text_search
✅ Visual Taxonomy Index Initialized
```

**Logging output on a restart (indexes already exist):**
```
✅ Database extensions enabled (vector, pg_trgm)
✅ Database tables verified/created
Index already exists: ix_items_image_vector_hnsw
Index already exists: ix_items_text_search
✅ Visual Taxonomy Index Initialized
```

---

## Testing Requirements

The `@build` agent must implement the following manual verification steps (not automated tests in the test suite — these are run-once validations against the running system).

### Test 1 — Extension verification

Connect to the PostgreSQL database directly (via `docker exec` into the `db` container or via `psql` on port 5433) and run:
```sql
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');
```

Expected result: two rows, one for `vector` and one for `pg_trgm`, each with a version number.

### Test 2 — Index verification

In the same PostgreSQL session, run:
```sql
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'items' AND indexname LIKE 'ix_items_%';
```

Expected result: exactly two rows.

Row 1 (`ix_items_image_vector_hnsw`): The `indexdef` must contain `USING hnsw` and `vector_cosine_ops`.

Row 2 (`ix_items_text_search`): The `indexdef` must contain `USING gin`, `coalesce`, `gin_trgm_ops`, and the concatenation of `title` and `description`.

### Test 3 — Idempotency (restart test)

Restart the API container (`docker compose restart api`). Observe the application logs. Verify that:
- Phase 3 logs `Index already exists` for both indexes (not `Created index`)
- No errors or warnings appear

### Test 4 — Search endpoint functional test

Before this change, the search endpoint fails with a SQL error because `similarity()` requires `pg_trgm` which was never enabled. After this change:

Send a POST request to the search endpoint with a text query (e.g., `{"query": "iPhone", "limit": 10}` to `/search/`). Verify:
- The response has HTTP status 200
- The response body contains an array of items (may be empty if no iPhones in the catalog, but must not error)
- No `function similarity(text, text) does not exist` or similar SQL error in the API logs

### Test 5 — Cold-start (fresh database) test

This is optional but strongly recommended for confidence:

1. Tear down the existing database volume: `docker compose down -v`
2. Start from scratch: `docker compose up -d`
3. Verify that:
   - Extensions are created (Test 1 passes)
   - Tables are created (check `\dt` in psql — `items` table exists)
   - Indexes are created (Test 2 passes)
   - The search endpoint works (Test 4 passes)

This validates the full fresh-deploy path.

---

## Dependency Order

```
TECH-01 (pg_trgm extension enabled in Phase 1)
    │
    ▼
TECH-02 (GIN index requires pg_trgm → Phase 3)
    +
TECH-02 (HNSW index requires vector → Phase 3)
    │
    ▼
Existing search/recommendation queries now leverage indexes
```

Both tickets are implemented together because:
1. TECH-02's GIN index functionally requires TECH-01's `pg_trgm` extension
2. Both require the same architectural change: moving `create_all()` into startup and adding the Phase 1 extension setup
3. Deploying them atomically avoids a window where `pg_trgm` is enabled but indexes are missing, or indexes are attempted before the extension exists

---

## What This Blueprint Replaces

| Before | After |
|--------|-------|
| `docker exec index_db psql ... -c "CREATE EXTENSION vector"` run manually by the operator | `ensure_db_extensions()` runs automatically in startup event Phase 1 |
| `pg_trgm` never enabled — every text search fails with a SQL error | `pg_trgm` enabled idempotently on every container start alongside `vector` |
| `Base.metadata.create_all()` runs at Python import time (line 31 of `main.py`) | Moved to startup event Phase 2, after extensions are guaranteed available |
| `Item.image_vector` has no index — every vector search does O(n) full scan of `items` table | HNSW index created in Phase 3 — queries use O(log n) approximate nearest-neighbor |
| Title+description `similarity()` has no GIN index — every text search does O(n) full scan | GIN trigram index created in Phase 3 — PostgreSQL can use index scan for `similarity()` |
| _(none — new principle)_ | Single source of truth for index definitions: Phase 3 in `startup_event()`. No dual code path. |

---

## Notes for @build

1. **Do NOT modify `docker-compose.yml`.** No new environment variables, no entrypoint scripts, no `depends_on` changes needed.

2. **Do NOT modify `backend/Dockerfile`.** No new system packages or startup scripts needed. The `backend/` directory bind-mount in docker-compose (line 34) means code changes are reflected immediately without a rebuild.

3. **Do NOT modify `backend/models.py`.** The model stays exactly as-is. No `__table_args__`, no `Index` imports, no `postgresql_ops`. The current `image_vector = mapped_column(Vector(512))` line is correct and does not need an `index=True` parameter — the index is handled entirely in Phase 3 DDL.

4. **The `pgvector/pgvector:pg16` Docker image already includes both `vector` and `pg_trgm` extensions.** They are bundled with the image and only need `CREATE EXTENSION` to activate. No additional Postgres packages or apt-get steps are required.

5. **Be careful with the `engine.begin()` context manager.** It commits on successful block exit and rolls back on exception. Since Phase 3 runs `CREATE INDEX IF NOT EXISTS` statements that are all or partially independent, wrap each `conn.execute(text(...))` in its own `try/except` inside the `engine.begin()` block, so one index failure doesn't roll back the other. Alternatively, keep both in one `try/except` if you want atomicity (both succeed or both get rolled back). The blueprint prefers independence — each index attempt should log its own outcome.

6. **The `Review` model already has `__table_args__`** (a `UniqueConstraint` on user_id + channel_id). This is an existing pattern in the codebase — do NOT modify it and do NOT add anything to it. The decision not to use `__table_args__` for `Item` indexes is deliberate (single source of truth in Phase 3).

7. **Race condition with `depends_on`:** `docker-compose.yml` has `api` depending on `db`, but `depends_on` only waits for the container to start, not for PostgreSQL to accept connections. If the database isn't ready when the API container reaches `startup_event()`, Phase 1's `engine.begin()` will throw a connection error. The `try/except` in Phase 1 handles this gracefully — it logs a warning and continues. The app starts without extensions or indexes, and search performance degrades until the next restart (when the database will be ready). This is acceptable for now; a production hardening could add retry logic, but that is out of scope for TECH-01/TECH-02.

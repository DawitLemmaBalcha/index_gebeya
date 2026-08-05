import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from database import engine, Base, ensure_db_extensions
from ai_engine.vector_client import initialize_taxonomy_index
from admin import setup_admin

# 👇 IMPORT ROUTERS 👇
from api.routes import ingestion, search, items, reviews, alerts, notifications, analytics, feed, channels, payments, subscriptions

# Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("index_api")

# --- CUSTOM LOG FILTER ---
class EndpointFilter(logging.Filter):
    """
    Filter out health checks and internal polling from access logs
    to keep the console clean.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/notifications/pending") == -1

# Apply filter to Uvicorn's access logger
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
# -------------------------

app = FastAPI(title="Index Gebeya API", version="0.6.0")

# Mount Media
os.makedirs("/app/media/temp", exist_ok=True)
app.mount("/media", StaticFiles(directory="/app/media"), name="media")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    # ===================================================================
    # Phase 1 — Enable PostgreSQL extensions (vector, pg_trgm)
    # ===================================================================
    try:
        ensure_db_extensions(engine)
    except Exception as e:
        logger.warning(f"⚠️ Extension setup failed: {e}")

    # ===================================================================
    # Phase 2 — Create tables (idempotent: CREATE TABLE IF NOT EXISTS)
    # ===================================================================
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables verified/created")
    except Exception as e:
        logger.warning(f"⚠️ Table creation failed: {e}")

    # ===================================================================
    # Phase 3 — Schema migrations (idempotent ALTER TABLE for new columns)
    # ===================================================================
    try:
        with engine.begin() as conn:
            # TECH-19: Add indexing_paused and is_active columns to channels
            conn.execute(text(
                "ALTER TABLE channels ADD COLUMN IF NOT EXISTS indexing_paused BOOLEAN DEFAULT FALSE"
            ))
            conn.execute(text(
                "ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"
            ))
            logger.info("✅ TECH-19 schema migration verified (indexing_paused, is_active)")
    except Exception as e:
        logger.warning(f"⚠️ Schema migration failed: {e}")

    try:
        with engine.begin() as conn:
            # TECH-21: Add is_active column to items for soft-delete dedup
            conn.execute(text(
                "ALTER TABLE items ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"
            ))
            logger.info("✅ TECH-21 schema migration verified (items.is_active)")
    except Exception as e:
        logger.warning(f"⚠️ TECH-21 schema migration failed: {e}")

    try:
        with engine.begin() as conn:
            # TECH-21b: Add is_dedup column to items for dedup replacement tracking
            conn.execute(text(
                "ALTER TABLE items ADD COLUMN IF NOT EXISTS is_dedup BOOLEAN DEFAULT FALSE"
            ))
            logger.info("✅ TECH-21b schema migration verified (items.is_dedup)")
    except Exception as e:
        logger.warning(f"⚠️ TECH-21b schema migration failed: {e}")

    try:
        with engine.begin() as conn:
            # TECH-22: Add status, is_stale columns to items + create sold_reports table
            conn.execute(text(
                "ALTER TABLE items ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active'"
            ))
            conn.execute(text(
                "ALTER TABLE items ADD COLUMN IF NOT EXISTS is_stale BOOLEAN DEFAULT FALSE"
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS sold_reports (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT _user_item_sold_report_uc UNIQUE(user_id, item_id)
                )
                """
            ))
            logger.info("✅ TECH-22 schema migration verified (items.status, items.is_stale, sold_reports)")
    except Exception as e:
        logger.warning(f"⚠️ TECH-22 schema migration failed: {e}")

    try:
        with engine.begin() as conn:
            # TECH-23: Create item_edits table for inventory edit history audit log
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS item_edits (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    field VARCHAR NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    edited_by INTEGER NOT NULL REFERENCES users(id),
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ))
            logger.info("✅ TECH-23 schema migration verified (item_edits)")
    except Exception as e:
        logger.warning(f"⚠️ TECH-23 schema migration failed: {e}")

    try:
        with engine.begin() as conn:
            # TECH-25: Alert/notification retention lifecycle
            #   1. Add deleted_at soft-delete marker to alerts (nullable, no
            #      DEFAULT — NULL means "never user-deleted"; the purge
            #      predicate branches on NULL explicitly).
            #   2. Swap notifications_alert_id_fkey from the default RESTRICT
            #      to ON DELETE CASCADE so an alert purge removes its
            #      notifications at the database level.
            # Idempotency: PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so
            # the drop is guarded on pg_constraint existence — the repo-
            # consistent extension of the IF NOT EXISTS idiom. Safe on all
            # three states: legacy DB (RESTRICT → dropped, re-added CASCADE),
            # prior TECH-25 run (CASCADE → dropped, re-added identical — a
            # no-op churn), fresh DB (create_all already made CASCADE → no-op
            # churn). No error path on any repeat.
            conn.execute(text(
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
            ))
            conn.execute(text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'notifications_alert_id_fkey'
                          AND conrelid = 'notifications'::regclass
                    ) THEN
                        ALTER TABLE notifications DROP CONSTRAINT notifications_alert_id_fkey;
                    END IF;
                END $$;
                """
            ))
            conn.execute(text(
                """
                ALTER TABLE notifications ADD CONSTRAINT notifications_alert_id_fkey
                FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
                """
            ))
            logger.info("✅ TECH-25 schema migration verified (alerts.deleted_at, notifications FK cascade)")
    except Exception as e:
        logger.warning(f"⚠️ TECH-25 schema migration failed: {e}")

    try:
        with engine.begin() as conn:
            # USER-DELETION FK POLICY (side mission, TECH-25 class):
            # sqladmin hard-delete of a users row used to fail with
            # ForeignKeyViolation because 8 FKs referenced users.id with no
            # ON DELETE action (RESTRICT default). Locked policy:
            #   user_interactions.user_id → ON DELETE SET NULL
            #   alerts/notifications/reviews/sold_reports/boosts/
            #     subscriptions user_id + item_edits.edited_by →
            #     ON DELETE CASCADE
            # channels.registered_by is a plain BigInteger, NOT an FK —
            # intentionally untouched (channels survive user deletion).
            # Idempotency: PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so
            # each drop is guarded on pg_constraint existence — the repo-
            # consistent extension of the IF NOT EXISTS idiom (TECH-25
            # precedent). Safe on all three states: legacy DB (RESTRICT →
            # dropped, re-added with action), prior run (action → dropped,
            # re-added identical — a no-op churn), fresh DB (create_all made
            # the action → no-op churn). No error path on any repeat.
            fk_actions = [
                # (table, column, constraint, on_delete_action)
                ("user_interactions", "user_id", "user_interactions_user_id_fkey", "SET NULL"),
                ("alerts", "user_id", "alerts_user_id_fkey", "CASCADE"),
                ("notifications", "user_id", "notifications_user_id_fkey", "CASCADE"),
                ("reviews", "user_id", "reviews_user_id_fkey", "CASCADE"),
                ("sold_reports", "user_id", "sold_reports_user_id_fkey", "CASCADE"),
                ("item_edits", "edited_by", "item_edits_edited_by_fkey", "CASCADE"),
                ("boosts", "user_id", "boosts_user_id_fkey", "CASCADE"),
                ("subscriptions", "user_id", "subscriptions_user_id_fkey", "CASCADE"),
            ]
            for table, column, constraint, action in fk_actions:
                conn.execute(text(
                    f"""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = '{constraint}'
                              AND conrelid = '{table}'::regclass
                        ) THEN
                            ALTER TABLE {table} DROP CONSTRAINT {constraint};
                        END IF;
                    END $$;
                    """
                ))
                conn.execute(text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                    f"FOREIGN KEY ({column}) REFERENCES users(id) ON DELETE {action}"
                ))
            logger.info("✅ user-deletion FK policy migration verified (8 user FKs)")
    except Exception as e:
        logger.warning(f"⚠️ user-deletion FK policy migration failed: {e}")

    try:
        with engine.begin() as conn:
            # CHANNEL-DELETION FK POLICY (final sweep of the FK-action bug
            # class, a97d1e2 pattern): sqladmin hard-delete of a channels row
            # used to fail because 3 FKs referenced channels.id with no ON
            # DELETE action (RESTRICT default). Locked policy:
            #   items.channel_id   → ON DELETE CASCADE (listings die)
            #   reviews.channel_id → ON DELETE CASCADE (ratings die)
            #   boosts.channel_id  → ON DELETE CASCADE (boosts die)
            # The SOFT remove flow (is_active flag) is untouched — a flag,
            # not a delete. With this, EVERY FK in models.py carries an
            # explicit ondelete action (users: 8 in a97d1e2; items: item_id
            # CASCADEs; alerts: TECH-25; channels: this block).
            # Idempotency: PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so
            # each drop is guarded on pg_constraint existence — the repo-
            # consistent extension of the IF NOT EXISTS idiom (TECH-25
            # precedent). Safe on all three states: legacy DB (RESTRICT →
            # dropped, re-added with action), prior run (action → dropped,
            # re-added identical — a no-op churn), fresh DB (create_all made
            # the action → no-op churn). No error path on any repeat.
            fk_actions = [
                # (table, column, constraint, on_delete_action)
                ("items", "channel_id", "items_channel_id_fkey", "CASCADE"),
                ("reviews", "channel_id", "reviews_channel_id_fkey", "CASCADE"),
                ("boosts", "channel_id", "boosts_channel_id_fkey", "CASCADE"),
            ]
            for table, column, constraint, action in fk_actions:
                conn.execute(text(
                    f"""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = '{constraint}'
                              AND conrelid = '{table}'::regclass
                        ) THEN
                            ALTER TABLE {table} DROP CONSTRAINT {constraint};
                        END IF;
                    END $$;
                    """
                ))
                conn.execute(text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                    f"FOREIGN KEY ({column}) REFERENCES channels(id) ON DELETE {action}"
                ))
            logger.info("✅ channel-deletion FK policy migration verified (3 channel FKs)")
    except Exception as e:
        logger.warning(f"⚠️ channel-deletion FK policy migration failed: {e}")

    try:
        with engine.begin() as conn:
            # TECH-26 (NB-43..NB-47): monetization schema
            #   1. alerts.lapsed — additive boolean; True = deactivated by
            #      subscription lapse, distinct from user pause (lapsed=False).
            #   2. boosts — paid/credit share one table; UNIQUE
            #      telegram_payment_charge_id is the idempotency key (NULLs
            #      distinct in Postgres, so credit boosts coexist).
            #   3. subscriptions — one row per user; renewals update the same
            #      row's period_end; UNIQUE charge id for idempotent replay.
            conn.execute(text(
                "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS lapsed BOOLEAN DEFAULT FALSE"
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS boosts (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    channel_id INTEGER NOT NULL REFERENCES channels(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    source VARCHAR NOT NULL DEFAULT 'paid',
                    price_paid_stars INTEGER,
                    telegram_payment_charge_id VARCHAR UNIQUE,
                    starts_at TIMESTAMPTZ NOT NULL,
                    ends_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_boosts_item_id ON boosts (item_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_boosts_ends_at ON boosts (ends_at)"
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    product VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'active',
                    telegram_payment_charge_id VARCHAR UNIQUE,
                    invoice_payload VARCHAR NOT NULL,
                    current_period_start TIMESTAMPTZ,
                    current_period_end TIMESTAMPTZ,
                    is_recurring BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id)"
            ))
            logger.info("✅ TECH-26 schema migration verified (alerts.lapsed, boosts, subscriptions)")
    except Exception as e:
        logger.warning(f"⚠️ TECH-26 schema migration failed: {e}")

    # ===================================================================
    # Phase 4 — Create indexes (SINGLE SOURCE OF TRUTH)
    # ===================================================================
    try:
        with engine.begin() as conn:
            def _index_exists(conn, name: str) -> bool:
                """Check if an index already exists on the items table."""
                row = conn.execute(
                    text(
                        "SELECT 1 FROM pg_indexes "
                        "WHERE indexname = :name AND tablename = 'items'"
                    ),
                    {"name": name},
                ).fetchone()
                return row is not None

            index_definitions = [
                {
                    "name": "ix_items_image_vector_hnsw",
                    "ddl": (
                        "CREATE INDEX IF NOT EXISTS ix_items_image_vector_hnsw "
                        "ON items USING hnsw (image_vector vector_cosine_ops)"
                    ),
                },
                {
                    "name": "ix_items_text_search",
                    "ddl": (
                        "CREATE INDEX IF NOT EXISTS ix_items_text_search "
                        "ON items USING gin ((coalesce(title, '') || ' ' || coalesce(description, '')) gin_trgm_ops)"
                    ),
                },
            ]

            for idx_def in index_definitions:
                try:
                    if _index_exists(conn, idx_def["name"]):
                        logger.info(f"Index already exists: {idx_def['name']}")
                    else:
                        conn.execute(text(idx_def["ddl"]))
                        logger.info(f"Created index: {idx_def['name']}")
                except Exception as e:
                    logger.warning(f"⚠️ Index creation failed for {idx_def['name']}: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Index setup connection failed: {e}")

    # ===================================================================
    # Phase 5 — Initialize taxonomy index (existing behavior, preserved)
    # ===================================================================
    try:
        initialize_taxonomy_index()
        logger.info("✅ Visual Taxonomy Index Initialized")
    except Exception as e:
        logger.error(f"❌ Failed to init Taxonomy Index: {e}")

    # ===================================================================
    # Phase 5.5 — TECH-22: Schedule daily cleanup background task
    # ===================================================================
    try:
        import threading
        from services.cleanup import run_cleanup_and_log

        def _schedule_cleanup():
            try:
                run_cleanup_and_log()
            except Exception as e:
                logger.warning(f"⚠️ Cleanup task failed: {e}")
            threading.Timer(86400, _schedule_cleanup).start()  # 24h

        threading.Timer(60, _schedule_cleanup).start()  # first run after 60s
        logger.info("✅ TECH-22 daily cleanup scheduler registered")
    except ImportError as e:
        logger.warning(f"⚠️ Could not import cleanup service: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Cleanup scheduler setup failed: {e}")

    # ===================================================================
    # Phase 5.6 — TECH-31: Daily Star payments reconciliation
    # ===================================================================
    try:
        import asyncio
        import threading
        from constants import MONETIZATION_ENABLED
        from services.reconciliation import reconcile_star_payments

        def _schedule_reconcile():
            try:
                if MONETIZATION_ENABLED:
                    from database import SessionLocal
                    db = SessionLocal()
                    try:
                        summary = asyncio.run(reconcile_star_payments(db))
                        logger.info(f"✅ Star payments reconciliation: {summary}")
                    finally:
                        db.close()
                else:
                    logger.info("⏸️ Star reconciliation skipped (MONETIZATION_ENABLED=0)")
            except Exception as e:
                logger.warning(f"⚠️ Star reconcile task failed: {e}")
            threading.Timer(86400, _schedule_reconcile).start()  # 24h

        threading.Timer(3600, _schedule_reconcile).start()  # first run after 1h
        logger.info("✅ TECH-31 daily star reconciliation scheduler registered")
    except ImportError as e:
        logger.warning(f"⚠️ Could not import reconciliation service: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Star reconcile scheduler setup failed: {e}")

@app.get("/")
def read_root():
    return {"status": "online", "service": "Index Gebeya Alpha 0.6.0"}

# INCLUDE ROUTERS
app.include_router(ingestion.router)
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(items.router, prefix="/items", tags=["Items"])
app.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# RENAMED FROM /analytics TO /activity
app.include_router(analytics.router, prefix="/activity", tags=["Analytics"]) 

app.include_router(feed.router, prefix="/feed", tags=["Feed"])
app.include_router(channels.router, prefix="/channels", tags=["Channels"])

# NB-43..NB-47: Monetization routers (blueprint §3.4) — internal payments first
app.include_router(payments.router)  # no prefix — internal paths are explicit
app.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])

# SQLAdmin — full CRUD dashboard at /admin
setup_admin(app)
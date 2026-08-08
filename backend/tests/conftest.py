"""
Shared fixtures for backend unit tests (test_auth, test_owner_dm, test_item_status).

These tests run in-process against an ISOLATED database (suq_test_db), NOT the
production suq_main_db. The app modules are pointed at the test DB by overriding
DB_* environment variables BEFORE importing anything from the app.

The repo .env file is loaded first (DB_USER, DB_PASSWORD, TELEGRAM_BOT_TOKEN...),
then the DB_* connection vars are redirected to the local Docker-mapped Postgres
(localhost:5433 -> db:5432) and the isolated test database.
"""

import os
import sys

from dotenv import load_dotenv

# Repo root is two levels up from this file (backend/tests/conftest.py)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Load .env (DB_USER, DB_PASSWORD, TELEGRAM_BOT_TOKEN, ...) if present.
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

# Redirect the app to the isolated test database BEFORE app modules import database.py.
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["DB_NAME"] = "suq_test_db"

# Make backend/ importable as top-level packages (models, services, api, ...).
_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# The app's import chain (services.alerting -> ai_engine.vector_client) imports
# fastembed at module-import time. The host test venv omits that heavy ML stack;
# provide a minimal stub that is only used when the real package is absent.
try:
    import fastembed  # noqa: F401
except ImportError:
    _FASTEMBED_STUB = "/tmp/opencode/fastembed_stub"
    if os.path.isdir(_FASTEMBED_STUB) and _FASTEMBED_STUB not in sys.path:
        sys.path.insert(0, _FASTEMBED_STUB)

import pytest  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402,F401  (registers ALL tables on Base.metadata before fixtures run)


@pytest.fixture(scope="session", autouse=True)
def _test_db_schema():
    """Create all tables in the isolated test DB once per session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clear_boost_price_cache():
    """NB-51: the boost-price module cache is process-global; tests seed
    different prices per test, so the cache must be clean between tests."""
    from services import boost_pricing

    boost_pricing._cache.clear()
    yield
    boost_pricing._cache.clear()


@pytest.fixture()
def db_session(_test_db_schema):
    """Fresh, empty session for each test (all tables truncated)."""
    session = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    try:
        yield session
    finally:
        session.close()

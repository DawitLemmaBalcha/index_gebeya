"""
NB-52: ops console Section 8 — Settings & Flags (blueprint §2.10).

The effective-config view; DB overrides on top of env defaults; the
console never accepts an unknown knob (409).
"""
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from models import AdminSetting, AuditLog
from services.settings_registry import REGISTRY, get_setting

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _settings_client(db_session):
    from api.routes import ops_auth, ops_settings

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_settings.router, prefix="/ops/settings")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    login = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert login.status_code == 200
    return client


class TestSettingsSurface:
    def test_lists_all_registered_keys_with_live_value_and_source(self, db_session, monkeypatch):
        monkeypatch.delenv("ALERT_MAX_PER_USER", raising=False)
        from services.settings_registry import set_setting
        set_setting(db_session, "max_alerts_per_user", "7")

        client = _settings_client(db_session)
        resp = client.get("/ops/settings")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == len(REGISTRY)
        by_key = {r["key"]: r for r in rows}
        assert by_key["max_alerts_per_user"]["value"] == 7
        assert by_key["max_alerts_per_user"]["source"] == "db"
        assert by_key["stale_item_days"]["source"] == "env"
        assert by_key["stale_item_days"]["value"] == 14

    def test_edit_creates_db_row_flipping_source(self, db_session, monkeypatch):
        monkeypatch.delenv("STALE_ITEM_DAYS", raising=False)
        assert db_session.scalar(
            select(AdminSetting).where(AdminSetting.key == "stale_item_days")
        ) is None

        client = _settings_client(db_session)
        resp = client.put("/ops/settings/stale_item_days", json={"value": "21"})
        assert resp.status_code == 200, resp.text
        assert get_setting(db_session, "stale_item_days") == 21

        row = db_session.scalar(
            select(AdminSetting).where(AdminSetting.key == "stale_item_days")
        )
        assert row is not None
        assert row.source == "db"

        # audit row written
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "update_setting")
        )
        assert audit is not None
        assert audit.entity_id == "stale_item_days"
        assert audit.admin_user == ADMIN_USER

    def test_invalid_value_400(self, db_session):
        client = _settings_client(db_session)
        resp = client.put("/ops/settings/stale_item_days", json={"value": "abc"})
        assert resp.status_code == 400

    def test_unregistered_key_409_with_clear_error(self, db_session):
        client = _settings_client(db_session)
        resp = client.put("/ops/settings/some_unknown_knob", json={"value": "1"})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Setting is env-sourced; edit via deploy"
        # nothing written
        assert db_session.scalar(
            select(AuditLog).where(AuditLog.entity_id == "some_unknown_knob")
        ) is None

    def test_requires_ops_admin(self, db_session):
        from api.routes import ops_settings

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
        app.include_router(ops_settings.router, prefix="/ops/settings")

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        resp = TestClient(app).get("/ops/settings")
        assert resp.status_code == 401

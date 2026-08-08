"""
NB-52: ops console Section 9 — Audit (blueprint §2.10).

Read-only list of every console mutation, filterable by section and admin,
ordered newest-first. No mutation endpoints exist.
"""
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from services.audit import record_audit

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _audit_client(db_session):
    from api.routes import ops_audit, ops_auth

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_audit.router, prefix="/ops/audit")

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


def _seed_rows(db_session):
    record_audit(
        db_session, admin_user="admin", action="update_boost_price",
        section="monetization", entity_type="boost_price", entity_id="A/B",
        before={"price_stars": 1}, after={"price_stars": 2},
    )
    record_audit(
        db_session, admin_user="operator2", action="run_reconciliation",
        section="payments", entity_type="scheduler",
    )
    record_audit(
        db_session, admin_user="admin", action="set_toggle",
        section="monetization", entity_type="admin_setting", entity_id="x",
    )


class TestAuditList:
    def test_lists_rows_newest_first(self, db_session):
        _seed_rows(db_session)
        client = _audit_client(db_session)
        resp = client.get("/ops/audit")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 3
        created = [r["created_at"] for r in rows]
        assert created == sorted(created, reverse=True)
        # full field surface
        assert {"id", "admin_user", "action", "section", "entity_type",
                "entity_id", "before", "after", "created_at"} <= set(rows[0].keys())

    def test_filter_by_section(self, db_session):
        _seed_rows(db_session)
        client = _audit_client(db_session)
        rows = client.get("/ops/audit", params={"section": "monetization"}).json()
        assert len(rows) == 2
        assert all(r["section"] == "monetization" for r in rows)

    def test_filter_by_admin(self, db_session):
        _seed_rows(db_session)
        client = _audit_client(db_session)
        rows = client.get("/ops/audit", params={"admin": "operator2"}).json()
        assert len(rows) == 1
        assert rows[0]["admin_user"] == "operator2"

    def test_combined_filters_and_limit_offset(self, db_session):
        _seed_rows(db_session)
        client = _audit_client(db_session)
        rows = client.get(
            "/ops/audit",
            params={"section": "monetization", "admin": "admin", "limit": 1, "offset": 0},
        ).json()
        assert len(rows) == 1
        assert rows[0]["admin_user"] == "admin"

    def test_read_only_no_mutation_endpoints(self, db_session):
        client = _audit_client(db_session)
        # no POST/PUT/DELETE routes on the router
        assert client.post("/ops/audit", json={}).status_code in (405, 404)
        assert client.put("/ops/audit/1", json={}).status_code in (405, 404)
        assert client.delete("/ops/audit/1").status_code in (405, 404)
        from api.routes import ops_audit
        methods = set()
        for route in ops_audit.router.routes:
            methods.update(getattr(route, "methods", set()))
        assert methods == {"GET"}

    def test_requires_ops_admin(self, db_session):
        from api.routes import ops_audit

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
        app.include_router(ops_audit.router, prefix="/ops/audit")

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        assert TestClient(app).get("/ops/audit").status_code == 401

"""
NB-49: ops-console auth seam tests.

(a) login/logout/me lifecycle over the ops_session cookie (TWO-DIRECTION
    namespace separation, blueprint D1);
(b) the locked acceptance: a console login never opens /admin and a
    sqladmin login never opens /ops/*;
(c) require_ops_admin gates protected routes with 401.
"""
import os

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from admin import setup_admin
from api.routes import ops_auth

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _ops_app():
    """Minimal app: ops auth router + one protected probe route."""
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret",
        session_cookie="ops_session",
        max_age=604800,
        same_site="lax",
    )
    app.include_router(ops_auth.router, prefix="/ops/auth")

    @app.get("/ops/protected")
    def protected(_: None = Depends(ops_auth.require_ops_admin)):
        return {"ok": True}

    return app


def _combined_app():
    """Parent app with the ops session middleware + sqladmin mounted
    (the production D1 shape: sqladmin lives on its own sub-app)."""
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret",
        session_cookie="ops_session",
        max_age=604800,
        same_site="lax",
    )
    setup_admin(app)
    app.include_router(ops_auth.router, prefix="/ops/auth")
    return app


class TestLoginLogoutMe:
    def test_login_sets_ops_session_cookie_and_me_returns_user(self):
        client = TestClient(_ops_app())
        resp = client.post(
            "/ops/auth/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
        assert resp.status_code == 200
        assert resp.json() == {"user": ADMIN_USER, "role": "admin"}
        assert "ops_session" in resp.headers.get("set-cookie", "")

        me = client.get("/ops/auth/me")
        assert me.status_code == 200
        assert me.json() == {"user": ADMIN_USER, "role": "admin"}

    def test_login_wrong_password_401(self):
        client = TestClient(_ops_app())
        resp = client.post(
            "/ops/auth/login",
            json={"username": ADMIN_USER, "password": "definitely-wrong"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_login_wrong_username_401(self):
        client = TestClient(_ops_app())
        resp = client.post(
            "/ops/auth/login",
            json={"username": "intruder", "password": ADMIN_PASS},
        )
        assert resp.status_code == 401

    def test_logout_then_me_401s(self):
        client = TestClient(_ops_app())
        client.post(
            "/ops/auth/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
        resp = client.post("/ops/auth/logout")
        assert resp.status_code == 200
        assert client.get("/ops/auth/me").status_code == 401

    def test_me_401_without_login(self):
        client = TestClient(_ops_app())
        assert client.get("/ops/auth/me").status_code == 401


class TestRouteGating:
    def test_protected_route_401_without_session(self):
        client = TestClient(_ops_app())
        assert client.get("/ops/protected").status_code == 401

    def test_protected_route_200_after_login(self):
        client = TestClient(_ops_app())
        client.post(
            "/ops/auth/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
        assert client.get("/ops/protected").status_code == 200


class TestAuthSeparation:
    """The two-direction acceptance (ops-console.md Rule 1.3, blueprint D1)."""

    def test_console_login_does_not_open_sqladmin(self):
        client = TestClient(_combined_app(), follow_redirects=False)
        login = client.post(
            "/ops/auth/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
        assert login.status_code == 200
        # /admin stays locked: 302 to the sqladmin login page
        admin = client.get("/admin/")
        assert admin.status_code == 302
        assert admin.headers["location"].endswith("/admin/login")

    def test_sqladmin_login_does_not_open_ops_console(self):
        client = TestClient(_combined_app(), follow_redirects=False)
        admin_login = client.post(
            "/admin/login",
            data={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
        assert admin_login.status_code == 302  # sqladmin authenticated
        me = client.get("/ops/auth/me")
        assert me.status_code == 401  # console locked

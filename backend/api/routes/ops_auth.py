"""
NB-49: the ops-console auth seam (blueprint §2.6, ops-console.md Rule 1.3).

Cookie namespace `ops_session` (parent-app SessionMiddleware, D1) + session
key `ops_admin`. Deliberately SEPARATE from sqladmin's sub-app session
(`session` cookie, `token` key): a console login can never open /admin and
a sqladmin login can never open /ops/* — scope is explicit.

The session token carries a role field (always 'admin' in v1); permission
checks are has_role(session, role) — future roles change data, not code.
"""

import os

from fastapi import APIRouter, HTTPException, Request

from schemas import OpsLoginRequest

router = APIRouter()


def has_role(request: Request, role: str) -> bool:
    """The permission check of the future: roles are data, not code."""
    return request.session.get("ops_admin", {}).get("role") == role


def require_ops_admin(request: Request) -> None:
    """FastAPI dependency: ops-admin role required, else 401."""
    if not has_role(request, "admin"):
        raise HTTPException(status_code=401, detail="Not authenticated")


@router.post("/login")
def login(body: OpsLoginRequest, request: Request):
    """Same env credentials as sqladmin (admin.py:23-24)."""
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_pass = os.getenv("ADMIN_PASSWORD", "indexgebeya")
    if body.username != expected_user or body.password != expected_pass:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.session["ops_admin"] = {"user": body.username, "role": "admin"}
    return {"user": body.username, "role": "admin"}


@router.post("/logout")
def logout(request: Request):
    """Pop ONLY the ops key — never clear() — must not wipe other keys."""
    request.session.pop("ops_admin", None)
    return {"status": "ok"}


@router.get("/me")
def me(request: Request):
    session = request.session.get("ops_admin")
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": session.get("user"), "role": session.get("role")}

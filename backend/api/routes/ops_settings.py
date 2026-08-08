"""
NB-52: ops console Section 8 — Settings & Flags (blueprint §2.10).

The effective-config view (GET) + DB-override edits (PUT). Every
registered key is editable — the edit CREATES the DB row, flipping the
source to 'db' (the intended override mechanism). Unknown keys are
rejected with 409 — the console never silently accepts an unknown knob.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from schemas import OpsSettingUpdateRequest
from services import settings_registry
from services.audit import record_audit

from .ops_auth import require_ops_admin

router = APIRouter()


def _admin_user(request: Request) -> str:
    return request.session.get("ops_admin", {}).get("user", "admin")


@router.get("")
def get_settings(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    return settings_registry.list_settings(db)


@router.put("/{key}")
def update_setting(
    key: str,
    body: OpsSettingUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if key not in settings_registry.REGISTRY:
        raise HTTPException(
            status_code=409,
            detail="Setting is env-sourced; edit via deploy",
        )
    old = settings_registry.get_setting(db, key)
    try:
        settings_registry.set_setting(db, key, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="update_setting",
        section="settings",
        entity_type="admin_setting",
        entity_id=key,
        before={"value": old},
        after={"value": body.value},
    )
    return {"key": key, "value": settings_registry.get_setting(db, key)}

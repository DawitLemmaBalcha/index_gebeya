"""
NB-52: ops console Section 9 — Audit (blueprint §2.10).

Read-only list of every console mutation, filtered by exact section and
admin_user, ordered created_at DESC. No edit/delete/export endpoints
(Rule 6.1).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog

from .ops_auth import require_ops_admin

router = APIRouter()


@router.get("")
def list_audit(
    section: str | None = Query(None),
    admin: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    stmt = select(AuditLog)
    if section:
        stmt = stmt.where(AuditLog.section == section)
    if admin:
        stmt = stmt.where(AuditLog.admin_user == admin)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "admin_user": r.admin_user,
            "action": r.action,
            "section": r.section,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "before": r.before,
            "after": r.after,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

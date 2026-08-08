"""
NB-49: the single audit path for ops-console mutations (Rule 1.4).

Every console mutation route calls record_audit. The helper COMMITS
independently of the mutation's own transaction: a failed mutation
produces no audit row; an applied one always does.

DB errors PROPAGATE — the console never mutates silently.
"""

from sqlalchemy.orm import Session

from models import AuditLog


def record_audit(
    db: Session, *,
    admin_user: str,
    action: str,
    section: str,
    entity_type: str,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    """Append one immutable audit row and commit (Rule 1.4)."""
    row = AuditLog(
        admin_user=admin_user,
        action=action,
        section=section,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

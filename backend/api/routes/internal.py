"""
NB-50: the listener heartbeat seam (backend half, blueprint §2.7).

POST /internal/heartbeat — the ONLY listener signal; X-Internal-Service:
index-listener required (else 403). Upserts the single ListenerHeartbeat
row (id fixed 1); the payload is stored verbatim for the Overview's
per-signal derivation (D9 — the listener is HTTP-only).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ListenerHeartbeat

router = APIRouter()


@router.post("/internal/heartbeat")
def heartbeat_route(
    payload: dict,
    db: Session = Depends(get_db),
    x_internal_service: str | None = Header(None, alias="X-Internal-Service"),
):
    if x_internal_service != "index-listener":
        raise HTTPException(status_code=403, detail="Forbidden: internal service only")
    now = datetime.now(timezone.utc)
    row = db.get(ListenerHeartbeat, 1)
    if row is None:
        row = ListenerHeartbeat(id=1, last_seen_at=now, payload=payload)
        db.add(row)
    else:
        row.last_seen_at = now
        row.payload = payload
    db.commit()
    return {"status": "ok"}

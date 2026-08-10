"""
NB-50: the listener heartbeat seam (backend half, blueprint §2.7).
NB-55: the internal item fetch seam (blueprint §1.1) — the owner DM's
source for the full item picture (description, spec summary, gallery).

POST /internal/heartbeat — the ONLY listener signal; X-Internal-Service:
index-listener required (else 403). Upserts the single ListenerHeartbeat
row (id fixed 1); the payload is stored verbatim for the Overview's
per-signal derivation (D9 — the listener is HTTP-only).

GET /internal/items/{item_id} — same header gate; the ingestion response
carries no image/specs/description, so the Indexed/Updated DM fetches the
item's full details here. 404 when the item row is missing.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Item, ItemImage, ListenerHeartbeat

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


@router.get("/internal/items/{item_id}")
def internal_item_route(
    item_id: int,
    db: Session = Depends(get_db),
    x_internal_service: str | None = Header(None, alias="X-Internal-Service"),
):
    """NB-55: item details for the owner DM — same internal-header gate as
    the heartbeat. Returns the item plus its ItemImage gallery."""
    if x_internal_service != "index-listener":
        raise HTTPException(status_code=403, detail="Forbidden: internal service only")
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    images = [img.image_path for img in (item.images or [])]
    return {
        "id": item.id,
        "title": item.title,
        "price": item.price,
        "currency": item.currency,
        "description": item.description,
        "specs": item.specs,
        "category": item.category,
        "subcategory": item.subcategory,
        "image_path": item.image_path,
        "images": images,
    }

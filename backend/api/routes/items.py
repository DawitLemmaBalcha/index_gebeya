from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, func as sql_func

from database import get_db
from models import Item, Channel, SoldReport
from schemas import ItemResponse, SoldReportCreate, SoldReportResponse, ItemUpdateRequest, ItemStatusResponse
from schemas import BoostQuoteResponse, BoostOrderResponse, BoostCreditResponse, BoostStatusResponse
from services import search as search_service
from services.analytics import AnalyticsService
from services.auth import authenticate
from services.boost import (
    get_boost_price,
    get_boost_status,
    get_boost_eligibility,
    create_boost_order,
    fulfill_credit_boost,
)
from constants import BOOST_DURATION_DAYS, MONETIZATION_ENABLED
from services.item_status import (
    report_sold,
    relist_item as item_relist,
    mark_sold,
    clear_reports,
    update_item as update_item_service,
    delete_item,
)

router = APIRouter()


def _monetization_enabled_or_503():
    """Kill switch (blueprint §6.1): MONETIZATION_ENABLED=0 -> 503 at router level."""
    if not MONETIZATION_ENABLED:
        raise HTTPException(status_code=503, detail="Monetization is currently disabled")


def _require_boost_owner(db: Session, user, item_id: int) -> Item:
    """Ownership gate for the boost endpoints (Rule 2.5)."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can boost this item",
        )
    return item


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Return aggregate stats: product count, channel count, and per-category item counts."""
    product_count = db.execute(select(sql_func.count()).select_from(Item)).scalar()
    channel_count = db.execute(select(sql_func.count()).select_from(Channel)).scalar()

    # Per-category counts for the category grid
    category_rows = db.execute(
        select(Item.category, sql_func.count())
        .where(Item.category.isnot(None))
        .group_by(Item.category)
    ).all()
    category_counts = {cat: cnt for cat, cnt in category_rows}

    return {
        "product_count": product_count,
        "channel_count": channel_count,
        "category_counts": category_counts,
    }


@router.get("/recent", response_model=List[ItemResponse])
def get_recent_items(limit: int = 20, db: Session = Depends(get_db)):
    # TECH-22: Only return active items in recent feed
    stmt = (
        select(Item)
        .where(Item.status == "active")
        .order_by(Item.created_at.desc())
        .limit(limit)
    )
    items = db.scalars(stmt).all()
    return items


@router.get("/{item_id}", response_model=ItemResponse)
def read_item(
    item_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # --- ANALYTICS LOGGING ---
    user_id_header = request.headers.get("x-user-id")
    session_id = request.headers.get("x-session-id")
    user_id = int(user_id_header) if user_id_header and user_id_header.isdigit() else None

    background_tasks.add_task(
        AnalyticsService.log_interaction,
        user_id=user_id,
        session_id=session_id,
        interaction_type="view_item",
        item_id=item_id
    )
    # -------------------------

    # TECH-22: Inject report_count into the response
    report_count = db.scalar(
        select(sql_func.count(SoldReport.id)).where(SoldReport.item_id == item_id)
    )
    # Build response dict from the ORM item, then inject report_count
    response = ItemResponse.model_validate(item)
    response.report_count = report_count or 0
    return response


@router.get("/{item_id}/related", response_model=List[ItemResponse])
def get_related_items(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.image_vector is None:
        return []

    # Get search results
    search_result = search_service.perform_image_search(
        db=db,
        query_vector=item.image_vector,
        limit=6
    )

    # Handle Tuple Return
    if isinstance(search_result, tuple):
        raw_items = search_result[0]
    else:
        raw_items = search_result

    # Filter out the source item
    filtered_results = [r for r in raw_items if getattr(r, 'id', None) != item_id]

    # TECH-22: Only return active items as related
    filtered_results = [r for r in filtered_results if getattr(r, 'status', 'active') == 'active']

    return filtered_results


# =========================================================================
# TECH-22: POST /items/{item_id}/report — Report item as sold
# =========================================================================
@router.post("/{item_id}/report")
async def report_item_as_sold(
    item_id: int,
    body: SoldReportCreate,
    db: Session = Depends(get_db),
):
    """
    Crowdsourced sold-reporting. Any authenticated buyer can report a product
    as sold. When the report count reaches CROWDSOURCE_SOLD_THRESHOLD,
    the item status is set to 'reported_sold'.
    """
    user = authenticate(body.init_data, db)
    return await report_sold(db, item_id, user)


# =========================================================================
# TECH-22: POST /items/{item_id}/relist — Owner re-lists an item
# =========================================================================
@router.post("/{item_id}/relist")
async def relist_item(
    item_id: int,
    body: SoldReportCreate,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """
    Owner clears all SoldReports and resets status to 'active'.
    Supports the internal listener bypass (DM buttons).
    """
    user = authenticate(body.init_data, db, x_internal_service)
    return item_relist(db, item_id, user)


# =========================================================================
# TECH-23: PATCH /items/{item_id} — Update item with edit history audit log
# =========================================================================
@router.patch("/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: int,
    body: ItemUpdateRequest,
    init_data: str,
    db: Session = Depends(get_db),
):
    """
    Partially update an item owned by the authenticated user's channel.
    Logs all changes to item_edits for audit trail.
    Re-triggers alert matching when price or specs change.
    """
    user = authenticate(init_data, db)
    return update_item_service(db, item_id, user, body)


# =========================================================================
# TECH-23: POST /items/{item_id}/sold — Owner marks item as sold (authoritative)
# =========================================================================
@router.post("/{item_id}/sold", response_model=ItemStatusResponse)
def mark_item_sold(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """Owner-authoritative mark as sold. No confirmation needed, but reversible."""
    user = authenticate(init_data, db, x_internal_service)
    return mark_sold(db, item_id, user)


# =========================================================================
# TECH-23: POST /items/{item_id}/clear-reports — Clear reports without changing status
# =========================================================================
@router.post("/{item_id}/clear-reports", response_model=ItemStatusResponse)
def clear_item_reports(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """Delete all SoldReport records for this item without changing status."""
    user = authenticate(init_data, db, x_internal_service)
    return clear_reports(db, item_id, user)


# =========================================================================
# Owner-only: permanently delete an item from the catalog
# =========================================================================
@router.delete("/{item_id}")
def delete_item_route(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """Permanently delete an item owned by the authenticated user's channel."""
    user = authenticate(init_data, db, x_internal_service)
    return delete_item(db, item_id, user)


# =========================================================================
# NB-43: Boost purchase endpoints (blueprint §2.5) — price shown in context
# (Rule 2.4), never as a rate card.
# =========================================================================
@router.get("/{item_id}/boost-quote", response_model=BoostQuoteResponse)
def get_item_boost_quote(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
):
    """Owner-only quote: price for THIS item's category + active-boost status
    + boostability so the UI can hide the section for non-active items."""
    _monetization_enabled_or_503()
    user = authenticate(init_data, db)
    item = _require_boost_owner(db, user, item_id)
    status = get_boost_status(db, item_id)
    active_boost = BoostStatusResponse(**status) if status else None
    boostable, reason = get_boost_eligibility(db, item)
    return BoostQuoteResponse(
        price_stars=get_boost_price(db, item),
        duration_days=BOOST_DURATION_DAYS,
        category=item.category,
        active_boost=active_boost,
        boostable=boostable,
        reason=reason,
    )


@router.post("/{item_id}/boost-order", response_model=BoostOrderResponse)
async def create_item_boost_order(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
):
    """Owner-only: create a Stars invoice to boost this item (Rule 2.7)."""
    _monetization_enabled_or_503()
    user = authenticate(init_data, db)
    item = _require_boost_owner(db, user, item_id)
    return await create_boost_order(db, user, item)


@router.post("/{item_id}/boost-credit", response_model=BoostCreditResponse)
def create_item_credit_boost(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
):
    """Owner-only: consume one all-in-one monthly boost credit (Rule 7.3)."""
    _monetization_enabled_or_503()
    user = authenticate(init_data, db)
    item = _require_boost_owner(db, user, item_id)
    boost = fulfill_credit_boost(db, user, item)
    return BoostCreditResponse(boost=BoostStatusResponse(
        id=boost.id, active=True, ends_at=boost.ends_at, source=boost.source,
    ))

import os
import json
import logging
from typing import List
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, func as sql_func

from database import get_db
from models import Item, Channel, SoldReport, Notification, User, ItemEdit
from schemas import ItemResponse, SoldReportCreate, SoldReportResponse, ItemUpdateRequest, ItemStatusResponse
from services import search as search_service
from services.analytics import AnalyticsService
from services.alerting import process_new_item

router = APIRouter()
logger = logging.getLogger("index_items")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# ----------------------------------------------------------------------
# TECH-22: Auth helper — mirrors channels.py _auth_user_from_init_data
# ----------------------------------------------------------------------
def _auth_user_from_init_data(init_data: str, db: Session) -> User:
    """
    Parse Telegram WebApp initData to authenticate/identify the user.
    Returns the User object. Raises 403 if init_data is missing or invalid.
    """
    try:
        tg_id = None
        username = "unknown"

        if "user=" not in init_data:
            raise HTTPException(
                status_code=403,
                detail="Restricted: Valid Telegram init_data required."
            )

        parsed = parse_qs(init_data)
        if 'user' in parsed:
            user_json = parsed['user'][0]
            user_data = json.loads(user_json)
            tg_id = user_data.get('id')
            username = user_data.get('username', 'unknown')
        else:
            raise ValueError("init_data missing 'user' field")

        if not tg_id:
            raise ValueError("Could not extract Telegram ID from init_data")

        # Database Lookup or Auto-Create
        user = db.scalar(select(User).where(User.telegram_id == tg_id))

        if not user:
            user = User(telegram_id=tg_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)

        return user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail="Authentication Failed")


# ----------------------------------------------------------------------
# TECH-22: Owner DM helper — sends Telegram DM (best-effort)
# ----------------------------------------------------------------------
async def _send_owner_dm(db: Session, channel_id: int, message: str) -> None:
    """
    Send a DM to the channel owner via Telegram Bot API.
    Best-effort: logs warning on failure, never raises.
    """
    try:
        channel = db.get(Channel, channel_id)
        if not channel or channel.registered_by is None:
            return  # No owner to notify

        if not BOT_TOKEN:
            logger.warning("BOT_TOKEN not set, cannot send owner DM")
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": channel.registered_by, "text": message},
            )
            if resp.status_code != 200:
                logger.warning(f"⚠️ DM send failed for channel {channel_id}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"⚠️ DM notification exception for channel {channel_id}: {e}")


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
    from constants import CROWDSOURCE_SOLD_THRESHOLD

    # 1. Authenticate user
    user = _auth_user_from_init_data(body.init_data, db)

    # 2. Find item
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 3. Check ownership — owner cannot report their own item
    channel = db.get(Channel, item.channel_id)
    if channel and channel.registered_by and channel.registered_by == user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot report your own product"
        )

    # 4. Check duplicate report
    existing = db.scalar(
        select(SoldReport).where(
            SoldReport.user_id == user.id,
            SoldReport.item_id == item_id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already reported this as sold."
        )

    # 5. Create SoldReport
    report = SoldReport(user_id=user.id, item_id=item_id)
    db.add(report)
    db.commit()

    # 6. Count reports
    report_count = db.scalar(
        select(sql_func.count(SoldReport.id)).where(SoldReport.item_id == item_id)
    )

    # 7. Check threshold
    if report_count and report_count >= CROWDSOURCE_SOLD_THRESHOLD:
        if item.status == "active":
            item.status = "reported_sold"
            db.commit()

            # 8. Send owner DM
            channel_username = channel.username if channel else "unknown"
            msg = (
                f"⚠️ Your listing '{item.title}' on @{channel_username} "
                f"has been reported as sold by {report_count} buyers. "
                f"It has been hidden from search. "
                f"If this is incorrect, re-list it from your Stores tab."
            )
            await _send_owner_dm(db, item.channel_id, msg)

    return {"status": "reported", "report_count": report_count}


# =========================================================================
# TECH-22: POST /items/{item_id}/relist — Owner re-lists an item
# =========================================================================
@router.post("/{item_id}/relist")
async def relist_item(
    item_id: int,
    body: SoldReportCreate,
    db: Session = Depends(get_db),
):
    """
    Owner clears all SoldReports and resets status to 'active'.
    """
    # 1. Authenticate user
    user = _auth_user_from_init_data(body.init_data, db)

    # 2. Find item
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 3. Check ownership
    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can re-list this item"
        )

    # 4. Check if item was ever reported
    report_count = db.scalar(
        select(sql_func.count(SoldReport.id)).where(SoldReport.item_id == item_id)
    )

    if item.status == "active" and (report_count is None or report_count == 0):
        return {"status": "already_active", "message": "Item was never reported"}

    # 5. Delete all sold reports
    db.query(SoldReport).filter(SoldReport.item_id == item_id).delete()

    # 6. Reset status
    item.status = "active"
    db.commit()

    return {"status": "active", "message": "Item re-listed successfully"}


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
    user = _auth_user_from_init_data(init_data, db)

    # Find and verify ownership
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit items in your own channels"
        )

    # Edit history logging helper
    def _log_edit(field_name: str, old_val, new_val):
        """Log a field change to item_edits. No-op if values are equal."""
        if isinstance(old_val, dict):
            old_str = json.dumps(old_val, sort_keys=True) if old_val else None
        else:
            old_str = str(old_val) if old_val is not None else None

        if isinstance(new_val, dict):
            new_str = json.dumps(new_val, sort_keys=True) if new_val else None
        else:
            new_str = str(new_val) if new_val is not None else None

        if old_str == new_str:
            return

        edit = ItemEdit(
            item_id=item_id,
            field=field_name,
            old_value=old_str,
            new_value=new_str,
            edited_by=user.id,
        )
        db.add(edit)

    # Apply updates using exclude_unset
    update_data = body.model_dump(exclude_unset=True)
    needs_reprocess = False

    if "title" in update_data and body.title != item.title:
        _log_edit("title", item.title, body.title)
        item.title = body.title

    if "description" in update_data and body.description != item.description:
        _log_edit("description", item.description, body.description)
        item.description = body.description

    if "price" in update_data:
        if item.price is None or abs(body.price - item.price) > 0.001:
            _log_edit("price", item.price, body.price)
            item.price = body.price
            needs_reprocess = True

    if "category" in update_data and body.category != item.category:
        _log_edit("category", item.category, body.category)
        item.category = body.category

    if "subcategory" in update_data and body.subcategory != item.subcategory:
        _log_edit("subcategory", item.subcategory, body.subcategory)
        item.subcategory = body.subcategory

    if "specs" in update_data:
        old_specs = {}
        if item.specs:
            try:
                old_specs = json.loads(item.specs) if isinstance(item.specs, str) else item.specs
            except (json.JSONDecodeError, TypeError):
                old_specs = {}
        new_specs = body.specs or {}

        _log_edit("specs", old_specs, new_specs)
        item.specs = json.dumps(new_specs)
        needs_reprocess = True

    db.commit()
    db.refresh(item)

    # Re-trigger alert matching (Rule 3.3)
    if needs_reprocess:
        try:
            process_new_item(db, item.id)
        except Exception as e:
            logger.warning(f"Alert re-processing failed for item {item_id}: {e}")

    return item


# =========================================================================
# TECH-23: POST /items/{item_id}/sold — Owner marks item as sold (authoritative)
# =========================================================================
@router.post("/{item_id}/sold", response_model=ItemStatusResponse)
def mark_item_sold(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
):
    """Owner-authoritative mark as sold. No confirmation needed, but reversible."""
    user = _auth_user_from_init_data(init_data, db)

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can mark items as sold"
        )

    item.status = "sold"
    db.commit()

    return ItemStatusResponse(status="sold", message="Item marked as sold")


# =========================================================================
# TECH-23: POST /items/{item_id}/clear-reports — Clear reports without changing status
# =========================================================================
@router.post("/{item_id}/clear-reports", response_model=ItemStatusResponse)
def clear_item_reports(
    item_id: int,
    init_data: str,
    db: Session = Depends(get_db),
):
    """Delete all SoldReport records for this item without changing status."""
    user = _auth_user_from_init_data(init_data, db)

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can clear reports"
        )

    deleted = db.query(SoldReport).filter(SoldReport.item_id == item_id).delete()
    db.commit()

    return ItemStatusResponse(
        status=item.status,
        message=f"{deleted} report(s) cleared"
    )

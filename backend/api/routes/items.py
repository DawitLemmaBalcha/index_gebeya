from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from database import get_db
from models import Item, Channel
from schemas import ItemResponse
from services import search as search_service
from services.analytics import AnalyticsService

router = APIRouter()

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Return aggregate stats: product count, channel count, and per-category item counts."""
    product_count = db.execute(select(func.count()).select_from(Item)).scalar()
    channel_count = db.execute(select(func.count()).select_from(Channel)).scalar()

    # Per-category counts for the category grid
    category_rows = db.execute(
        select(Item.category, func.count())
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
    stmt = select(Item).order_by(Item.created_at.desc()).limit(limit)
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

    return item

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
            
    return filtered_results
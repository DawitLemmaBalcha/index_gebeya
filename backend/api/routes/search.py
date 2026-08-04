import os
import uuid
import shutil
import time
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request
from sqlalchemy.orm import Session

from database import get_db
from schemas import SearchQuery, SearchResponse, ItemResponse
from services import search as search_service
from services.analytics import AnalyticsService
from services.boost import get_pinned_boosted_items
from ai_engine.vector_client import vectorize_image

router = APIRouter()

@router.post("/", response_model=SearchResponse)
def search_items(
    query: SearchQuery, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    start_time = time.time()

    # --- NB-43 PIN LAYER (D7: the ONE application point) ---
    # Boosted items occupy the reserved top positions of the eligible
    # surfaces (category browse == POST /search/ with body.category, and
    # text searches matching title/category). Pinned items are excluded
    # from the organic list below (Rule 3.4 — no duplicates on a page).
    now = datetime.now(timezone.utc)
    pinned = get_pinned_boosted_items(
        db,
        category=(None if query.category in (None, "All") else query.category),
        query_text=query.query or None,
        now=now,
    )
    pinned_ids = {i.id for i in pinned}
    
    # Perform Search
    results_raw = search_service.perform_hybrid_search(
        db=db,
        query_text=query.query,
        limit=query.limit,
        min_price=query.min_price,
        max_price=query.max_price,
        category=query.category,
        exclude_unpriced=query.exclude_unpriced,
        exclude_item_ids=list(pinned_ids),
    )
    
    # Handle Tuple Return (items, count)
    if isinstance(results_raw, tuple):
        items_list = results_raw[0]
        total_count = results_raw[1] if len(results_raw) > 1 else len(items_list)
    else:
        items_list = results_raw
        total_count = len(items_list)

    # Mark boosted flags on the serialized organic items, then compose the
    # page: pinned (rotation order) followed by the organic slice.
    for item in items_list:
        item.is_boosted = item.id in pinned_ids

    pinned_responses = [ItemResponse.model_validate(i) for i in pinned]
    for item in pinned_responses:
        item.is_boosted = True
    page_items = pinned_responses + items_list

    execution_time = (time.time() - start_time) * 1000
    
    # --- ANALYTICS LOGGING ---
    user_id_header = request.headers.get("x-user-id")
    session_id = request.headers.get("x-session-id")
    user_id = int(user_id_header) if user_id_header and user_id_header.isdigit() else None

    background_tasks.add_task(
        AnalyticsService.log_interaction,
        user_id=user_id,
        session_id=session_id,
        interaction_type="search",
        item_id=None,
        meta_data={"query": query.query, "result_count": total_count}
    )
    # -------------------------
    
    return SearchResponse(
        items=page_items,
        total=total_count,
        execution_time_ms=execution_time
    )

@router.post("/by-image", response_model=List[ItemResponse])
async def search_by_image(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        # Save temp file
        file_ext = file.filename.split(".")[-1]
        temp_filename = f"{uuid.uuid4()}.{file_ext}"
        temp_path = os.path.join("/app/media/temp", temp_filename)
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        full_path = os.path.abspath(temp_path)
        img_vector = vectorize_image(full_path)
        os.remove(temp_path) # Cleanup
        
        if not img_vector:
            raise HTTPException(status_code=400, detail="Could not process image")

        results_raw = search_service.perform_image_search(db=db, query_vector=img_vector, limit=50)
        
        # --- ANALYTICS LOGGING ---
        user_id_header = request.headers.get("x-user-id")
        session_id = request.headers.get("x-session-id")
        user_id = int(user_id_header) if user_id_header and user_id_header.isdigit() else None

        background_tasks.add_task(
            AnalyticsService.log_interaction,
            user_id=user_id,
            session_id=session_id,
            interaction_type="image_search",
            item_id=None,
            meta_data={"filename": file.filename}
        )
        # -------------------------
        
        if isinstance(results_raw, tuple):
            return results_raw[0]
        
        return results_raw

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
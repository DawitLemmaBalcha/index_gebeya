import os
import uuid
import shutil
import time
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request
from sqlalchemy.orm import Session

from database import get_db
from schemas import SearchQuery, SearchResponse, ItemResponse
from services import search as search_service
from services.analytics import AnalyticsService
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
    
    # Perform Search
    results_raw = search_service.perform_hybrid_search(
        db=db,
        query_text=query.query,
        limit=query.limit
    )
    
    # Handle Tuple Return (items, count)
    if isinstance(results_raw, tuple):
        items_list = results_raw[0]
        total_count = results_raw[1] if len(results_raw) > 1 else len(items_list)
    else:
        items_list = results_raw
        total_count = len(items_list)

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
        items=items_list,
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
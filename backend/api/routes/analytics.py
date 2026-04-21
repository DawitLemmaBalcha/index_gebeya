from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from services.analytics import AnalyticsService

router = APIRouter()

# Local Schema Definition to avoid modifying global schemas.py prematurely
class EventCreate(BaseModel):
    event_type: str
    item_id: Optional[int] = None
    meta_data: Optional[Dict[str, Any]] = None

@router.post("/events")
async def track_event(
    event: EventCreate,
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint for Frontend to report generic events (clicks, dwells, etc.)
    """
    # Extract identity from headers
    user_id_header = request.headers.get("x-user-id")
    session_id = request.headers.get("x-session-id")
    
    # Validate User ID format
    user_id = None
    if user_id_header and user_id_header.isdigit():
        user_id = int(user_id_header)

    # Queue the log entry
    background_tasks.add_task(
        AnalyticsService.log_interaction,
        user_id=user_id,
        session_id=session_id,
        item_id=event.item_id,
        interaction_type=event.event_type,
        meta_data=event.meta_data
    )

    return {"status": "queued"}
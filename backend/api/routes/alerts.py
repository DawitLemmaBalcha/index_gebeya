from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timezone

from database import get_db
from models import Alert, Notification, Item
from schemas import AlertCreate, AlertResponse, MatchHistoryResponse
from services.alerting import create_alert
from services.analytics import AnalyticsService
from services.auth import authenticate
from constants import MAX_ALERTS_PER_USER

router = APIRouter()


@router.post("/", response_model=AlertResponse)
def create_new_alert(
    payload: AlertCreate, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None)
):
    """
    User creates an alert -> We vectorize it -> Save to DB.
    """
    # Pass header manually to helper
    user = authenticate(payload.init_data, db, x_internal_service)
    
    # --- Route-level max alerts guard ---
    if MAX_ALERTS_PER_USER > 0:
        active_count = db.scalar(
            select(func.count()).select_from(Alert).where(
                Alert.user_id == user.id,
                Alert.is_active == True
            )
        )
        if active_count >= MAX_ALERTS_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"You've reached the maximum of {MAX_ALERTS_PER_USER} active alerts. Pause or delete an existing alert to create a new one."
            )
    
    alert = create_alert(
        db=db,
        user=user,
        query_text=payload.query_text,
        max_price=payload.max_price,
        preferences=payload.preferences
    )

    # --- ANALYTICS LOGGING ---
    session_id = request.headers.get("x-session-id")

    background_tasks.add_task(
        AnalyticsService.log_interaction,
        user_id=user.id,
        session_id=session_id,
        interaction_type="create_alert",
        item_id=None,
        meta_data={
            "query": payload.query_text, 
            "max_price": payload.max_price,
            "preferences": payload.preferences
        }
    )
    # -------------------------
    
    return alert

@router.get("/", response_model=List[AlertResponse])
def list_my_alerts(
    init_data: str, 
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None)
):
    user = authenticate(init_data, db, x_internal_service)
    alerts = db.scalars(select(Alert).where(Alert.user_id == user.id, Alert.is_active == True)).all()
    return alerts

@router.delete("/{alert_id}")
def delete_alert(
    alert_id: int, 
    init_data: str, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None)
):
    user = authenticate(init_data, db, x_internal_service)
    alert = db.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_active = False
    alert.deleted_at = datetime.now(timezone.utc)  # TECH-25: retention lifecycle soft-delete marker
    db.commit()

    # --- ANALYTICS LOGGING ---
    session_id = request.headers.get("x-session-id")
    background_tasks.add_task(
        AnalyticsService.log_interaction,
        user_id=user.id,
        session_id=session_id,
        interaction_type="delete_alert",
        item_id=None,
        meta_data={"alert_id": alert_id}
    )
    # -------------------------

    return {"status": "deleted"}


# ----------------------------------------------------------------------
# TECH-17: PATCH /alerts/{alert_id}/pause — toggle is_active
# ----------------------------------------------------------------------
@router.patch("/{alert_id}/pause")
def toggle_alert_pause(
    alert_id: int,
    init_data: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None)
):
    """
    Toggle an alert's is_active status (pause/resume).
    Returns the new state.
    """
    user = authenticate(init_data, db, x_internal_service)
    alert = db.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Capture state before toggle
    was_active = alert.is_active

    # Toggle
    alert.is_active = not alert.is_active

    # Reset match counters on resume
    if was_active is False and alert.is_active is True:
        alert.total_matches = 0
        alert.bullseye_matches = 0
        logger = __import__('logging').getLogger("index_alerts")
        logger.info(f"🔄 Reset match counters for Alert {alert.id} on resume.")

    db.commit()
    db.refresh(alert)

    new_status = "resumed" if alert.is_active else "paused"

    # --- ANALYTICS LOGGING ---
    session_id = request.headers.get("x-session-id")
    background_tasks.add_task(
        AnalyticsService.log_interaction,
        user_id=user.id,
        session_id=session_id,
        interaction_type=f"alert_{new_status}",
        item_id=None,
        meta_data={"alert_id": alert_id, "new_state": alert.is_active}
    )
    # -------------------------

    return {"status": new_status, "is_active": alert.is_active}


# ----------------------------------------------------------------------
# TECH-17: GET /alerts/matches — match history for user's alerts
# ----------------------------------------------------------------------
@router.get("/matches", response_model=List[MatchHistoryResponse])
def get_alert_matches(
    init_data: str,
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None)
):
    """
    Returns recent match history (notifications) for the user's alerts.
    Sorted by created_at DESC, limit 50.
    """
    user = authenticate(init_data, db, x_internal_service)

    # Query notifications for this user, joined with alert and item
    notifications = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).all()

    result = []
    for notif in notifications:
        alert = db.scalar(select(Alert).where(Alert.id == notif.alert_id)) if notif.alert_id else None
        item = db.scalar(select(Item).where(Item.id == notif.item_id)) if notif.item_id else None

        result.append(MatchHistoryResponse(
            id=notif.id,
            alert_id=notif.alert_id,
            alert_query_text=alert.query_text if alert else None,
            match_tier=notif.match_tier,
            match_score=notif.match_score,
            item_title=item.title if item else None,
            item_price=item.price if item else None,
            item_image_path=item.image_path if item else None,
            item_id=notif.item_id,
            created_at=notif.created_at,
        ))

    return result
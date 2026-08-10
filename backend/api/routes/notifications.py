from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime

from database import get_db
from models import Notification, User
from schemas import NotificationResponse

router = APIRouter()

@router.get("/pending", response_model=List[NotificationResponse])
def get_pending_notifications(db: Session = Depends(get_db)):
    """
    Called by Listener (Poller) to get undelivered alerts.
    """
    # Join User to get telegram_id easily
    stmt = (
        select(Notification)
        .join(User)
        .where(Notification.status == "PENDING")
        .limit(50) # Batch size
    )
    notifications = db.scalars(stmt).all()
    
    # Enhance objects with user_telegram_id for Schema
    results = []
    for n in notifications:
        n.user_telegram_id = n.user.telegram_id
        results.append(n)
        
    return results

@router.post("/{notification_id}/ack")
def acknowledge_notification(notification_id: int, db: Session = Depends(get_db)):
    """
    Called by Listener after successful DM delivery.
    """
    notification = db.scalar(select(Notification).where(Notification.id == notification_id))
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.status = "SENT"
    notification.sent_at = datetime.utcnow()
    db.commit()
    
    return {"status": "acked"}


@router.post("/{notification_id}/fail")
def fail_notification(notification_id: int, db: Session = Depends(get_db)):
    """
    NB-57 (§3.4): the poller marks a notification FAILED after
    NOTIFICATION_FAILURE_LIMIT consecutive delivery failures — the honest
    dead-chat source the radar reads. PENDING → FAILED (200); any terminal
    state (SENT/REPLACED/FAILED) → 409. Unauthenticated, mirroring /ack
    (the poller is the machine caller).
    """
    notification = db.scalar(select(Notification).where(Notification.id == notification_id))
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot fail a {notification.status} notification",
        )
    notification.status = "FAILED"
    db.commit()
    return {"status": "failed"}
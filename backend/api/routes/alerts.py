import json
from urllib.parse import parse_qs
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional

from database import get_db
from models import Alert, User
from schemas import AlertCreate, AlertResponse
from services.alerting import create_alert
from services.analytics import AnalyticsService

router = APIRouter()

def get_current_user(
    init_data: str, 
    db: Session,
    x_internal_service: Optional[str] = Header(None)
):
    """
    Parses Telegram WebApp initData to authenticate/identify the user.
    STRICT MODE: Rejects 'user_id_placeholder' and plain integers UNLESS
    the request comes from the Internal Listener Service.
    """
    try:
        tg_id = None
        username = "unknown"
        
        # --- INTERNAL BYPASS ---
        # If the request comes from the index-listener (bot), we allow plain integer IDs.
        is_internal = (x_internal_service == "index-listener")

        if is_internal and init_data.isdigit():
            tg_id = int(init_data)
        
        # --- EXTERNAL (WEBAPP) STRICT CHECK ---
        else:
            # Valid Telegram WebApp data is a query string containing "user="
            if "user=" not in init_data:
                 raise HTTPException(
                     status_code=403, 
                     detail="Restricted: Alerts can only be managed from inside the Telegram Mini App."
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
             # Auto-register user on first action
             user = User(telegram_id=tg_id, username=username)
             db.add(user)
             db.commit()
             db.refresh(user)
        
        return user

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ Auth Failed: {str(e)}") # Print to docker logs for debugging
        raise HTTPException(status_code=403, detail="Authentication Failed: Telegram Identity Required")

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
    user = get_current_user(payload.init_data, db, x_internal_service)
    
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
    user = get_current_user(init_data, db, x_internal_service)
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
    user = get_current_user(init_data, db, x_internal_service)
    alert = db.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_active = False
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
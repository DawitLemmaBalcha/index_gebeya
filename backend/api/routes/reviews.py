import os
import hmac
import hashlib
import json
from typing import List
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Review, User, Channel
from schemas import ReviewCreate, ReviewResponse

# 👇 THIS IS THE KEY: It defines a ROUTER, not an APP 👇
router = APIRouter()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def validate_telegram_data(init_data: str) -> dict:
    """
    Validates the 'initData' string sent by the Mini App.
    """
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Server config error: Missing Bot Token")

    try:
        # 1. Parse query string into a dict
        data = dict(qc.split("=") for qc in unquote(init_data).split("&"))
        
        if "hash" not in data:
            raise ValueError("No hash found")

        received_hash = data.pop("hash")
        
        # 2. Sort keys alphabetically
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        
        # 3. Calculate HMAC-SHA256 Signature
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        # 4. Compare
        if calculated_hash != received_hash:
            raise ValueError("Invalid Signature")
            
        # 5. Extract User Data
        user_data = json.loads(data["user"])
        return user_data

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication Failed: {str(e)}")

@router.post("/", response_model=ReviewResponse)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    """
    Securely posts a review and updates the Channel's Trust Score.
    """
    # 1. Verify Identity (Cryptographic Check)
    tg_user = validate_telegram_data(payload.init_data)
    tg_id = tg_user.get("id")
    
    if not tg_id:
        raise HTTPException(status_code=400, detail="Invalid User Data")

    # 2. Get or Create User in DB
    user = db.query(User).filter(User.telegram_id == tg_id).first()
    if not user:
        user = User(
            telegram_id=tg_id,
            first_name=tg_user.get("first_name"),
            username=tg_user.get("username")
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 3. Check for Duplicate Review (One per channel per person)
    existing = db.query(Review).filter(
        Review.user_id == user.id,
        Review.channel_id == payload.channel_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="You have already reviewed this seller.")

    # 4. Save Review
    new_review = Review(
        user_id=user.id,
        channel_id=payload.channel_id,
        rating=payload.rating,
        comment=payload.comment
    )
    db.add(new_review)
    db.commit()

    # 5. Recalculate Trust Score (Math)
    stats = db.query(
        func.avg(Review.rating).label("average"),
        func.count(Review.id).label("count")
    ).filter(Review.channel_id == payload.channel_id).first()

    channel = db.query(Channel).filter(Channel.id == payload.channel_id).first()
    if channel and stats.average:
        channel.trust_score = round(float(stats.average), 1)
        channel.review_count = stats.count
        db.commit()

    db.refresh(new_review)
    return new_review

# 👇 NEW ENDPOINT: GET REVIEWS 👇
@router.get("/{channel_id}", response_model=List[ReviewResponse])
def get_reviews(channel_id: int, db: Session = Depends(get_db), limit: int = 10):
    """Fetch recent reviews for a specific channel"""
    return db.query(Review).filter(Review.channel_id == channel_id).order_by(Review.created_at.desc()).limit(limit).all()
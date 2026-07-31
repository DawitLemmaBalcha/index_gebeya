from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from database import get_db
from models import Review, User, Channel
from schemas import ReviewCreate, ReviewResponse
from services.auth import verify_init_data

# 👇 THIS IS THE KEY: It defines a ROUTER, not an APP 👇
router = APIRouter()

@router.post("/", response_model=ReviewResponse)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    """
    Securely posts a review and updates the Channel's Trust Score.
    """
    # 1. Verify Identity (Cryptographic Check)
    tg_user = verify_init_data(payload.init_data)
    tg_id = tg_user.get("id")
    photo_url = tg_user.get("photo_url")  # TECH-07: Capture user profile photo from initData
    
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
        comment=payload.comment,
        user_photo_url=photo_url
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
    reviews = db.query(Review).options(joinedload(Review.user)).filter(Review.channel_id == channel_id).order_by(Review.created_at.desc()).limit(limit).all()
    for r in reviews:
        r.user_name = r.user.first_name or r.user.username or "User"
    return reviews
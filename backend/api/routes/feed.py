from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from schemas import ItemResponse
from services.recommendation import build_feed

router = APIRouter()

@router.get("/foryou", response_model=List[ItemResponse])
def get_personalized_feed(
    request: Request,
    limit: int = 20,
    x_user_id: Optional[int] = Header(None),
    x_session_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Generates a personalized 'For You' feed based on the user's
    interaction history (Session or Long-Term).
    """
    
    # Priority: Authenticated User > Anonymous Session > Trending Fallback
    # The 'build_feed' service handles the logic of which ID to use.
    
    items = build_feed(
        db=db, 
        user_id=x_user_id, 
        session_id=x_session_id, 
        limit=limit
    )
    
    return items
from typing import Optional, Dict, Any
import json
from sqlalchemy.orm import Session
from database import SessionLocal  # Assumes SessionLocal is configured in database.py
from models import UserInteraction

class AnalyticsService:
    """
    Service for asynchronously logging user interactions and events.
    Uses its own DB session to ensure thread safety in BackgroundTasks.
    """

    @staticmethod
    def log_interaction(
        user_id: Optional[int],
        session_id: Optional[str],
        interaction_type: str,
        item_id: Optional[int] = None,
        meta_data: Optional[Dict[str, Any]] = None
    ):
        db: Session = SessionLocal()
        try:
            # Serialize metadata if provided
            meta_str = json.dumps(meta_data) if meta_data else None

            interaction = UserInteraction(
                user_id=user_id,
                session_id=session_id,
                item_id=item_id,
                interaction_type=interaction_type,
                meta_data=meta_str
            )
            
            db.add(interaction)
            db.commit()
            
        except Exception as e:
            # We log errors but do not crash the application for analytics failures
            print(f"[Analytics Error] Failed to log interaction: {e}")
            db.rollback()
        finally:
            db.close()
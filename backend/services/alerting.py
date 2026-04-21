import json
import logging
import re 
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Dict, Optional
import numpy as np

from models import Alert, Item, User, Notification
from ai_engine.matcher import evaluate_match, MatchTier
from ai_engine.vector_client import vectorize_text
from ai_engine.llm_client import verify_match_with_llm 

logger = logging.getLogger("suq_alerts")

def _normalize(s: str) -> str:
    """
    Local helper for strict identity checks.
    Removes all non-alphanumeric chars and lowercases.
    """
    if not s: return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())

def process_new_item(db: Session, item_id: int):
    """
    THE ORCHESTRATOR (Synchronous 3-Stage Pipeline)
    """
    try:
        # 1. Load the Item
        item = db.scalar(select(Item).where(Item.id == item_id))
        if not item or item.image_vector is None:
            logger.warning(f"⚠️ Alerting skipped: Item {item_id} invalid or no vector.")
            return

        # Handle vector conversion once
        if hasattr(item.image_vector, "tolist"):
            item_vec = item.image_vector.tolist()
        else:
            item_vec = list(item.image_vector)

        # 2. Load Active Alerts
        alerts = db.scalars(select(Alert).where(Alert.is_active == True)).all()
        logger.info(f"🔔 Checking Item {item_id} ('{item.title}' | {item.price} ETB) against {len(alerts)} active alerts.")
        
        matches_found = 0
        now_utc = datetime.now(timezone.utc)

        for alert in alerts:
            # -----------------------------------------------------------
            # PRE-CHECK: EXPIRY
            # -----------------------------------------------------------
            if alert.expires_at:
                expiry = alert.expires_at
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry < now_utc:
                    continue

            # -----------------------------------------------------------
            # PRE-CHECK: PRICE FILTER (GLOBAL)
            # -----------------------------------------------------------
            # Updated to Log EVERYTHING
            if alert.max_price is not None and item.price is not None:
                if item.price > alert.max_price:
                    logger.info(f"💰 Price Mismatch: Alert {alert.id} Max({alert.max_price}) < Item({item.price}) | STOP")
                    continue
                else:
                    logger.info(f"💰 Price Pass: Alert {alert.id} Max({alert.max_price}) >= Item({item.price})")
            
            elif alert.max_price is None:
                logger.info(f"💰 Price Check Skipped: Alert {alert.id} is set to 'Any Price'.")
            
            elif item.price is None:
                logger.info(f"💰 Price Check Skipped: Item {item.id} has no price listed.")

            # Prepare Alert Vector
            if hasattr(alert.query_vector, "tolist"):
                alert_vec = alert.query_vector.tolist()
            else:
                alert_vec = list(alert.query_vector)

            # -----------------------------------------------------------
            # STAGE 1: IDENTITY CHECK ("Speed Pass")
            # -----------------------------------------------------------
            norm_query = _normalize(alert.query_text)
            norm_title = _normalize(item.title)
            
            # Ensure query is substantial (>3 chars)
            is_identity_match = (len(norm_query) > 3) and (norm_query == norm_title)

            should_notify = False
            result = None

            if is_identity_match:
                logger.info(f"⚡ Identity Match: '{norm_query}' == '{norm_title}' | SPEED PASS GRANTED")
                
                # Mock a result for consistency
                result = evaluate_match(
                    item_vector=item_vec,
                    alert_vector=alert_vec,
                    item_price=item.price,
                    alert_max_price=alert.max_price,
                    item_title=item.title,
                    alert_query_text=alert.query_text 
                )
                
                should_notify = True
                is_verified = True
            
            else:
                logger.info(f"🔍 Identity Mismatch: '{norm_query}' != '{norm_title}' | Proceeding to Hybrid Matcher")

                # -------------------------------------------------------
                # STAGE 2: CANDIDATE GENERATION (Vectors/Trigrams)
                # -------------------------------------------------------
                result = evaluate_match(
                    item_vector=item_vec,
                    alert_vector=alert_vec,
                    item_price=item.price,
                    alert_max_price=alert.max_price,
                    item_title=item.title,
                    alert_query_text=alert.query_text 
                )
                
                if result.tier == MatchTier.MISS:
                    logger.info(f"👋 Hybrid Miss: Alert {alert.id} Score {result.score:.3f} too low. Stopping.")
                    continue
                else:
                    logger.info(f"📊 Hybrid Candidate: Alert {alert.id} -> Tier: {result.tier.value} | Score: {result.score:.3f}")

                # -------------------------------------------------------
                # STAGE 3: THE JUDGE (Universal LLM Verification)
                # -------------------------------------------------------
                preferences = json.loads(alert.preferences) if alert.preferences else {}
                
                logger.info(f"⚖️ Invoking LLM Judge for Alert {alert.id}...")
                is_verified = verify_match_with_llm(item.title, alert.query_text, preferences)

                if not is_verified:
                    logger.info(f"🛑 LLM Rejected: '{alert.query_text}' vs '{item.title}'")
                    continue
                else:
                    logger.info(f"✅ LLM Approved: '{alert.query_text}' vs '{item.title}'")

                # Determine notification eligibility
                if result.tier == MatchTier.BULLSEYE:
                    should_notify = True
                    if result.score > alert.best_opportunity_score:
                        alert.best_opportunity_score = result.score
                
                elif result.tier == MatchTier.RING:
                    tolerance = 0.05
                    if result.score >= (alert.best_opportunity_score - tolerance):
                        should_notify = True
                    else:
                        logger.info(f"📉 Ring Match Suppressed: Score {result.score:.3f} < High Water Mark {alert.best_opportunity_score:.3f}")

            # -----------------------------------------------------------
            # FINAL: DISPATCH
            # -----------------------------------------------------------
            if should_notify:
                matches_found += 1
                logger.info(f"🎯 MATCH CONFIRMED! Alert {alert.id} | Tier: {result.tier.value if result else 'SPEED_PASS'}")
                
                alert.last_triggered_at = now_utc
                _dispatch_notification(db, alert.user_id, alert.id, item, result)
        
        db.commit()
        logger.info(f"🏁 Item Processing Complete. Total Matches: {matches_found}")

    except Exception as e:
        logger.error(f"❌ Alert Orchestrator Failed: {str(e)}")

# ... (rest of file: create_alert, _dispatch_notification)
def create_alert(db: Session, user: User, query_text: str, max_price: Optional[float], preferences: Dict):
    vector = vectorize_text(query_text)
    if hasattr(vector, "tolist"):
        vector = vector.tolist()

    expires_at = datetime.now(timezone.utc) + timedelta(days=14)

    new_alert = Alert(
        user_id=user.id,
        query_text=query_text,
        query_vector=vector,
        max_price=max_price,
        preferences=json.dumps(preferences),
        best_opportunity_score=0.0,
        expires_at=expires_at 
    )
    
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    return new_alert

def _dispatch_notification(db: Session, user_id: int, alert_id: int, item: Item, match_result):
    notification = Notification(
        user_id=user_id,
        item_id=item.id,
        alert_id=alert_id,
        match_tier=match_result.tier.value,
        match_score=match_result.score,
        status="PENDING"
    )
    db.add(notification)
    logger.info(f"📨 [SAVED] Notification for User {user_id} queued.")
import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List, Dict, Optional
import numpy as np

from models import Alert, Item, User, Notification
from ai_engine.matcher import evaluate_match, MatchTier
from ai_engine.vector_client import vectorize_text
from ai_engine.llm_client import verify_match_with_llm, JudgeVerdict
from constants import (
    MAX_ALERTS_PER_USER,
    MAX_MATCHES_BEFORE_PAUSE,
    MAX_BULLSEYE_BEFORE_PAUSE,
    NOTIFICATION_THROTTLE_SECONDS,
    ALERT_LIFESPAN_DAYS,
    RING_TOLERANCE,
)
from services.ban import is_banned  # NB-56 Rule 3.2: the alert-creation seam
from services.subscriptions import get_effective_alert_cap  # NB-46 (D3): the single cap authority

logger = logging.getLogger("index_alerts")

# NB-20: LLM judge fail-open observability (process-local; no DB table —
# acceptable for v1 per the architect). Reset on API restart.
JUDGE_ERROR_COUNT = 0
JUDGE_ERROR_LAST_TS = None  # UTC datetime or None

def _create_system_notification(db: Session, user_id: int, alert_id: int, message: str, tier: str) -> None:
    """
    Creates a Notification with no item for system DMs (auto-pause, expiry).
    The Listener's notification poller will detect message_text and format accordingly.
    """
    notification = Notification(
        user_id=user_id,
        item_id=None,
        alert_id=alert_id,
        match_tier=tier,
        match_score=0.0,
        status="PENDING",
        message_text=message,
    )
    db.add(notification)
    logger.info(f"📨 [SAVED] System DM for User {user_id} queued: {tier}")

def process_new_item(db: Session, item_id: int):
    """
    THE ORCHESTRATOR (Synchronous 3-Stage Pipeline)
    """
    try:
        # 1. Load the Item
        item = db.scalar(select(Item).where(Item.id == item_id))
        if not item:
            logger.warning(f"⚠️ Alerting skipped: Item {item_id} not found.")
            return

        # Handle vector conversion (may be None for text-only posts)
        item_vec = None
        if item.image_vector is not None:
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
            # PRE-CHECK GATES (expiry + price filter)
            # -----------------------------------------------------------
            if _precheck_gates(db, alert, item, now_utc):
                continue

            # Prepare Alert Vector
            if hasattr(alert.query_vector, "tolist"):
                alert_vec = alert.query_vector.tolist()
            else:
                alert_vec = list(alert.query_vector)

            # -----------------------------------------------------------
            # SINGLE MATCHING COMPUTATION (Speed Pass + Hybrid)
            # -----------------------------------------------------------
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

            # -----------------------------------------------------------
            # CONDITIONAL LLM JUDGE
            # Deterministic speed passes (containment) skip Stage 2/3 entirely
            # (behavior doc Rule 3.1 — "Consequence of Speed Pass").
            # -----------------------------------------------------------
            if not result.speed_pass:
                preferences = json.loads(alert.preferences) if alert.preferences else {}
                
                logger.info(f"⚖️ Invoking LLM Judge for Alert {alert.id}...")
                verdict = verify_match_with_llm(item.title, alert.query_text, preferences)

                if verdict is JudgeVerdict.REJECTED:
                    logger.info(f"🛑 LLM Rejected: '{alert.query_text}' vs '{item.title}'")
                    continue

                if verdict is JudgeVerdict.ERRORED:
                    # NB-20: fail-open — same dispatch outcome as the legacy
                    # exception→True path, but counted + timestamped for ops.
                    global JUDGE_ERROR_COUNT, JUDGE_ERROR_LAST_TS
                    JUDGE_ERROR_COUNT += 1
                    JUDGE_ERROR_LAST_TS = datetime.now(timezone.utc)
                    logger.warning(f"⚠️ LLM Judge errored — fail-open: '{alert.query_text}' vs '{item.title}'")
                elif verdict is JudgeVerdict.APPROVED:
                    logger.info(f"✅ LLM Approved: '{alert.query_text}' vs '{item.title}'")
                else:
                    # Defensive: a non-enum return (stale mock, future drift)
                    # fails CLOSED — never dispatch on an unknown verdict.
                    logger.warning(f"⚠️ LLM Judge returned unknown verdict {verdict!r} — skipping")
                    continue

            # -----------------------------------------------------------
            # DISPATCH DECISION
            # -----------------------------------------------------------
            should_notify = _dispatch_decision(result, alert)

            # -----------------------------------------------------------
            # GUARDRAILS (throttle + duplicate suppression)
            # -----------------------------------------------------------
            should_notify = _apply_guardrails(db, alert, item, result, now_utc, should_notify)

            # -----------------------------------------------------------
            # FINAL DISPATCH + COUNTERS + AUTO-PAUSE
            # -----------------------------------------------------------
            if should_notify:
                matches_found += 1
                tier_value = result.tier.value
                logger.info(f"🎯 MATCH CONFIRMED! Alert {alert.id} | Tier: {tier_value}")
                
                alert.last_triggered_at = now_utc
                _dispatch_notification(db, alert.user_id, alert.id, item, result)

                _apply_auto_pause(db, alert, item, result)
        
        db.commit()
        logger.info(f"🏁 Item Processing Complete. Total Matches: {matches_found}")

    except Exception as e:
        logger.error(f"❌ Alert Orchestrator Failed: {str(e)}")

def _precheck_gates(db: Session, alert: Alert, item: Item, now_utc) -> bool:
    """
    Returns True when the alert must be skipped (expired or price-rejected),
    False otherwise. Reproduces the expiry gate (deactivate + system DM + log)
    and the price gate (logs; no-price passes) exactly.
    """
    # -----------------------------------------------------------
    # PRE-CHECK: EXPIRY
    # -----------------------------------------------------------
    if alert.expires_at:
        expiry = alert.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < now_utc:
            alert.is_active = False
            _create_system_notification(
                db, alert.user_id, alert.id,
                f"⏰ Your alert for '{alert.query_text}' has expired. Create a new one anytime.",
                "system_expiry"
            )
            logger.info(f"⌛ Expired Alert {alert.id}, DM sent.")
            return True

    # -----------------------------------------------------------
    # PRE-CHECK: PRICE FILTER (GLOBAL)
    # -----------------------------------------------------------
    # Updated to Log EVERYTHING
    if alert.max_price is not None and item.price is not None:
        if item.price > alert.max_price:
            logger.info(f"💰 Price Mismatch: Alert {alert.id} Max({alert.max_price}) < Item({item.price}) | STOP")
            return True
        else:
            logger.info(f"💰 Price Pass: Alert {alert.id} Max({alert.max_price}) >= Item({item.price})")
    
    elif alert.max_price is None:
        logger.info(f"💰 Price Check Skipped: Alert {alert.id} is set to 'Any Price'.")
    
    elif item.price is None:
        logger.info(f"💰 Price Check Skipped: Item {item.id} has no price listed.")

    return False

def _dispatch_decision(result, alert: Alert) -> bool:
    """
    Decides whether the match is worth notifying about:
    BULLSEYE always dispatches (and raises the high water mark),
    RING dispatches only within tolerance of the high water mark.
    """
    if result.tier == MatchTier.BULLSEYE:
        if result.score > alert.best_opportunity_score:
            alert.best_opportunity_score = result.score
        return True
    
    elif result.tier == MatchTier.RING:
        tolerance = RING_TOLERANCE
        if result.score >= (alert.best_opportunity_score - tolerance):
            return True
        else:
            logger.info(f"📉 Ring Match Suppressed: Score {result.score:.3f} < High Water Mark {alert.best_opportunity_score:.3f}")
            return False

    return False

def _apply_guardrails(db: Session, alert: Alert, item: Item, result, now_utc, should_notify: bool) -> bool:
    """
    Applies the TECH-20 guardrails: ring-only throttle (bullseye bypasses)
    then duplicate suppression. Returns the final decision.
    """
    # --- Throttle Check (Ring only; Bullseye bypasses) ---
    if should_notify and result.tier == MatchTier.RING and NOTIFICATION_THROTTLE_SECONDS > 0:
        if alert.last_triggered_at is not None:
            elapsed = (now_utc - alert.last_triggered_at).total_seconds()
            if elapsed < NOTIFICATION_THROTTLE_SECONDS:
                logger.info(f"⏱️ Throttled: Alert {alert.id} within cooldown window.")
                should_notify = False

    if not should_notify:
        return False

    # --- Duplicate Suppression ---
    if item.is_dedup:
        # For dedup replacements: suppress if alert already fired for ANY item
        # from this channel within the last hour. First repost (after original
        # aged out) notifies; rapid subsequent reposts don't.
        one_hour_ago = now_utc - timedelta(hours=1)
        existing_from_channel = db.scalar(
            select(Notification.id).join(Item, Notification.item_id == Item.id).where(
                Notification.alert_id == alert.id,
                Item.channel_id == item.channel_id,
                Notification.created_at >= one_hour_ago,
                Notification.item_id != item.id
            ).limit(1)
        )
        if existing_from_channel is not None:
            logger.info(f"🔁 Dedup suppressed: Alert {alert.id} already notified from channel {item.channel_id}.")
            should_notify = False
    else:
        # Normal items: suppress if same alert+item already notified
        existing = db.scalar(
            select(Notification).where(
                Notification.alert_id == alert.id,
                Notification.item_id == item.id
            ).limit(1)
        )
        if existing is not None:
            logger.info(f"🔁 Duplicate suppressed: Alert {alert.id} already notified for Item {item.id}.")
            should_notify = False

    return should_notify

def _apply_auto_pause(db: Session, alert: Alert, item: Item, result) -> None:
    """
    Updates match counters (skipped for dedup replacements) and applies the
    auto-pause check: bullseye limit takes priority, then total limit.
    Each pause emits its system_pause DM.
    """
    # --- Match Counter — skip for dedup replacements ---
    if not item.is_dedup:
        alert.total_matches += 1
        if result.tier == MatchTier.BULLSEYE:
            alert.bullseye_matches += 1

    # --- Auto-Pause Check ---
    # Bullseye limit takes priority
    if MAX_BULLSEYE_BEFORE_PAUSE > 0 and alert.bullseye_matches >= MAX_BULLSEYE_BEFORE_PAUSE:
        alert.is_active = False
        _create_system_notification(
            db, alert.user_id, alert.id,
            f"🎯 Your alert for '{alert.query_text}' found {MAX_BULLSEYE_BEFORE_PAUSE} exact matches and has been paused. You probably already found what you need.",
            "system_pause"
        )
        logger.info(f"⏸️ Auto-paused Alert {alert.id} after {MAX_BULLSEYE_BEFORE_PAUSE} bullseye matches.")
    elif MAX_MATCHES_BEFORE_PAUSE > 0 and alert.total_matches >= MAX_MATCHES_BEFORE_PAUSE:
        alert.is_active = False
        _create_system_notification(
            db, alert.user_id, alert.id,
            f"🔕 Your alert for '{alert.query_text}' has been paused after {MAX_MATCHES_BEFORE_PAUSE} matches. Resume it anytime in the Alerts tab.",
            "system_pause"
        )
        logger.info(f"⏸️ Auto-paused Alert {alert.id} after {MAX_MATCHES_BEFORE_PAUSE} total matches.")

def create_alert(db: Session, user: User, query_text: str, max_price: Optional[float], preferences: Dict):
    # NB-56 (Rule 3.2): banned buyers cannot create alerts — the seam at the
    # service level covers the route and every caller.
    if is_banned(db, user):
        raise HTTPException(status_code=403, detail="Account banned")

    # --- Max Alerts Per User Check (NB-46 D3: effective cap = free + subscription extra) ---
    cap = get_effective_alert_cap(db, user)
    if cap > 0:
        active_count = db.scalar(
            select(func.count()).select_from(Alert).where(
                Alert.user_id == user.id,
                Alert.is_active == True
            )
        )
        if active_count >= cap:
            raise HTTPException(
                status_code=400,
                detail=f"You've reached the maximum of {cap} active alerts. Pause or delete an existing alert to create a new one."
            )

    vector = vectorize_text(query_text)
    if hasattr(vector, "tolist"):
        vector = vector.tolist()

    expires_at = datetime.now(timezone.utc) + timedelta(days=ALERT_LIFESPAN_DAYS)

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

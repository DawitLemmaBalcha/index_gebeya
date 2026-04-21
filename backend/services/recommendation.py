import numpy as np
import logging
import json
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, or_
from typing import List, Dict, Any
from datetime import datetime, timedelta

from models import Item, UserInteraction
from database import engine

# --- LOGGER SETUP ---
logger = logging.getLogger("suq_api")
# --------------------

# Configuration
VECTOR_DIM = 512
HISTORY_WINDOW_DISCOVERY = 50  # Look at last 50 items for Category Profile
HISTORY_WINDOW_SESSION = 5     # Look at last 5 items for Immediate Intent

def _parse_vector(vec_data) -> np.ndarray:
    """Helper to ensure vector is a numpy array."""
    if vec_data is None:
        return np.zeros(VECTOR_DIM)
    if isinstance(vec_data, str):
        try:
            vec_data = json.loads(vec_data)
        except:
            return np.zeros(VECTOR_DIM)
    return np.array(vec_data, dtype=np.float32)

def get_recent_items(db: Session, limit: int = 10) -> List[Item]:
    """Fallback: Just the latest items."""
    logger.info(f"🧠 [FALLBACK] Fetching {limit} recent items.")
    return db.scalars(
        select(Item).order_by(Item.created_at.desc()).limit(limit)
    ).all()

def get_trending_items(db: Session, limit: int = 10) -> List[Item]:
    """
    Items with most interactions in the last 24h.
    Falls back to Recent Items if no data.
    """
    yesterday = datetime.utcnow() - timedelta(hours=24)
    
    stmt = (
        select(UserInteraction.item_id, func.count(UserInteraction.item_id).label("count"))
        .where(UserInteraction.created_at >= yesterday)
        .where(UserInteraction.item_id != None)
        .group_by(UserInteraction.item_id)
        .order_by(desc("count"))
        .limit(limit)
    )
    
    results = db.execute(stmt).all()
    item_ids = [r[0] for r in results]
    
    if not item_ids:
        logger.info("🧠 [TRENDING] No trending data found. Fallback to Recent.")
        return get_recent_items(db, limit)
        
    items = db.scalars(select(Item).where(Item.id.in_(item_ids))).all()
    items_map = {i.id: i for i in items}
    sorted_items = [items_map[iid] for iid in item_ids if iid in items_map]
    
    if len(sorted_items) < limit:
        needed = limit - len(sorted_items)
        extras = get_recent_items(db, needed)
        existing_ids = set(item_ids)
        for ex in extras:
            if ex.id not in existing_ids:
                sorted_items.append(ex)

    logger.info(f"🧠 [TRENDING] Returning {len(sorted_items)} trending items.")
    return sorted_items

def get_session_feed(db: Session, interactions: List[UserInteraction], limit: int = 5) -> List[Item]:
    """
    Calculates the 'Session Vector' (Mean of last N items) and finds similar items.
    """
    recent_interactions = interactions[:HISTORY_WINDOW_SESSION]
    item_ids = [i.item_id for i in recent_interactions if i.item_id]
    
    if not item_ids:
        return []

    source_items = db.scalars(select(Item).where(Item.id.in_(item_ids))).all()
    if not source_items:
        return []

    vectors = [_parse_vector(item.image_vector) for item in source_items]
    if not vectors:
        return []
    
    mean_vector = np.mean(vectors, axis=0)
    
    logger.info(f"🧠 [SESSION] Averaging {len(vectors)} items -> Generating Context Vector.")
    
    query = (
        select(Item)
        .where(Item.id.not_in(item_ids))
        .order_by(Item.image_vector.l2_distance(mean_vector))
        .limit(limit)
    )
    
    results = db.scalars(query).all()
    logger.info(f"🧠 [SESSION] Found {len(results)} items similar to current context.")
    return results

def get_discovery_feed(db: Session, interactions: List[UserInteraction], total_limit: int = 10) -> List[Item]:
    """
    Multi-Modal Discovery: Weighted Category Vectors.
    """
    if not interactions:
        return []

    history_ids = [i.item_id for i in interactions if i.item_id]
    if not history_ids:
        return []
    
    history_items = db.scalars(select(Item).where(Item.id.in_(history_ids))).all()
    item_map = {i.id: i for i in history_items}
    
    category_buckets = {}
    for interaction in interactions:
        if interaction.item_id in item_map:
            item = item_map[interaction.item_id]
            if not item.category: continue
            
            if item.category not in category_buckets:
                category_buckets[item.category] = []
            category_buckets[item.category].append(item)

    if not category_buckets:
        return []

    sorted_cats = sorted(category_buckets.items(), key=lambda x: len(x[1]), reverse=True)
    top_cats = sorted_cats[:3]
    total_weight = sum([len(items) for cat, items in top_cats])
    
    results = []
    
    logger.info(f"🧠 [DISCOVERY] Profile: {[cat for cat, _ in top_cats]}")

    for category, items in top_cats:
        weight = len(items) / total_weight
        limit_for_cat = max(1, int(round(weight * total_limit)))
        
        vectors = [_parse_vector(i.image_vector) for i in items]
        mean_vector = np.mean(vectors, axis=0)
        
        seen_ids = [i.id for i in items]
        
        sub_query = (
            select(Item)
            .where(Item.category == category)
            .where(Item.id.not_in(seen_ids))
            .order_by(Item.image_vector.l2_distance(mean_vector))
            .limit(limit_for_cat)
        )
        
        cat_recommendations = db.scalars(sub_query).all()
        logger.info(f"   -> Category '{category}' ({int(weight*100)}%): Fetched {len(cat_recommendations)} items.")
        results.extend(cat_recommendations)

    return results

def build_feed(db: Session, user_id: int = None, session_id: str = None, limit: int = 20) -> List[Item]:
    """
    The Orchestrator.
    Decides the mix ratio based on user maturity (Interaction Count).
    """
    
    query = select(UserInteraction).where(UserInteraction.item_id != None).order_by(UserInteraction.created_at.desc())
    
    if user_id:
        query = query.where(UserInteraction.user_id == user_id)
        id_log = f"User {user_id}"
    elif session_id:
        query = query.where(UserInteraction.session_id == session_id)
        id_log = f"Session {session_id}"
    else:
        logger.info("🧠 [FEED] Anonymous Request (No ID). Returning Trending.")
        return get_trending_items(db, limit)

    all_interactions = db.scalars(query.limit(HISTORY_WINDOW_DISCOVERY)).all()
    count = len(all_interactions)
    
    logger.info(f"🧠 [FEED] Building Feed for {id_log} | History: {count} items")
    
    feed_items = []
    
    # STATE A: COLD START
    if count < 3:
        logger.info("🧠 [STATE] COLD START -> 100% Trending")
        return get_trending_items(db, limit)
        
    # STATE B: EXPLORER
    elif count <= 10:
        logger.info("🧠 [STATE] EXPLORER -> 70% Session | 30% Trending")
        limit_session = int(limit * 0.7)
        limit_trending = limit - limit_session
        
        feed_items.extend(get_session_feed(db, all_interactions, limit_session))
        feed_items.extend(get_trending_items(db, limit_trending))
        
    # STATE C: REGULAR
    else:
        logger.info("🧠 [STATE] REGULAR -> 40% Session | 40% Discovery | 20% Trending")
        limit_session = int(limit * 0.4)
        limit_discovery = int(limit * 0.4)
        limit_trending = limit - limit_session - limit_discovery
        
        feed_items.extend(get_session_feed(db, all_interactions, limit_session))
        feed_items.extend(get_discovery_feed(db, all_interactions, limit_discovery))
        feed_items.extend(get_trending_items(db, limit_trending))

    # DEDUPLICATION
    seen = set()
    unique_feed = []
    
    for item in feed_items:
        if item.id not in seen:
            unique_feed.append(item)
            seen.add(item.id)
            
    if len(unique_feed) < limit:
        needed = limit - len(unique_feed)
        logger.info(f"🧠 [FEED] Deduplication removed items. Backfilling {needed} from Trending.")
        extras = get_trending_items(db, limit)
        for item in extras:
            if item.id not in seen:
                unique_feed.append(item)
                seen.add(item.id)
                if len(unique_feed) >= limit: break

    return unique_feed[:limit]
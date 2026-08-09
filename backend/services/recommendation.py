import numpy as np
import logging
import json
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, or_
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from models import Item, UserInteraction
from database import engine

# --- LOGGER SETUP ---
logger = logging.getLogger("index_api")
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

def get_recent_items(db: Session, limit: int = 10, exclude_ids: set = set()) -> List[Item]:
    """Fallback: Just the latest items."""
    logger.info(f"🧠 [FALLBACK] Fetching {limit} recent items.")
    results = db.scalars(
        select(Item)
        .where(Item.status == "active")
        .order_by(Item.created_at.desc())
        .limit(limit + len(exclude_ids))
    ).all()
    # Filter out excluded IDs
    results = [item for item in results if item.id not in exclude_ids]
    return results[:limit]

def get_trending_items(db: Session, limit: int = 10, exclude_ids: set = set()) -> List[Item]:
    """
    Items with most interactions in the last 24h.
    Falls back to Recent Items if no data.
    """
    yesterday = datetime.utcnow() - timedelta(hours=24)
    
    # Fetch extra to account for excluded IDs
    fetch_limit = limit + len(exclude_ids)
    
    stmt = (
        select(UserInteraction.item_id, func.count(UserInteraction.item_id).label("count"))
        .where(UserInteraction.created_at >= yesterday)
        .where(UserInteraction.item_id != None)
        .group_by(UserInteraction.item_id)
        .order_by(desc("count"))
        .limit(fetch_limit)
    )
    
    results = db.execute(stmt).all()
    item_ids = [r[0] for r in results if r[0] not in exclude_ids]
    
    if not item_ids:
        logger.info("🧠 [TRENDING] No trending data found. Fallback to Recent.")
        return get_recent_items(db, limit, exclude_ids)
        
    items = db.scalars(
        select(Item)
        .where(Item.id.in_(item_ids))
        .where(Item.status == "active")
    ).all()
    items_map = {i.id: i for i in items}
    sorted_items = [items_map[iid] for iid in item_ids if iid in items_map]
    
    if len(sorted_items) < limit:
        needed = limit - len(sorted_items)
        # The recent backfill must exclude the already-queried ids: without
        # them, the fetch skips already-included items and under-fills the
        # page (user-verified: a 40-item catalog yielded a 15-item first
        # page -> frontend hasMore=false and scrolling stopped).
        existing_ids = set(item_ids)
        extras = get_recent_items(db, needed, exclude_ids | existing_ids)
        for ex in extras:
            if ex.id not in existing_ids:
                sorted_items.append(ex)

    logger.info(f"🧠 [TRENDING] Returning {len(sorted_items)} trending items.")
    return sorted_items

def get_session_feed(db: Session, interactions: List[UserInteraction], limit: int = 5, exclude_ids: set = set()) -> List[Item]:
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
        .where(Item.status == "active")
        .order_by(Item.image_vector.l2_distance(mean_vector))
        .limit(limit + len(exclude_ids))
    )
    
    results = db.scalars(query).all()
    # Filter out excluded IDs
    results = [item for item in results if item.id not in exclude_ids]
    results = results[:limit]
    logger.info(f"🧠 [SESSION] Found {len(results)} items similar to current context.")
    return results

def get_discovery_feed(db: Session, interactions: List[UserInteraction], total_limit: int = 10, exclude_ids: set = set()) -> List[Item]:
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
        # Merge exclude_ids into seen_ids for the query
        query_exclude_ids = set(seen_ids) | exclude_ids
        
        sub_query = (
            select(Item)
            .where(Item.category == category)
            .where(Item.status == "active")
            .where(Item.id.not_in(query_exclude_ids))
            .order_by(Item.image_vector.l2_distance(mean_vector))
            .limit(limit_for_cat)
        )
        
        cat_recommendations = db.scalars(sub_query).all()
        logger.info(f"   -> Category '{category}' ({int(weight*100)}%): Fetched {len(cat_recommendations)} items.")
        results.extend(cat_recommendations)

    return results

def get_wildcard_feed(db: Session, interactions: List[UserInteraction], limit: int = 10, exclude_ids: set = set()) -> List[Item]:
    """
    Pulls trending items from the user's second-tier categories —
    categories they have interacted with but are NOT in their top 3 most-interacted categories.
    """
    # Build a frequency map of category → count from user interactions
    interaction_item_ids = [i.item_id for i in interactions if i.item_id]
    if not interaction_item_ids or len(interaction_item_ids) < 3:
        logger.info("🧠 [WILDCARD] Not enough interaction data. Falling back to Trending.")
        return get_trending_items(db, limit, exclude_ids)
    
    interacted_items = db.scalars(select(Item).where(Item.id.in_(interaction_item_ids))).all()
    if not interacted_items:
        return get_trending_items(db, limit, exclude_ids)
    
    category_counts: Dict[str, int] = {}
    for item in interacted_items:
        if item.category:
            category_counts[item.category] = category_counts.get(item.category, 0) + 1
    
    if not category_counts:
        return get_trending_items(db, limit, exclude_ids)
    
    # Sort categories by interaction count descending
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Top 3 categories are the primary categories; the rest are second-tier
    top_categories = set(cat for cat, _ in sorted_categories[:3])
    second_tier = [cat for cat, _ in sorted_categories[3:]]
    
    if not second_tier:
        logger.info("🧠 [WILDCARD] No second-tier categories found. Falling back to Trending.")
        return get_trending_items(db, limit, exclude_ids)
    
    logger.info(f"🧠 [WILDCARD] Second-tier categories: {second_tier} (top: {list(top_categories)[:3]})")
    
    # Distribute limit evenly across second-tier categories (minimum 1 per category)
    per_cat = max(1, limit // len(second_tier))
    results = []
    wildcard_seen = set()
    
    for category in second_tier:
        cat_limit = per_cat
        cat_items = db.scalars(
            select(Item)
            .where(Item.category == category)
            .where(Item.status == "active")
            .order_by(Item.created_at.desc())
            .limit(cat_limit + len(exclude_ids))
        ).all()
        # Filter excluded IDs
        for item in cat_items:
            if item.id not in exclude_ids and item.id not in wildcard_seen:
                results.append(item)
                wildcard_seen.add(item.id)
                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break
    
    # Backfill with trending if we don't have enough
    if len(results) < limit:
        needed = limit - len(results)
        logger.info(f"🧠 [WILDCARD] Backfilling {needed} from Trending.")
        trending = get_trending_items(db, needed, exclude_ids | wildcard_seen)
        for item in trending:
            if item.id not in wildcard_seen:
                results.append(item)
                wildcard_seen.add(item.id)
    
    logger.info(f"🧠 [WILDCARD] Returning {len(results)} items from second-tier categories.")
    return results[:limit]

def build_feed(db: Session, user_id: int = None, session_id: str = None, limit: int = 20, offset: int = 0, exclude_ids_str: Optional[str] = None) -> List[Item]:
    """
    The Orchestrator.
    Decides the mix ratio based on user maturity (Interaction Count) and scroll depth (page).
    """
    
    # Parse exclude_ids from comma-separated string
    exclude_ids: set = set()
    if exclude_ids_str:
        try:
            exclude_ids = set()
            for token in exclude_ids_str.split(","):
                token = token.strip()
                if token:
                    exclude_ids.add(int(token))
        except (ValueError, TypeError):
            logger.warning(f"🧠 [FEED] Invalid exclude_ids_str received: {exclude_ids_str}")
    
    # Calculate page number (1-indexed)
    page = offset // limit + 1
    logger.info(f"🧠 [FEED] Page {page} (offset={offset}, limit={limit}), exclude_ids count={len(exclude_ids)}")
    
    query = select(UserInteraction).where(UserInteraction.item_id != None).order_by(UserInteraction.created_at.desc())
    
    if user_id:
        query = query.where(UserInteraction.user_id == user_id)
        id_log = f"User {user_id}"
    elif session_id:
        query = query.where(UserInteraction.session_id == session_id)
        id_log = f"Session {session_id}"
    else:
        logger.info("🧠 [FEED] Anonymous Request (No ID). Returning Trending.")
        return get_trending_items(db, limit, exclude_ids)

    all_interactions = db.scalars(query.limit(HISTORY_WINDOW_DISCOVERY)).all()
    count = len(all_interactions)
    
    logger.info(f"🧠 [FEED] Building Feed for {id_log} | History: {count} items")
    
    feed_items = []
    
    # STATE A: COLD START
    if count < 3:
        logger.info("🧠 [STATE] COLD START -> 100% Trending")
        return get_trending_items(db, limit, exclude_ids)
        
    # STATE B: EXPLORER
    elif count <= 10:
        logger.info("🧠 [STATE] EXPLORER -> 70% Session | 30% Trending")
        limit_session = int(limit * 0.7)
        limit_trending = limit - limit_session
        
        feed_items.extend(get_session_feed(db, all_interactions, limit_session, exclude_ids))
        feed_items.extend(get_trending_items(db, limit_trending, exclude_ids))
        
    # STATE C: REGULAR — Waterfall Mix Table
    else:
        # Waterfall ratio table based on page number
        waterfall = {
            1: {"session": 0.40, "discovery": 0.40, "trending": 0.20, "wildcard": 0.0},
            2: {"session": 0.25, "discovery": 0.45, "trending": 0.30, "wildcard": 0.0},
            3: {"session": 0.10, "discovery": 0.50, "trending": 0.40, "wildcard": 0.0},
        }
        
        # For page 4+, use the last entry (page 4 profile)
        if page >= 4:
            ratios = {"session": 0.0, "discovery": 0.40, "trending": 0.40, "wildcard": 0.20}
        else:
            ratios = waterfall.get(page, waterfall[1])
        
        logger.info(f"🧠 [STATE] REGULAR -> Page {page}: "
                     f"{int(ratios['session']*100)}% Session | "
                     f"{int(ratios['discovery']*100)}% Discovery | "
                     f"{int(ratios['trending']*100)}% Trending | "
                     f"{int(ratios['wildcard']*100)}% Wildcard")
        
        limit_session = int(limit * ratios["session"])
        limit_discovery = int(limit * ratios["discovery"])
        limit_trending = int(limit * ratios["trending"])
        limit_wildcard = int(limit * ratios["wildcard"])
        
        # Backfill rule: if sum of sub-limits < limit due to rounding,
        # add remainder to the largest allocation
        remainder = limit - (limit_session + limit_discovery + limit_trending + limit_wildcard)
        if remainder > 0:
            # Find the largest allocation and add remainder
            allocations = {"discovery": limit_discovery, "trending": limit_trending, "session": limit_session, "wildcard": limit_wildcard}
            largest = max(allocations, key=allocations.get)
            if largest == "discovery":
                limit_discovery += remainder
            elif largest == "trending":
                limit_trending += remainder
            elif largest == "session":
                limit_session += remainder
            else:
                limit_wildcard += remainder
        
        if limit_session > 0:
            feed_items.extend(get_session_feed(db, all_interactions, limit_session, exclude_ids))
        if limit_discovery > 0:
            feed_items.extend(get_discovery_feed(db, all_interactions, limit_discovery, exclude_ids))
        if limit_trending > 0:
            feed_items.extend(get_trending_items(db, limit_trending, exclude_ids))
        if limit_wildcard > 0:
            feed_items.extend(get_wildcard_feed(db, all_interactions, limit_wildcard, exclude_ids))

    # DEDUPLICATION
    # Merge frontend-excluded IDs into the seen set so they are also removed
    seen = set(exclude_ids)
    unique_feed = []
    
    for item in feed_items:
        if item.id not in seen:
            unique_feed.append(item)
            seen.add(item.id)
            
    if len(unique_feed) < limit:
        needed = limit - len(unique_feed)
        logger.info(f"🧠 [FEED] Deduplication removed items. Backfilling {needed} from Trending.")
        extras = get_trending_items(db, limit, exclude_ids | seen)
        for item in extras:
            if item.id not in seen:
                unique_feed.append(item)
                seen.add(item.id)
                if len(unique_feed) >= limit: break

    return unique_feed[:limit]
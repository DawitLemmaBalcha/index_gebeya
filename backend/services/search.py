import time
import os
import json
from collections import defaultdict
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Tuple
import numpy as np

# Absolute imports (Docker-friendly)
from ai_engine.vector_client import vectorize_text
from schemas import ItemResponse, ChannelResponse
from models import ItemImage
from constants import SEMANTIC_WEIGHT, LEXICAL_WEIGHT, DEFAULT_RESULT_LIMIT

def _execute_search_sql(db: Session, vec_literal: str, query_text: str, limit: int, offset: int, exclude_unpriced: bool = False, exclude_item_ids: Optional[List[int]] = None) -> List[ItemResponse]:
    """
    Executes the Hybrid Search SQL using strict Top-K Ranking.
    
    CHANGE: Removed threshold filtering. 
    We now return the top 'limit' items sorted by score, regardless of how low the score is.

    NB-43 (D8): additive `exclude_item_ids` — boosted items pinned above the
    organic list must not appear twice on the same page (Rule 3.4). Emitted
    only when non-empty; relevance math untouched.
    """
    
    unpriced_clause = ""
    if exclude_unpriced:
        unpriced_clause = "AND i.price IS NOT NULL AND i.price > 0"
    
    exclude_clause = ""
    if exclude_item_ids:
        exclude_clause = "AND i.id NOT IN :exclude_ids"
    
    sql = text(f"""
    WITH scored_items AS (
        SELECT 
            i.id, 
            i.title,
            i.original_caption,
            i.description, 
            i.price, 
            i.currency, 
            i.category,
            i.subcategory,
            i.image_path, 
            i.specs,
            i.condition,
            i.location,
            i.telegram_message_id, 
            i.created_at,
            i.phone_number,
            
            -- Channel Info (JOINED)
            c.id as channel_id,
            c.username as channel_username,
            c.title as channel_title,
            c.trust_score,
            c.is_verified,
            c.review_count,

            -- Semantic Score (Visual/Vector Match)
            CASE 
                WHEN i.image_vector IS NOT NULL THEN (1 - (i.image_vector <=> {vec_literal}))
                ELSE 0.0
            END as semantic_score,
            
            -- Lexical Score (Text Match via pg_trgm)
            CASE
                WHEN :q != '' THEN similarity(coalesce(i.title, '') || ' ' || i.description, :q)
                ELSE 0.0
            END as lexical_raw
        FROM items i
        JOIN channels c ON i.channel_id = c.id
        WHERE 
            -- Basic Validity Check:
            -- Item must have a vector (for semantic) OR
            -- Item must have SOME text match (> 0.01 very loose) to be worth scoring.
            -- We keep this loose filter to avoid sorting the entire database for 0.0 score items.
            (i.image_vector IS NOT NULL OR (:q != '' AND similarity(coalesce(i.title, '') || ' ' || i.description, :q) > 0.01))
            {unpriced_clause}
            {exclude_clause}
            -- TECH-22: Only return active items in search
            AND i.status = 'active'
    )
    SELECT 
        *,
        -- Final Weighted Calculation
        -- Items without vectors get full lexical weight instead of zero semantic
        CASE 
            WHEN semantic_score = 0 THEN lexical_raw
            ELSE (semantic_score * :w_sem) + (lexical_raw * :w_lex)
        END as total_score
    FROM scored_items
    -- REMOVED: WHERE total_score > threshold
    -- REASON: We want Top-K ranking. Even low scores should appear if they are the "best available".
    ORDER BY total_score DESC
    LIMIT :limit OFFSET :offset;
    """)

    params: dict = {
        "q": query_text, 
        "w_sem": SEMANTIC_WEIGHT, 
        "w_lex": LEXICAL_WEIGHT,
        "limit": limit,
        "offset": offset
    }
    stmt = sql
    if exclude_item_ids:
        params["exclude_ids"] = exclude_item_ids
        stmt = sql.bindparams(bindparam("exclude_ids", expanding=True))

    results = db.execute(stmt, params).fetchall()

    # Serialize results into Pydantic Models
    items = []
    for row in results:
        # 1. Reconstruct Channel Object
        channel_obj = ChannelResponse(
            id=row.channel_id,
            username=row.channel_username,
            title=row.channel_title,
            trust_score=row.trust_score,
            is_verified=row.is_verified,
            review_count=row.review_count
        )

        # 2. Reconstruct Specs Dict safely
        specs_dict = {}
        try:
            if row.specs:
                clean_json = row.specs.replace("'", '"')
                specs_dict = json.loads(clean_json)
        except:
            specs_dict = {}

        # 3. Create Item Response (images filled post-loop — full gallery)
        items.append(ItemResponse(
            id=row.id,
            title=row.title, 
            original_caption=row.original_caption,
            description=row.description,
            price=row.price,
            currency=row.currency,
            phone_number=row.phone_number,
            category=row.category,
            subcategory=row.subcategory,
            specs=specs_dict,
            condition=row.condition,
            location=row.location,
            image_path=row.image_path,
            created_at=row.created_at,
            channel=channel_obj,
            images=[],
            
            # Explicitly Map Score
            total_score=row.total_score,
            relevance_score=row.total_score # For backward compatibility
        ))

    # NB-17: single source of truth — `images` is ALWAYS the full gallery.
    # Batch-enrich in ONE query for all built items; legacy items with no
    # ItemImage rows fall back to the backward-compat thumbnail singleton.
    if items:
        gallery_by_item = defaultdict(list)
        img_stmt = text(
            "SELECT item_id, image_path FROM item_images WHERE item_id IN :ids ORDER BY id"
        ).bindparams(bindparam("ids", expanding=True))
        img_rows = db.execute(img_stmt, {"ids": [it.id for it in items]}).fetchall()
        for img in img_rows:
            gallery_by_item[img.item_id].append(img.image_path)
        for it in items:
            it.images = gallery_by_item[it.id] or ([it.image_path] if it.image_path else [])
        
    return items

def perform_hybrid_search(db: Session, query_text: str, limit: int = None, offset: int = 0, threshold: float = 0.2, min_price: float = None, max_price: float = None, category: str = None, exclude_unpriced: bool = False, exclude_item_ids: Optional[List[int]] = None) -> Tuple[List[ItemResponse], int]:
    """
    Main Entry point for Text-triggered Hybrid Search.
    Returns: (List[ItemResponse], TotalCount)

    NB-43 (D8): additive `exclude_item_ids` threaded into the SQL so boosted
    items pinned by the /search/ route never appear twice (Rule 3.4).
    All existing callers keep working (default None).
    """
    t0 = time.time()
    
    # Use Env Var Default if limit is not provided
    if limit is None:
        limit = DEFAULT_RESULT_LIMIT

    # 1. Vectorize Text
    if not query_text:
        query_vector = vectorize_text("")
    else:
        query_vector = vectorize_text(query_text)
    
    # 2. Handle Vector Type (numpy -> list)
    if hasattr(query_vector, "tolist"): vec_as_list = query_vector.tolist()
    elif isinstance(query_vector, list): vec_as_list = query_vector
    else: vec_as_list = list(query_vector)

    vec_literal = f"'{str(vec_as_list)}'"
    
    # 3. Execute Hybrid SQL (Top-K Ranking)
    # We fetch slightly more (limit + 5) to account for post-filtering, though SQL is preferred.
    fetch_limit = limit + 10 
    
    # Note: 'threshold' argument is now ignored in favor of pure ranking
    items = _execute_search_sql(db, vec_literal, query_text, fetch_limit, offset, exclude_unpriced=exclude_unpriced, exclude_item_ids=exclude_item_ids)

    # 4. Apply Post-SQL Filters
    filtered_items = []
    for item in items:
        if min_price and (item.price is None or item.price < min_price): continue
        if max_price and (item.price is None or item.price > max_price): continue
        if category and category != "All" and item.category != category: continue
        filtered_items.append(item)
    
    # Slice to requested limit
    final_items = filtered_items[:limit]

    print(f"⏱️ Hybrid Search: Found {len(final_items)} items in {time.time() - t0:.4f}s")
    
    return final_items, len(final_items)

def perform_image_search(db: Session, query_vector: List[float], limit: int = None, offset: int = 0, threshold: float = 0.2) -> Tuple[List[ItemResponse], int]:
    """
    Image-triggered Search (Visual Resonance).
    Ignores text query.
    """
    t0 = time.time()
    
    if limit is None:
        limit = DEFAULT_RESULT_LIMIT

    # Handle Vector Format
    if hasattr(query_vector, "tolist"): vec_as_list = query_vector.tolist()
    else: vec_as_list = list(query_vector)

    vec_literal = f"'{str(vec_as_list)}'"
    
    # Pass empty string for text query so lexical score is 0
    items = _execute_search_sql(db, vec_literal, "", limit, offset)
    
    print(f"⏱️ Visual Search: Found {len(items)} items in {time.time() - t0:.4f}s")
    return items, len(items)
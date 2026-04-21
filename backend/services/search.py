import time
import os
import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Tuple
import numpy as np

# Absolute imports (Docker-friendly)
from ai_engine.vector_client import vectorize_text
from schemas import ItemResponse, ChannelResponse
from ai_engine.matcher import SEMANTIC_WEIGHT, LEXICAL_WEIGHT, DEFAULT_RESULT_LIMIT

def _execute_search_sql(db: Session, vec_literal: str, query_text: str, limit: int, offset: int) -> List[ItemResponse]:
    """
    Executes the Hybrid Search SQL using strict Top-K Ranking.
    
    CHANGE: Removed threshold filtering. 
    We now return the top 'limit' items sorted by score, regardless of how low the score is.
    """
    
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
    )
    SELECT 
        *,
        -- Final Weighted Calculation
        (
            (semantic_score * :w_sem) + 
            (lexical_raw * :w_lex)
        ) as total_score
    FROM scored_items
    -- REMOVED: WHERE total_score > threshold
    -- REASON: We want Top-K ranking. Even low scores should appear if they are the "best available".
    ORDER BY total_score DESC
    LIMIT :limit OFFSET :offset;
    """)

    results = db.execute(sql, {
        "q": query_text, 
        "w_sem": SEMANTIC_WEIGHT, 
        "w_lex": LEXICAL_WEIGHT,
        "limit": limit,
        "offset": offset
    }).fetchall()

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

        # 3. Create Item Response
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
            image_path=row.image_path,
            created_at=row.created_at,
            channel=channel_obj,
            images=[row.image_path] if row.image_path else [],
            
            # Explicitly Map Score
            total_score=row.total_score,
            relevance_score=row.total_score # For backward compatibility
        ))
        
    return items

def perform_hybrid_search(db: Session, query_text: str, limit: int = None, offset: int = 0, threshold: float = 0.2, min_price: float = None, max_price: float = None, category: str = None) -> Tuple[List[ItemResponse], int]:
    """
    Main Entry point for Text-triggered Hybrid Search.
    Returns: (List[ItemResponse], TotalCount)
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
    items = _execute_search_sql(db, vec_literal, query_text, fetch_limit, offset)

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
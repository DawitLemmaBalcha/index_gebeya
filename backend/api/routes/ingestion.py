import os
import time
import logging
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import get_db
from models import Item, Channel, ItemImage
from schemas import TelegramPost, IngestionResponse
from ai_engine import extract_product_info
from ai_engine.vector_client import vectorize_image, get_visual_hints
from services.alerting import process_new_item # IMPORT ORCHESTRATOR

router = APIRouter()
logger = logging.getLogger("suq_ingestion")

@router.post("/parse-telegram-post", response_model=IngestionResponse)
async def parse_telegram_post(
    post: TelegramPost, 
    background_tasks: BackgroundTasks, # ADDED BACKGROUND TASKS
    db: Session = Depends(get_db)
):
    logger.info(f"Ingesting post {post.message_id} from {post.channel_name}")

    try:
        # ---------------------------------------------------------
        # PHASE 2: VISUAL INTELLIGENCE (VECTOR AVERAGING)
        # ---------------------------------------------------------
        visual_vector = None
        visual_hints = None
        
        # Collect all unique paths (Thumbnail + Album)
        image_paths_to_process = set()
        if post.image_path:
            image_paths_to_process.add(post.image_path)
        if post.album_paths:
            for p in post.album_paths:
                image_paths_to_process.add(p)
        
        collected_vectors = []
        
        # Vectorize Loop
        for rel_path in image_paths_to_process:
            full_path = os.path.join("/app/media", rel_path)
            if os.path.exists(full_path):
                vec = vectorize_image(full_path)
                if vec:
                    collected_vectors.append(vec)
        
        # Calculate Centroid (Average Vector)
        if collected_vectors:
            # Axis 0 averages the lists column-wise (creating one 512-dim vector)
            visual_vector = np.mean(collected_vectors, axis=0).tolist()
            logger.info(f"🧠 Generated Composite Vector from {len(collected_vectors)} images.")
            
            # Generate Hints from the Centroid
            visual_hints = get_visual_hints(visual_vector)
            logger.info(f"🧠 Composite Hints: {visual_hints}")
        else:
            logger.warning("⚠️ No valid images found for vectorization.")

        # ---------------------------------------------------------
        # 1. AI Extraction Pipeline
        # ---------------------------------------------------------
        extraction_data = extract_product_info(
            text=post.text, 
            image_path=os.path.join("/app/media", post.image_path) if post.image_path else None,
            visual_hints=visual_hints
        )
        
        if not extraction_data:
            raise HTTPException(status_code=500, detail="AI Extraction failed")

        # Wrapper for dot notation access if dict returned
        class DataWrapper:
            def __init__(self, d): self.__dict__ = d
        
        if isinstance(extraction_data, dict):
            ext = DataWrapper(extraction_data)
        else:
            ext = extraction_data

        # ---------------------------------------------------------
        # 2. Channel Resolution
        # ---------------------------------------------------------
        clean_username = post.channel_name.replace("https://t.me/", "").replace("@", "")
        stmt = select(Channel).where(Channel.username == clean_username)
        channel = db.scalar(stmt)
        
        if not channel:
            logger.info(f"Creating new channel: {clean_username}")
            channel = Channel(username=clean_username, title=clean_username, trust_score=2.5)
            db.add(channel)
            db.flush()

        # ---------------------------------------------------------
        # 3. Create Item
        # ---------------------------------------------------------
        new_item = Item(
            channel_id=channel.id,
            telegram_message_id=post.message_id,
            title=getattr(ext, 'title', getattr(ext, 'item_name', 'Unknown Item')),
            original_caption=post.text,
            description=getattr(ext, 'description', 'No description'),
            price=getattr(ext, 'price', 0),
            currency=getattr(ext, 'currency', 'ETB'),
            phone_number=getattr(ext, 'contact_phone', None) or getattr(ext, 'phone_number', None),
            category=getattr(ext, 'category', 'Uncategorized'),
            subcategory=getattr(ext, 'subcategory', 'General'),
            specs=str(getattr(ext, 'item_metadata', {})),
            image_path=post.image_path,
            image_vector=visual_vector # Storing the CENTROID
        )

        db.add(new_item)
        db.flush()

        # 4. Handle Gallery
        if post.album_paths:
            for path in post.album_paths:
                db.add(ItemImage(item_id=new_item.id, image_path=path))
        elif post.image_path:
            db.add(ItemImage(item_id=new_item.id, image_path=post.image_path))

        db.commit()
        db.refresh(new_item)

        # ---------------------------------------------------------
        # 5. TRIGGER ALERT ENGINE (Background Task)
        # ---------------------------------------------------------
        # We pass a fresh DB session inside the service, or handle session carefully.
        # Ideally, background tasks should open their own session.
        # For simplicity in this architecture, we pass the ID and let the service open a session if needed,
        # but here we are inside a request, so we should trust the service to handle it synchronously for now
        # OR better: run it in background to avoid blocking ingestion response.
        
        # Note: Passing 'db' to background task is risky because request closes it.
        # We will assume 'process_new_item' opens its own session or we run it synchronously if fast enough.
        # Given vector search speed, synchronous is safer for consistency in Phase 2.
        
        process_new_item(db, new_item.id)

        return IngestionResponse(
            status="success",
            item_id=new_item.id,
            extracted_data=extraction_data if isinstance(extraction_data, dict) else extraction_data.dict(),
            error=None
        )

    except Exception as e:
        logger.error(f"Error processing post: {str(e)}")
        db.rollback()
        return IngestionResponse(status="error", error=str(e))
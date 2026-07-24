import os
import logging
import httpx
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Channel
from schemas import ChannelResponse

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
router = APIRouter()
logger = logging.getLogger("index_channels")


class ChannelUpdate(BaseModel):
    photo_file_id: Optional[str] = None
    title: Optional[str] = None


@router.get("/", response_model=List[ChannelResponse])
def list_channels(db: Session = Depends(get_db)):
    """List all active channels. Used by the listener's daily photo refresher."""
    return db.query(Channel).all()


@router.patch("/{channel_id}", response_model=ChannelResponse)
def update_channel(channel_id: int, update: ChannelUpdate, db: Session = Depends(get_db)):
    """Update channel fields (photo_file_id, title). Used by the listener's daily refresher."""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Use exclude_unset to distinguish between "not provided" and "explicitly null"
    update_data = update.model_dump(exclude_unset=True)
    if "photo_file_id" in update_data:
        channel.photo_file_id = update_data["photo_file_id"]
    if "title" in update_data:
        channel.title = update_data["title"]

    db.commit()
    db.refresh(channel)
    return channel


@router.get("/{channel_id}/photo")
async def serve_channel_photo(channel_id: int, db: Session = Depends(get_db)):
    """
    Serve channel profile photo via 307 redirect to Telegram CDN.
    The browser caches the redirect for 1 hour (Cache-Control header).
    """
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.photo_file_id is None:
        raise HTTPException(status_code=404, detail="No photo available for this channel")

    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Server config error: Missing Bot Token")

    try:
        file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={channel.photo_file_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(file_url)
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and data["result"].get("file_path"):
                    file_path = data["result"]["file_path"]
                    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                    return RedirectResponse(
                        url=download_url,
                        status_code=307,
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
            logger.warning(f"⚠️ getFile failed for channel {channel_id}: {response.status_code}")
    except Exception as e:
        logger.warning(f"⚠️ Photo resolution failed for channel {channel_id}: {e}")

    raise HTTPException(status_code=502, detail="Failed to resolve photo URL")

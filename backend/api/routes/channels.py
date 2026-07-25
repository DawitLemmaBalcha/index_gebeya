import os
import logging
import json
import httpx
from typing import List, Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from database import get_db
from models import Channel, User, Item
from schemas import ChannelResponse, ChannelUpsert, OwnerChannelResponse

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


@router.post("/", response_model=ChannelResponse)
def upsert_channel(body: ChannelUpsert, db: Session = Depends(get_db)):
    """Upsert a channel from the listener bot (owner onboarding)."""
    channel = db.query(Channel).filter(Channel.username == body.username).first()

    if channel:
        # Update existing channel
        if body.registered_by is not None:
            channel.registered_by = body.registered_by
        if body.title is not None:
            channel.title = body.title
        if body.telegram_id is not None:
            channel.telegram_id = body.telegram_id
        db.commit()
        db.refresh(channel)
        return channel
    else:
        # Create new channel with default trust_score
        channel = Channel(
            username=body.username,
            title=body.title or body.username,
            registered_by=body.registered_by,
            telegram_id=body.telegram_id,
            trust_score=2.5,
        )
        db.add(channel)
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


# ----------------------------------------------------------------------
# TECH-17: Auth helper for init_data-based authentication
# ----------------------------------------------------------------------
def _auth_user_from_init_data(init_data: str, db: Session) -> User:
    """
    Parse Telegram WebApp initData to authenticate/identify the user.
    Returns the User object. Raises 403 if init_data is missing or invalid.
    """
    try:
        tg_id = None
        username = "unknown"

        if "user=" not in init_data:
            raise HTTPException(
                status_code=403,
                detail="Restricted: Valid Telegram init_data required."
            )

        parsed = parse_qs(init_data)
        if 'user' in parsed:
            user_json = parsed['user'][0]
            user_data = json.loads(user_json)
            tg_id = user_data.get('id')
            username = user_data.get('username', 'unknown')
        else:
            raise ValueError("init_data missing 'user' field")

        if not tg_id:
            raise ValueError("Could not extract Telegram ID from init_data")

        # Database Lookup or Auto-Create
        user = db.scalar(select(User).where(User.telegram_id == tg_id))

        if not user:
            user = User(telegram_id=tg_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)

        return user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail="Authentication Failed")


# ----------------------------------------------------------------------
# TECH-17: GET /channels/mine — return channels owned by authenticated user
# ----------------------------------------------------------------------
@router.get("/mine", response_model=List[OwnerChannelResponse])
def get_my_channels(
    init_data: str,
    db: Session = Depends(get_db),
):
    """
    Returns the list of channels owned by the authenticated user,
    including product count for each channel.
    """
    user = _auth_user_from_init_data(init_data, db)

    # Query channels where registered_by matches the user's telegram_id
    channels = db.scalars(
        select(Channel).where(Channel.registered_by == user.telegram_id)
    ).all()

    result = []
    for channel in channels:
        # Count products for this channel
        product_count = db.scalar(
            select(func.count(Item.id)).where(Item.channel_id == channel.id)
        )
        result.append(OwnerChannelResponse(
            id=channel.id,
            username=channel.username,
            title=channel.title,
            trust_score=channel.trust_score,
            review_count=channel.review_count,
            is_verified=channel.is_verified,
            product_count=product_count or 0,
            is_active=True,
        ))

    return result

import os
import logging
import httpx
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from database import get_db
from models import Channel, Item
from schemas import ChannelResponse, ChannelUpsert, OwnerChannelResponse
from schemas import ChannelInfoResponse, ChannelPauseRequest, ChannelActionResponse, ItemResponse
from services.auth import authenticate

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
    user = authenticate(init_data, db)

    # Query channels where registered_by matches the user's telegram_id
    # TECH-19: Filter out inactive (removed) channels
    channels = db.scalars(
        select(Channel).where(
            Channel.registered_by == user.telegram_id,
            Channel.is_active == True,
        )
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
            indexing_paused=channel.indexing_paused,
            is_active=not channel.indexing_paused,
        ))

    return result


# ----------------------------------------------------------------------
# TECH-19: GET /channels/by-username/{username} — internal channel info lookup
# ----------------------------------------------------------------------
@router.get("/by-username/{username}", response_model=ChannelInfoResponse)
def get_channel_by_username(
    username: str,
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
    db: Session = Depends(get_db),
):
    """
    Look up channel info by Telegram username. Internal endpoint for the listener worker.
    Requires X-Internal-Service header for authentication.
    """
    if x_internal_service != "index-listener":
        raise HTTPException(status_code=403, detail="Forbidden: internal service only")

    channel = db.query(Channel).filter(Channel.username == username).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    return ChannelInfoResponse(
        id=channel.id,
        username=channel.username,
        registered_by=channel.registered_by,
        indexing_paused=channel.indexing_paused,
        is_active=channel.is_active,
    )


# ----------------------------------------------------------------------
# TECH-19: PATCH /channels/{channel_id}/pause — toggle indexing_paused
# ----------------------------------------------------------------------
@router.patch("/{channel_id}/pause", response_model=ChannelActionResponse)
async def toggle_channel_pause(
    channel_id: int,
    body: ChannelPauseRequest,
    init_data: str,
    db: Session = Depends(get_db),
):
    """
    Pause or resume indexing for a channel owned by the authenticated user.
    Sends a DM notification to the channel owner via Telegram Bot API.
    """
    user = authenticate(init_data, db)

    channel = db.query(Channel).filter(
        Channel.id == channel_id,
        Channel.registered_by == user.telegram_id,
    ).first()

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel.indexing_paused = body.indexing_paused
    db.commit()
    db.refresh(channel)

    # Send DM notification via Telegram Bot API
    if BOT_TOKEN:
        try:
            if body.indexing_paused:
                msg = (
                    f"⏸️ @{channel.username} is paused. "
                    f"Your products remain indexed but new posts won't appear. "
                    f"Tap Resume in Stores anytime."
                )
            else:
                msg = (
                    f"▶️ @{channel.username} is active again. "
                    f"New posts will appear in the marketplace."
                )
            async with httpx.AsyncClient(timeout=10.0) as client:
                dm_resp = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": channel.registered_by,
                        "text": msg,
                    },
                )
                if dm_resp.status_code != 200:
                    logger.warning(f"⚠️ DM send failed for channel {channel_id}: {dm_resp.text[:200]}")
        except Exception as e:
            logger.warning(f"⚠️ DM notification exception for channel {channel_id}: {e}")

    return ChannelActionResponse(status="ok")


# ----------------------------------------------------------------------
# TECH-19: DELETE /channels/{channel_id} — remove channel with auto-leave
# ----------------------------------------------------------------------
@router.delete("/{channel_id}", response_model=ChannelActionResponse)
async def remove_channel(
    channel_id: int,
    init_data: str,
    db: Session = Depends(get_db),
):
    """
    Remove a channel owned by the authenticated user. Attempts to make the bot
    leave the channel via Telegram API (leaveChat), then soft-deletes the channel
    (sets is_active=False). Sends a DM notification to the owner.
    """
    user = authenticate(init_data, db)

    channel = db.query(Channel).filter(
        Channel.id == channel_id,
        Channel.registered_by == user.telegram_id,
    ).first()

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Attempt auto-leave from the Telegram channel
    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Step 1: Get chat_id from username
                get_chat_resp = await client.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getChat",
                    params={"chat_id": f"@{channel.username}"},
                )
                if get_chat_resp.status_code == 200:
                    chat_data = get_chat_resp.json()
                    if chat_data.get("ok") and chat_data.get("result", {}).get("id"):
                        chat_id = chat_data["result"]["id"]
                        # Step 2: Leave the channel
                        leave_resp = await client.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/leaveChat",
                            json={"chat_id": chat_id},
                        )
                        if leave_resp.status_code != 200:
                            logger.warning(
                                f"⚠️ leaveChat failed for channel {channel_id}: "
                                f"{leave_resp.text[:200]}"
                            )
                    else:
                        logger.warning(f"⚠️ getChat returned no id for channel {channel_id}")
                else:
                    logger.warning(
                        f"⚠️ getChat failed for channel {channel_id}: "
                        f"{get_chat_resp.status_code} — {get_chat_resp.text[:200]}"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Telegram leaveChat exception for channel {channel_id}: {e}")

    # Soft-delete: mark channel as inactive (Rule 3.3: DB is source of truth)
    channel.is_active = False
    db.commit()
    db.refresh(channel)

    # Send DM notification via Telegram Bot API
    if BOT_TOKEN and channel.registered_by:
        try:
            msg = (
                f"👋 I've left @{channel.username}. "
                f"Your existing products stay indexed. Add me back anytime to resume."
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                dm_resp = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": channel.registered_by,
                        "text": msg,
                    },
                )
                if dm_resp.status_code != 200:
                    logger.warning(f"⚠️ DM send failed for channel {channel_id}: {dm_resp.text[:200]}")
        except Exception as e:
            logger.warning(f"⚠️ DM notification exception for channel {channel_id}: {e}")

    return ChannelActionResponse(status="ok")


# ----------------------------------------------------------------------
# TECH-23: GET /channels/{channel_id}/items — inventory management
# ----------------------------------------------------------------------
@router.get("/{channel_id}/items", response_model=List[ItemResponse])
def get_channel_items(
    channel_id: int,
    init_data: str,
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    sort: Optional[str] = "recent",
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns paginated, filterable, sortable items for a channel owned
    by the authenticated user.
    """
    user = authenticate(init_data, db)

    # Verify ownership
    channel = db.scalar(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.registered_by == user.telegram_id,
        )
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Base query: active items owned by this channel
    stmt = select(Item).where(
        Item.channel_id == channel_id,
        Item.is_active == True,
    )

    # Status filter
    if status == "sold":
        stmt = stmt.where(Item.status == "sold")
    elif status == "reported":
        stmt = stmt.where(Item.status == "reported_sold")
    elif status == "active":
        stmt = stmt.where(Item.status == "active")
    # "all" or None: no status filter

    # Search filter (case-insensitive by title)
    if search:
        stmt = stmt.where(Item.title.ilike(f"%{search}%"))

    # Sorting
    if sort == "price_asc":
        stmt = stmt.order_by(Item.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Item.price.desc())
    else:
        # Default: most recent first
        stmt = stmt.order_by(Item.created_at.desc())

    # Pagination
    stmt = stmt.offset(offset).limit(limit)

    items = db.scalars(stmt).all()
    return items

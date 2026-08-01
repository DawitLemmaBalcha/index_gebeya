"""
Owner DM delivery — notify a channel owner via the Telegram Bot API.

One domain concept, two adapters (previously duplicated across items.py and
cleanup.py with drifted implementations):

  - `send_owner_dm`      — async adapter for route handlers (FastAPI async context)
  - `send_owner_dm_sync` — sync adapter for the cleanup background thread
                           (opens its own SessionLocal; never touches the
                           caller's session)

Both are best-effort: channel lookup, early return when the channel has no
owner (`registered_by is None`), warning-only logging on missing BOT_TOKEN,
HTTP errors, and transport exceptions. They never raise.
"""

import os
import logging
import httpx
from sqlalchemy.orm import Session

from models import Channel
from database import SessionLocal

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logger = logging.getLogger("index_owner_dm")


async def send_owner_dm(db: Session, channel_id: int, message: str, reply_markup: dict = None) -> None:
    """
    Send a DM to the channel owner via Telegram Bot API.
    Best-effort: logs warning on failure, never raises.
    (Async adapter for route handlers.)
    reply_markup: optional Telegram InlineKeyboardMarkup JSON (buttons).
    """
    try:
        channel = db.get(Channel, channel_id)
        if not channel or channel.registered_by is None:
            return  # No owner to notify

        if not BOT_TOKEN:
            logger.warning("BOT_TOKEN not set, cannot send owner DM")
            return

        payload = {"chat_id": channel.registered_by, "text": message}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning(f"⚠️ DM send failed for channel {channel_id}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"⚠️ DM notification exception for channel {channel_id}: {e}")


def send_owner_dm_sync(channel_id: int, message: str, reply_markup: dict = None) -> None:
    """
    Send a DM to the channel owner via Telegram Bot API.
    Best-effort: logs warning on failure, never raises.
    (Synchronous adapter for the background thread — opens its own session.)
    """
    try:
        db = SessionLocal()
        channel = db.get(Channel, channel_id)
        db.close()

        if not channel or channel.registered_by is None:
            return  # No owner to notify

        if not BOT_TOKEN:
            logger.warning("BOT_TOKEN not set, cannot send owner DM")
            return

        payload = {"chat_id": channel.registered_by, "text": message}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        resp = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning(f"⚠️ DM send failed for channel {channel_id}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"⚠️ DM notification exception for channel {channel_id}: {e}")

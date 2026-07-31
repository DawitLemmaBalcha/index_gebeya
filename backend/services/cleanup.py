"""
TECH-22: Daily background cleanup service.

Scheduled via threading.Timer in main.py startup_event.
Performs three cleanup phases:
  1. Soft-deleted item removal (after SOFT_DELETED_RETENTION_DAYS)
  2. Reported-sold item removal (after REPORTED_SOLD_RETENTION_DAYS)
  3. Stale item flagging (after STALE_ITEM_DAYS, zero interactions)
"""

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func

from database import SessionLocal
from models import Item, Channel, UserInteraction
from services.owner_dm import send_owner_dm_sync
from constants import (
    SOFT_DELETED_RETENTION_DAYS,
    REPORTED_SOLD_RETENTION_DAYS,
    STALE_ITEM_DAYS,
)

logger = logging.getLogger("index_cleanup")


def run_daily_cleanup() -> dict:
    """
    Execute all three cleanup phases synchronously.
    Returns a summary dict with counts.
    """
    db = SessionLocal()
    now_utc = datetime.now(timezone.utc)

    soft_deleted_removed = 0
    reported_sold_removed = 0
    stale_flagged = 0

    # --- Phase 1: Soft-deleted cleanup ---
    try:
        cutoff_soft = now_utc - timedelta(days=SOFT_DELETED_RETENTION_DAYS)
        soft_items = db.scalars(
            select(Item).where(
                Item.status == "soft_deleted",
                Item.created_at < cutoff_soft,
            )
        ).all()

        for item in soft_items:
            channel = db.get(Channel, item.channel_id)
            if channel and channel.username:
                send_owner_dm_sync(
                    item.channel_id,
                    f"🗑️ Your listing '{item.title}' on @{channel.username} "
                    f"has been permanently removed after {SOFT_DELETED_RETENTION_DAYS} days.",
                )
            db.delete(item)
            soft_deleted_removed += 1

        db.commit()
        if soft_deleted_removed:
            logger.info(f"🧹 Cleanup: Removed {soft_deleted_removed} soft-deleted items")
    except Exception as e:
        logger.warning(f"⚠️ Soft-deleted cleanup error: {e}")
        db.rollback()

    # --- Phase 2: Reported-sold cleanup ---
    try:
        cutoff_reported = now_utc - timedelta(days=REPORTED_SOLD_RETENTION_DAYS)
        reported_items = db.scalars(
            select(Item).where(
                Item.status == "reported_sold",
                Item.created_at < cutoff_reported,
            )
        ).all()

        for item in reported_items:
            channel = db.get(Channel, item.channel_id)
            if channel and channel.username:
                send_owner_dm_sync(
                    item.channel_id,
                    f"🗑️ Your listing '{item.title}' on @{channel.username} "
                    f"was removed after being reported sold and unaddressed "
                    f"for {REPORTED_SOLD_RETENTION_DAYS} days.",
                )
            db.delete(item)
            reported_sold_removed += 1

        db.commit()
        if reported_sold_removed:
            logger.info(f"🧹 Cleanup: Removed {reported_sold_removed} reported-sold items")
    except Exception as e:
        logger.warning(f"⚠️ Reported-sold cleanup error: {e}")
        db.rollback()

    # --- Phase 3: Stale item flagging ---
    try:
        cutoff_stale = now_utc - timedelta(days=STALE_ITEM_DAYS)
        stale_candidates = db.scalars(
            select(Item).where(
                Item.status == "active",
                Item.created_at < cutoff_stale,
            )
        ).all()

        for item in stale_candidates:
            # Check for zero interactions
            interaction_count = db.scalar(
                select(func.count(UserInteraction.id)).where(
                    UserInteraction.item_id == item.id,
                )
            )
            if interaction_count is None or interaction_count == 0:
                item.is_stale = True
                stale_flagged += 1

        db.commit()
        if stale_flagged:
            logger.info(f"🧹 Cleanup: Flagged {stale_flagged} items as stale")
    except Exception as e:
        logger.warning(f"⚠️ Stale flagging error: {e}")
        db.rollback()

    db.close()

    return {
        "soft_deleted_removed": soft_deleted_removed,
        "reported_sold_removed": reported_sold_removed,
        "stale_flagged": stale_flagged,
    }


def run_cleanup_and_log() -> None:
    """Wrapper: runs cleanup and logs results."""
    logger.info("🧹 Starting daily cleanup cycle...")
    summary = run_daily_cleanup()
    logger.info(
        f"🧹 Cleanup complete: "
        f"{summary['soft_deleted_removed']} soft-deleted, "
        f"{summary['reported_sold_removed']} reported-sold removed, "
        f"{summary['stale_flagged']} items flagged as stale"
    )

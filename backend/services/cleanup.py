"""
TECH-22: Daily background cleanup service.

Scheduled via threading.Timer in main.py startup_event.
Performs five cleanup phases:
  1. Soft-deleted item removal (after SOFT_DELETED_RETENTION_DAYS)
  2. Reported-sold item removal (after REPORTED_SOLD_RETENTION_DAYS)
  3. Stale item flagging (after STALE_ITEM_DAYS, zero interactions)
  4. Dead alert purge (TECH-25, after ALERT_RETENTION_DAYS) — user-deleted
     (deleted_at) or expired (expires_at) alerts; their notifications are
     cascade-removed at the DB level (ON DELETE CASCADE). Silent: no owner DM.
  5. Notification retention purge (TECH-25, after NOTIFICATION_RETENTION_DAYS)
     — terminal notifications (SENT, FAILED, REPLACED) only; PENDING is never
     purged.
"""

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, or_

from database import SessionLocal
from models import Item, Channel, UserInteraction, Alert, Notification
from services.owner_dm import send_owner_dm_sync
from services.scheduler_runs import record_scheduler_run
from constants import (
    SOFT_DELETED_RETENTION_DAYS,
    REPORTED_SOLD_RETENTION_DAYS,
    STALE_ITEM_DAYS,
    ALERT_RETENTION_DAYS,
    NOTIFICATION_RETENTION_DAYS,
)

logger = logging.getLogger("index_cleanup")


def run_daily_cleanup() -> dict:
    """
    Execute all five cleanup phases synchronously.
    Returns a summary dict with counts.
    """
    db = SessionLocal()
    now_utc = datetime.now(timezone.utc)

    soft_deleted_removed = 0
    reported_sold_removed = 0
    stale_flagged = 0
    alerts_purged = 0
    notifications_purged = 0

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

    # --- Phase 4: Dead alert purge (TECH-25) ---
    # Purges alerts that were user-deleted (deleted_at set) or expired
    # (expires_at passed) beyond ALERT_RETENTION_DAYS. Paused and active
    # alerts are protected BY CONSTRUCTION: deleted_at IS NULL and expires_at
    # is in the future, so neither predicate branch matches — no is_active
    # filter needed. The notifications_alert_id_fkey ON DELETE CASCADE removes
    # the alert's notifications at the database level. Silent: no owner DM.
    # Guarded by ALERT_RETENTION_DAYS > 0 (<= 0 disables retention).
    if ALERT_RETENTION_DAYS > 0:
        try:
            cutoff_alerts = now_utc - timedelta(days=ALERT_RETENTION_DAYS)
            dead_alerts = db.scalars(
                select(Alert).where(
                    or_(
                        Alert.deleted_at.isnot(None) & (Alert.deleted_at < cutoff_alerts),
                        Alert.expires_at.isnot(None) & (Alert.expires_at < cutoff_alerts),
                    )
                )
            ).all()

            for alert in dead_alerts:
                db.delete(alert)
                alerts_purged += 1

            db.commit()
            if alerts_purged:
                logger.info(f"🧹 Cleanup: Purged {alerts_purged} dead alerts")
        except Exception as e:
            logger.warning(f"⚠️ Alert purge error: {e}")
            db.rollback()

    # --- Phase 5: Notification retention purge (TECH-25) ---
    # Purges terminal notifications (SENT, FAILED, REPLACED) older than
    # NOTIFICATION_RETENTION_DAYS. PENDING is NEVER purged: the explicit
    # terminal-status IN list guarantees it (a PENDING row older than the
    # cutoff survives by design). Guarded by NOTIFICATION_RETENTION_DAYS > 0.
    if NOTIFICATION_RETENTION_DAYS > 0:
        try:
            cutoff_notifs = now_utc - timedelta(days=NOTIFICATION_RETENTION_DAYS)
            old_notifs = db.scalars(
                select(Notification).where(
                    Notification.status.in_(["SENT", "FAILED", "REPLACED"]),
                    Notification.created_at < cutoff_notifs,
                )
            ).all()

            for notif in old_notifs:
                db.delete(notif)
                notifications_purged += 1

            db.commit()
            if notifications_purged:
                logger.info(f"🧹 Cleanup: Purged {notifications_purged} old notifications")
        except Exception as e:
            logger.warning(f"⚠️ Notification retention error: {e}")
            db.rollback()

    db.close()

    return {
        "soft_deleted_removed": soft_deleted_removed,
        "reported_sold_removed": reported_sold_removed,
        "stale_flagged": stale_flagged,
        "alerts_purged": alerts_purged,
        "notifications_purged": notifications_purged,
    }


def run_cleanup_and_log() -> None:
    """Wrapper: runs cleanup, logs results, records the scheduler run
    (NB-50 — the ops console Overview reads scheduler_runs)."""
    logger.info("🧹 Starting daily cleanup cycle...")
    db = SessionLocal()
    try:
        try:
            record_scheduler_run(db, scheduler="cleanup", success=False, error="started")
        except Exception as e:
            logger.warning(f"⚠️ Could not record cleanup scheduler start: {e}")
        summary = run_daily_cleanup()
        logger.info(
            f"🧹 Cleanup complete: "
            f"{summary['soft_deleted_removed']} soft-deleted, "
            f"{summary['reported_sold_removed']} reported-sold removed, "
            f"{summary['stale_flagged']} items flagged as stale, "
            f"{summary['alerts_purged']} dead alerts purged, "
            f"{summary['notifications_purged']} old notifications purged"
        )
        record_scheduler_run(db, scheduler="cleanup", success=True, result=summary)
    except Exception as e:
        logger.warning(f"⚠️ Cleanup cycle failed: {e}")
        try:
            record_scheduler_run(db, scheduler="cleanup", success=False, error=str(e))
        except Exception:
            logger.warning("⚠️ Could not record cleanup scheduler run")
    finally:
        db.close()

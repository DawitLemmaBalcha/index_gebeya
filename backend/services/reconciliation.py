"""
Star-payments reconciliation (TECH-31, blueprint §6).

Lost successful_payment updates are recovered from getStarTransactions:
for each incoming invoice transaction whose id has no Boost/Subscription
row, the fulfillment is replayed — both fulfill_boost and
fulfill_subscription_payment are idempotent on telegram_payment_charge_id,
so replay is safe (blueprint §6.2).

Watermark: the newest fulfillment row's created_at (max over boosts and
subscriptions). DB-backed, survives restarts; transactions older than the
watermark are skipped. Period end for replayed subscriptions is derived as
the charge date + the transaction's subscription_period (or the hard-locked
30d constant), which is exactly how Telegram sets the authoritative
expiration for both initial and renewal charges.

This module lives outside telegram_payments.py to keep the import map
cycle-free (it imports both boost and subscriptions fulfillment).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import SUBSCRIPTION_PERIOD_SECONDS
from models import Boost, Subscription
from services.boost import fulfill_boost
from services.subscriptions import fulfill_subscription_payment
from services.telegram_payments import star_payments

logger = logging.getLogger("index_reconcile")

# Missed-payment tolerance: a successful_payment timestamped in the SAME
# second as (or up to 5s before) the newest fulfillment row must not be
# skipped by the watermark — Telegram dates are second-granularity, and
# created_at of the replayed row can land in the same second as the missed
# payment's own timestamp. The charge-exists guard below is the real
# idempotency backstop; the watermark only avoids scanning the ancient ledger.
_WATERMARK_TOLERANCE = timedelta(seconds=5)


def _tx_date(tx: dict) -> datetime | None:
    """The transaction date from Telegram's JSON (unix timestamp or ISO)."""
    raw = tx.get("date")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _watermark(db: Session) -> datetime | None:
    """Newest fulfillment row across boosts and subscriptions."""
    boost_max = db.scalar(select(func.max(Boost.created_at)))
    sub_max = db.scalar(select(func.max(Subscription.created_at)))
    candidates = [ts for ts in (boost_max, sub_max) if ts is not None]
    if not candidates:
        return None
    return max(candidates)


def _charge_exists(db: Session, charge_id: str) -> bool:
    if db.scalar(select(Boost.id).where(Boost.telegram_payment_charge_id == charge_id)):
        return True
    return db.scalar(
        select(Subscription.id).where(Subscription.telegram_payment_charge_id == charge_id)
    ) is not None


async def reconcile_star_payments(db: Session, *, limit: int = 100) -> dict:
    """
    Fetch recent Star transactions and replay unfulfilled ones. Returns a
    summary dict {fetched, replayed_boost, replayed_subscription, skipped,
    errors}. Idempotent — safe to run daily (or on demand). Async because the
    StarPaymentsAdapter port is async; the main.py scheduler wraps it in
    asyncio.run().
    """
    summary = {"fetched": 0, "replayed_boost": 0, "replayed_subscription": 0,
               "skipped": 0, "errors": 0}
    watermark = _watermark(db)

    try:
        transactions = await star_payments.get_star_transactions(limit=limit)
    except Exception as e:
        logger.warning(f"reconcile: get_star_transactions failed: {e}")
        summary["errors"] = 1
        return summary

    if not isinstance(transactions, list):
        transactions = []

    summary["fetched"] = len(transactions)
    for tx in transactions:
        charge_id = tx.get("id")
        if not charge_id:
            summary["skipped"] += 1
            continue

        tx_dt = _tx_date(tx)
        # Watermark (tolerant): skip only transactions strictly older than
        # (watermark - tolerance). Same-second and slightly-earlier payments
        # pass this check — already-fulfilled ones are caught by the
        # charge-exists guard below, genuinely missed ones are replayed
        # (both idempotent paths).
        if watermark is not None and (
            tx_dt is None or tx_dt <= watermark - _WATERMARK_TOLERANCE
        ):
            summary["skipped"] += 1
            continue
        if _charge_exists(db, charge_id):
            summary["skipped"] += 1
            continue

        source = tx.get("source") or {}
        # Only incoming invoice payments carry a payload (outgoing
        # transactions have no source).
        if source.get("transaction_type") != "invoice_payment":
            summary["skipped"] += 1
            continue

        payload = source.get("invoice_payload") or ""
        user = source.get("user") or {}
        telegram_user_id = user.get("id")
        if not telegram_user_id:
            summary["skipped"] += 1
            continue

        prefix = payload[:2]
        try:
            if prefix == "b:":
                fulfill_boost(
                    db,
                    telegram_user_id=telegram_user_id,
                    telegram_payment_charge_id=charge_id,
                    invoice_payload=payload,
                    total_amount=int(tx.get("amount") or 0),
                )
                summary["replayed_boost"] += 1
                logger.info(f"reconcile: replayed boost {charge_id}")
            elif prefix == "s:":
                period = source.get("subscription_period") or SUBSCRIPTION_PERIOD_SECONDS
                if isinstance(period, dict):  # Telegram may serialize timedelta
                    period = SUBSCRIPTION_PERIOD_SECONDS
                base = tx_dt or datetime.now(timezone.utc)
                fulfill_subscription_payment(
                    db,
                    telegram_user_id=telegram_user_id,
                    telegram_payment_charge_id=charge_id,
                    invoice_payload=payload,
                    total_amount=int(tx.get("amount") or 0),
                    subscription_expiration_date=base + timedelta(seconds=int(period)),
                    is_recurring=False,
                    is_first_recurring=True,
                )
                summary["replayed_subscription"] += 1
                logger.info(f"reconcile: replayed subscription {charge_id}")
            else:
                logger.warning(f"reconcile: unknown payload prefix {prefix!r} — skipped")
                summary["skipped"] += 1
        except Exception as e:
            logger.warning(f"reconcile: replay failed for {charge_id}: {e}")
            summary["errors"] += 1

    return summary

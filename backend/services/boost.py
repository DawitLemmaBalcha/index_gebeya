"""
Boost — the deep module for all boost behavior (NB-43/44, blueprint §2.2).

One purchase unit (7 days, BOOST_DURATION_DAYS), price by top-level category
(BOOST_PRICE_STARS, exact-key else Other floor). Paid and credit boosts share
one table; placement queries never filter on source (Rule 7.3.3). Rotation is
computed from the clock — deterministic, no background jobs (Rule 4.2).

Import direction: this module imports services.subscriptions; subscriptions
never imports boost — cycle-free.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from constants import (
    BOOST_DURATION_DAYS,
    BOOST_PRICE_STARS,
    BOOST_ROTATION_MINUTES,
    MONETIZATION_ENABLED,
)
from models import Boost, Channel, Item, User
from services.subscriptions import get_credit_boosts_remaining
from services.telegram_payments import star_payments

logger = logging.getLogger("index_boost")

_OTHER_FLOOR = 25


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Purchase (buyer-facing, invoked by route modules)
# ---------------------------------------------------------------------------

def get_boost_price(db: Session, item: Item) -> int:
    """BOOST_PRICE_STARS[item.category] exact-key, else the Other floor (D12).
    Always returns a positive int."""
    price = BOOST_PRICE_STARS.get(item.category)
    if not price:
        price = BOOST_PRICE_STARS.get("Other", _OTHER_FLOOR)
    return max(1, int(price))


def _active_boost_exists(db: Session, item_id: int) -> bool:
    now = _now_utc()
    return db.scalar(
        select(Boost.id).where(Boost.item_id == item_id, Boost.ends_at > now)
    ) is not None


def _validate_boost_eligibility(db: Session, user: User, item: Item) -> Channel:
    """Shared ownership/eligibility validation (Rule 2.5). Raises 403/400/409."""
    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can boost this item",
        )
    if item.status != "active" or not item.is_active:
        raise HTTPException(
            status_code=400,
            detail="Only active items can be boosted",
        )
    if _active_boost_exists(db, item.id):
        raise HTTPException(
            status_code=409,
            detail="This item already has an active boost",
        )
    return channel


async def create_boost_order(db: Session, user: User, item: Item) -> dict:
    """Create a Stars invoice for a boost on this item (Rule 2.7)."""
    if not MONETIZATION_ENABLED:
        raise HTTPException(status_code=503, detail="Monetization is currently disabled")

    _validate_boost_eligibility(db, user, item)
    price = get_boost_price(db, item)
    payload = f"b:{item.id}:{secrets.token_hex(4)}"  # <=128 bytes, unique per invoice
    invoice_url = await star_payments.create_invoice_link(
        title="Boost this product",
        description=f"{BOOST_DURATION_DAYS} days of top placement in category & search",
        payload=payload,
        prices=[("Boost", price)],
    )
    return {
        "invoice_url": invoice_url,
        "payload": payload,
        "price_stars": price,
        "duration_days": BOOST_DURATION_DAYS,
    }


# ---------------------------------------------------------------------------
# Fulfillment (internal, idempotent)
# ---------------------------------------------------------------------------

def fulfill_boost(
    db: Session, *,
    telegram_user_id: int,
    telegram_payment_charge_id: str,
    invoice_payload: str,
    total_amount: int,
) -> Boost:
    """
    Activate a paid boost from a successful_payment. Idempotent on
    telegram_payment_charge_id: a replay returns the existing row.
    price_paid_stars = the ACTUAL charged amount (total_amount) — never
    re-reads BOOST_PRICE_STARS at fulfillment time.
    """
    existing = db.scalar(
        select(Boost).where(Boost.telegram_payment_charge_id == telegram_payment_charge_id)
    )
    if existing:
        return existing

    parts = invoice_payload.split(":")
    if len(parts) != 3 or parts[0] != "b":
        raise HTTPException(status_code=400, detail="Invalid boost invoice payload")
    try:
        item_id = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid boost invoice payload")

    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != telegram_user_id:
        logger.warning(
            f"fulfill_boost: user {telegram_user_id} not owner of channel {item.channel_id} "
            f"— refusing foreign boost activation"
        )
        raise HTTPException(
            status_code=403, detail="Cannot activate a boost for a foreign channel"
        )

    user = db.scalar(select(User).where(User.telegram_id == telegram_user_id))
    if not user:
        user = User(telegram_id=telegram_user_id, username="unknown")
        db.add(user)
        db.flush()

    now = _now_utc()
    boost = Boost(
        item_id=item.id,
        channel_id=item.channel_id,
        user_id=user.id,
        source="paid",
        price_paid_stars=total_amount,
        telegram_payment_charge_id=telegram_payment_charge_id,
        starts_at=now,
        ends_at=now + timedelta(days=BOOST_DURATION_DAYS),
    )
    db.add(boost)
    db.commit()
    db.refresh(boost)
    return boost


def fulfill_credit_boost(db: Session, user: User, item: Item) -> Boost:
    """
    Credit path (Rule 7.3): requires an active all_in_one subscription with
    remaining monthly credit. Creates Boost(source='credit',
    telegram_payment_charge_id=NULL, price_paid_stars=NULL) — placement-
    indistinguishable from paid boosts.
    """
    if not MONETIZATION_ENABLED:
        raise HTTPException(status_code=503, detail="Monetization is currently disabled")

    _validate_boost_eligibility(db, user, item)
    remaining = get_credit_boosts_remaining(db, user)
    if remaining <= 0:
        raise HTTPException(
            status_code=400, detail="No subscription boost credit remaining"
        )

    now = _now_utc()
    boost = Boost(
        item_id=item.id,
        channel_id=item.channel_id,
        user_id=user.id,
        source="credit",
        price_paid_stars=None,
        telegram_payment_charge_id=None,
        starts_at=now,
        ends_at=now + timedelta(days=BOOST_DURATION_DAYS),
    )
    db.add(boost)
    db.commit()
    db.refresh(boost)
    return boost


# ---------------------------------------------------------------------------
# Placement (the pinned layer)
# ---------------------------------------------------------------------------

def get_pinned_boosted_items(
    db: Session, *,
    category: str | None = None,
    query_text: str | None = None,
    now: datetime | None = None,
) -> list[Item]:
    """
    Active boosted items for the /search/ route (D7 — the ONE application
    point). Deterministic time-sliced rotation (Rule 4.2), no mutable state.
    NEVER called from services/recommendation.py (Rule 3.2 — feed isolation).
    """
    now = now or _now_utc()
    rows = db.execute(
        select(Boost, Item)
        .join(Item, Boost.item_id == Item.id)
        .where(
            Boost.ends_at > now,
            Item.status == "active",
            Item.is_active == True,
        )
    ).all()

    # Dedupe per item (one active boost per item is enforced at order time,
    # but be defensive) and sort by id for a stable rotation base.
    by_id = {item.id: item for _, item in rows}
    candidates = sorted(by_id.values(), key=lambda i: i.id)

    if category:
        candidates = [i for i in candidates if i.category == category]
    if query_text and query_text.strip():
        q = query_text.strip().lower()
        candidates = [
            i for i in candidates
            if i.title and q in i.title.lower()
        ]

    if len(candidates) == 0:
        return []

    rotation_offset = (
        int(now.timestamp()) // (BOOST_ROTATION_MINUTES * 60) % len(candidates)
    )
    return candidates[rotation_offset:] + candidates[:rotation_offset]


# ---------------------------------------------------------------------------
# Lifecycle hooks (Rules 6.1/6.2)
# ---------------------------------------------------------------------------

def end_boost_for_item(db: Session, item_id: int) -> None:
    """Sold/reported_sold -> boost ends immediately, no refund (Rule 6.1)."""
    now = _now_utc()
    db.execute(
        update(Boost)
        .where(Boost.item_id == item_id, Boost.ends_at > now)
        .values(ends_at=now)
    )
    db.commit()


def transfer_boost(db: Session, old_item_id: int, new_item_id: int) -> None:
    """Dedup replacement (Rule 6.2): remaining boost moves to the replacement.
    NO commit here — the ingestion route commits atomically with the
    replacement (blueprint D13)."""
    now = _now_utc()
    db.execute(
        update(Boost)
        .where(Boost.item_id == old_item_id, Boost.ends_at > now)
        .values(item_id=new_item_id)
    )


def get_boost_status(db: Session, item_id: int) -> dict | None:
    """For the frontend refresh loop after invoiceClosed."""
    now = _now_utc()
    boost = db.scalar(
        select(Boost)
        .where(Boost.item_id == item_id, Boost.ends_at > now)
        .order_by(Boost.id.desc())
    )
    if not boost:
        return None
    return {
        "active": True,
        "ends_at": boost.ends_at.isoformat(),
        "source": boost.source,
    }

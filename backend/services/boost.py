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
    BOOST_ROTATION_MINUTES,
)
from models import Boost, Channel, Item, User
from services import settings_registry
from services.ban import owner_banned_pred  # NB-56 Rule 3.3: the pinned layer
from services.boost_pricing import get_boost_price  # re-export (D12, D14)
from services.subscriptions import get_credit_boosts_remaining
from services.telegram_payments import star_payments

logger = logging.getLogger("index_boost")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Purchase (buyer-facing, invoked by route modules)
# ---------------------------------------------------------------------------

def _active_boost_exists(db: Session, item_id: int) -> bool:
    now = _now_utc()
    return db.scalar(
        select(Boost.id).where(Boost.item_id == item_id, Boost.ends_at > now)
    ) is not None


# Exact detail strings are part of the API contract (UAT regression: the
# quote exposes them via `reason`, order/credit endpoints raise them).
_STATUS_REASON = "Only active items can be boosted"
_ACTIVE_BOOST_REASON = "This item already has an active boost"


def get_boost_eligibility(db: Session, item: Item) -> tuple[bool, str | None]:
    """Why this item can/cannot be boosted right now (non-ownership reasons).

    Returns (True, None) when a boost can be purchased; otherwise the
    (False, reason) pair with the same detail strings the order/credit
    endpoints raise. Ownership is NOT checked here — routes enforce it.
    """
    if item.status != "active" or not item.is_active:
        return False, _STATUS_REASON
    if _active_boost_exists(db, item.id):
        return False, _ACTIVE_BOOST_REASON
    return True, None


def _validate_boost_eligibility(db: Session, user: User, item: Item) -> Channel:
    """Shared ownership/eligibility validation (Rule 2.5). Raises 403/400/409."""
    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can boost this item",
        )
    boostable, reason = get_boost_eligibility(db, item)
    if not boostable:
        # Status-code contract preserved: status problems -> 400,
        # already-boosted conflict -> 409 (blueprint Rule 2.5).
        status_code = 409 if reason == _ACTIVE_BOOST_REASON else 400
        raise HTTPException(status_code=status_code, detail=reason)
    return channel


async def create_boost_order(db: Session, user: User, item: Item) -> dict:
    """Create a Stars invoice for a boost on this item (Rule 2.7)."""
    if not settings_registry.get_setting(db, "monetization_enabled"):
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
    if not settings_registry.get_setting(db, "monetization_enabled"):
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
    Active boosted items eligible for the pinned block of a surface
    (category browse or search results). Deterministic time-sliced rotation
    (Rule 4.2), no mutable state. NEVER called from
    services/recommendation.py (Rule 3.2 — feed isolation).
    """
    now = now or _now_utc()
    rows = db.execute(
        select(Boost, Item)
        .join(Item, Boost.item_id == Item.id)
        .where(
            Boost.ends_at > now,
            Item.status == "active",
            Item.is_active == True,
            # NB-56 (Rule 3.3): the pinned layer queries items itself — a
            # banned seller's boost must not surface above the organic
            # results even though the organic lists are filtered.
            ~owner_banned_pred(),
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
            if (i.title and q in i.title.lower())
            or (i.category and q in i.category.lower())
        ]

    if len(candidates) == 0:
        return []

    rotation_offset = (
        int(now.timestamp()) // (BOOST_ROTATION_MINUTES * 60) % len(candidates)
    )
    return candidates[rotation_offset:] + candidates[:rotation_offset]


def compose_pinned_page(
    db: Session, *,
    category: str | None = None,
    query_text: str | None = None,
    items: list,
    now: datetime | None = None,
    pinned: list | None = None,
) -> tuple[list, set[int]]:
    """
    Compose a page with the pinned boost layer applied — the ONE application
    point of the pin layer (D7) across the eligible surfaces (category browse
    and search results, Rule 3.1). Marks the organic list and returns the
    pinned block (rotation order, Rule 4.2) followed by organic minus pinned
    (Rule 3.4 — no duplicates on a page).

    Duck-typed contract: `items` and `pinned` are lists of objects exposing
    `.id` and a writable `.is_boosted` attribute (ItemResponse in the search
    caller, ORM Item in the browse caller — Item has no is_boosted column;
    dynamic attribute assignment works, Rule 3.3/3.4). Every pinned element
    is flagged `is_boosted=True` so `is_boosted` rides the dynamic attribute
    through model_validate in both callers. Does NOT touch `total` — the
    caller owns count semantics.
    """
    if pinned is None:
        pinned = get_pinned_boosted_items(
            db, category=category, query_text=query_text, now=now
        )
    pinned_ids = {i.id for i in pinned}
    for item in items:
        item.is_boosted = item.id in pinned_ids
    for pinned_item in pinned:
        pinned_item.is_boosted = True
    return pinned + [i for i in items if i.id not in pinned_ids], pinned_ids


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


def list_active_channel_boosts(db: Session, channel_id: int) -> list[dict]:
    """NB-48 (§2.3): active boosts for a channel, for the Stores boost card.

    Active-only: ends_at > now AND the item is still live (status=='active'
    AND is_active — sold/reported/soft-deleted items drop out per Rule 6.1).
    Defensive dedupe per item (latest id wins, mirroring get_boost_status);
    sorted ends_at ascending (soonest-expiring first for the "time remaining"
    card). Returns [{item_id, title, ends_at, source}].
    """
    now = _now_utc()
    rows = db.execute(
        select(Boost, Item)
        .join(Item, Boost.item_id == Item.id)
        .where(
            Boost.channel_id == channel_id,
            Boost.ends_at > now,
            Item.status == "active",
            Item.is_active == True,
        )
        .order_by(Boost.id.asc())
    ).all()
    by_item: dict[int, tuple] = {}
    for boost, item in rows:
        by_item[item.id] = (boost, item)  # later id overwrites -> latest wins
    summaries = [
        {
            "item_id": item.id,
            "title": item.title,
            "ends_at": boost.ends_at,
            "source": boost.source,
        }
        for boost, item in by_item.values()
    ]
    return sorted(summaries, key=lambda s: s["ends_at"])

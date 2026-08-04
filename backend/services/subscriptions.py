"""
Subscriptions — cap math, credit accounting, lapse mechanism (NB-46,
blueprint §2.3).

Phase 1 (TECH-26) scope: cap/credit/lapse primitives. Phase 3 (TECH-28)
adds order + fulfillment + state-update handling. `services/boost.py`
imports from here; this module imports models/constants/telegram_payments
ONLY — no import cycle.

The effective alert cap is THE single authority (blueprint D3): both
call sites (api/routes/alerts.py and services/alerting.py) delegate here.
"""

from datetime import datetime, timezone

import logging
import secrets

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import (
    ALL_IN_ONE_MONTHLY_BOOST_CREDIT,
    ALL_IN_ONE_PRICE_STARS,
    ALERTS_ONLY_PRICE_STARS,
    ALERTS_SUBSCRIPTION_EXTRA_ALERTS,
    MAX_ALERTS_PER_USER,
    SUBSCRIPTION_PERIOD_SECONDS,
    # NB-48 (§2.2): hub payload fields. ALERT_CAP_BANNER_THRESHOLD is the
    # banner display threshold; BOOST_* feed the hub's "from X Stars" floor
    # and duration copy. NO import of services/boost here (cycle rule —
    # boost.py imports subscriptions.py, never the reverse).
    ALERT_CAP_BANNER_THRESHOLD,
    BOOST_DURATION_DAYS,
    BOOST_PRICE_STARS,
)
from models import Alert, Boost, Subscription, User
from services.telegram_payments import star_payments

logger = logging.getLogger("index_subscriptions")

_PRODUCTS = {"alerts_only", "all_in_one"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_active_subscription(db: Session, user: User) -> Subscription | None:
    """The user's active subscription (status='active' AND period not ended)."""
    now = _now_utc()
    return db.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
            Subscription.current_period_end > now,
        )
        .order_by(Subscription.id.desc())
    )


def get_effective_alert_cap(db: Session, user: User) -> int:
    """The single cap authority (blueprint D3): free cap + subscription extra."""
    if get_active_subscription(db, user):
        return MAX_ALERTS_PER_USER + ALERTS_SUBSCRIPTION_EXTRA_ALERTS
    return MAX_ALERTS_PER_USER


def get_credit_boosts_remaining(db: Session, user: User) -> int:
    """
    Monthly all-in-one boost credit. 0 without an active all_in_one
    subscription. Credit expires at period end by construction (window
    query) — no rollover (Rule 7.3.2).
    """
    sub = get_active_subscription(db, user)
    if not sub or sub.product != "all_in_one":
        return 0
    used = db.scalar(
        select(func.count(Boost.id)).where(
            Boost.user_id == user.id,
            Boost.source == "credit",
            Boost.created_at >= sub.current_period_start,
            Boost.created_at <= sub.current_period_end,
        )
    ) or 0
    return max(0, ALL_IN_ONE_MONTHLY_BOOST_CREDIT - used)


def lapse_benefits(db: Session, user: User) -> None:
    """
    THE lapse-deactivation mechanism (Rule 7.1.2): deactivate alerts BEYOND
    the free cap, oldest-first by id, marking them lapsed=True — distinct
    from user pause (is_active=False, lapsed=False).
    """
    active_alerts = db.scalars(
        select(Alert)
        .where(Alert.user_id == user.id, Alert.is_active == True)
        .order_by(Alert.id.asc())
    ).all()
    for alert in active_alerts[MAX_ALERTS_PER_USER:]:
        alert.is_active = False
        alert.lapsed = True
    db.commit()


def reactivate_lapsed_alerts(db: Session, user: User) -> None:
    """
    On renewal: reactivate lapsed alerts oldest-first up to the new effective
    cap. Alerts past the cap stay lapsed.
    """
    cap = get_effective_alert_cap(db, user)
    active_count = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.user_id == user.id, Alert.is_active == True
        )
    ) or 0
    lapsed_alerts = db.scalars(
        select(Alert)
        .where(Alert.user_id == user.id, Alert.lapsed == True)
        .order_by(Alert.id.asc())
    ).all()
    for alert in lapsed_alerts:
        if active_count >= cap:
            break
        alert.is_active = True
        active_count += 1
    db.commit()


# ---------------------------------------------------------------------------
# Phase 3 (TECH-28): order + fulfillment + state updates
# ---------------------------------------------------------------------------

async def create_subscription_order(db: Session, user: User, product: str) -> dict:
    """Create a native 30-day auto-renewing Star subscription invoice
    (Rule 7.1.1). product in {"alerts_only", "all_in_one"}; no upgrade path
    in v1 (409 when an active subscription exists)."""
    if product not in _PRODUCTS:
        raise HTTPException(status_code=400, detail="Unknown subscription product")
    if get_active_subscription(db, user):
        raise HTTPException(
            status_code=409,
            detail="An active subscription already exists",
        )

    price = ALERTS_ONLY_PRICE_STARS if product == "alerts_only" else ALL_IN_ONE_PRICE_STARS
    title = "Alerts Only" if product == "alerts_only" else "All-in-One"
    payload = f"s:{user.id}:{product}:{secrets.token_hex(4)}"

    invoice_url = await star_payments.create_invoice_link(
        title=title,
        description="30-day auto-renewing Telegram Star subscription",
        payload=payload,
        prices=[(title, price)],
        subscription_period=SUBSCRIPTION_PERIOD_SECONDS,  # hard-locked 2592000 (XTR only)
    )
    return {"invoice_url": invoice_url, "payload": payload, "price_stars": price}


def fulfill_subscription_payment(
    db: Session, *,
    telegram_user_id: int,
    telegram_payment_charge_id: str,
    invoice_payload: str,
    total_amount: int,
    subscription_expiration_date,
    is_recurring: bool,
    is_first_recurring: bool,
) -> Subscription:
    """Idempotent on telegram_payment_charge_id (return existing row on
    replay). Initial charge and renewals land here; renewals update the SAME
    row's period_end while period_start stays the initial purchase. After
    activation, lapsed alerts reactivate up to the new effective cap."""
    existing = db.scalar(
        select(Subscription).where(
            Subscription.telegram_payment_charge_id == telegram_payment_charge_id)
    )
    if existing:
        return existing

    parts = invoice_payload.split(":")
    if len(parts) != 4 or parts[0] != "s" or parts[2] not in _PRODUCTS:
        raise HTTPException(status_code=400, detail="Invalid subscription invoice payload")
    try:
        user_id = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid subscription invoice payload")
    product = parts[2]

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.telegram_id != telegram_user_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot activate a subscription for a foreign user",
        )
    if subscription_expiration_date is None:
        raise HTTPException(
            status_code=400,
            detail="Missing subscription_expiration_date",
        )

    now = _now_utc()
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.id.desc())
    )
    if sub:
        # Renewal: update the SAME row; period_start stays the initial purchase.
        # The row's telegram_payment_charge_id stays the FIRST charge id — it is
        # the idempotency key and must never be overwritten (replaying the
        # initial charge must find this row).
        sub.status = "active"
        sub.current_period_end = subscription_expiration_date
        sub.is_recurring = True
    else:
        sub = Subscription(
            user_id=user.id,
            product=product,
            status="active",
            telegram_payment_charge_id=telegram_payment_charge_id,
            invoice_payload=invoice_payload,
            current_period_start=now,
            current_period_end=subscription_expiration_date,
            is_recurring=is_recurring,
        )
        db.add(sub)
    db.commit()
    db.refresh(sub)

    reactivate_lapsed_alerts(db, user)
    return sub


def handle_subscription_state_update(
    db: Session, *,
    telegram_user_id: int,
    invoice_payload: str,
    state: str,
) -> None:
    """User-side subscription updates (canceled/active/failed) from the PTB
    22.8 api_kwargs seam (D2). canceled/failed -> lapse_benefits; active ->
    reactivate. Unknown states log and are ignored. Last-write-wins (Rule
    6.6) — transient interleavings self-heal on the next event."""
    if state not in {"canceled", "active", "failed"}:
        logger.warning(f"subscriptions: unknown state {state!r} ignored")
        return

    user = db.scalar(select(User).where(User.telegram_id == telegram_user_id))
    if not user:
        logger.warning(f"subscriptions: no user for telegram_id {telegram_user_id}")
        return

    sub = db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.id.desc())
    )
    if not sub:
        logger.warning(f"subscriptions: no subscription for user {user.id}")
        return

    sub.status = state
    db.commit()

    if state in {"canceled", "failed"}:
        lapse_benefits(db, user)
    elif state == "active":
        reactivate_lapsed_alerts(db, user)


def get_subscription_status(db: Session, user: User) -> dict:
    """For the frontend subscription card (blueprint §2.3) and the NB-48
    hub (blueprint §2.2): the single "seller monetization context" payload
    (caps + banner threshold + prices + boost floor/duration)."""
    sub = get_active_subscription(db, user)
    # NB-48: the floor mirrors services.boost.get_boost_price's Other-bucket
    # fallback (boost._OTHER_FLOOR). Deliberate mirror: subscriptions.py must
    # NEVER import boost.py (cycle rule), so the floor is computed from the
    # constants directly. "Other" is the designated floor bucket (Rule 2.2);
    # min() guards a malformed config missing the key.
    boost_floor = BOOST_PRICE_STARS.get("Other", min(BOOST_PRICE_STARS.values()))
    if not sub:
        return {
            "product": None,
            "status": None,
            "current_period_end": None,
            "extra_alerts": 0,
            "credit_remaining": 0,
            "credit_total": 0,
            "free_cap": MAX_ALERTS_PER_USER,
            "effective_cap": get_effective_alert_cap(db, user),
            "cap_banner_threshold": ALERT_CAP_BANNER_THRESHOLD,
            "alerts_only_price_stars": ALERTS_ONLY_PRICE_STARS,
            "all_in_one_price_stars": ALL_IN_ONE_PRICE_STARS,
            "boost_floor_price_stars": boost_floor,
            "boost_duration_days": BOOST_DURATION_DAYS,
        }
    return {
        "product": sub.product,
        "status": sub.status,
        "current_period_end": sub.current_period_end,
        "extra_alerts": ALERTS_SUBSCRIPTION_EXTRA_ALERTS,
        "credit_remaining": get_credit_boosts_remaining(db, user),
        "credit_total": (
            ALL_IN_ONE_MONTHLY_BOOST_CREDIT if sub.product == "all_in_one" else 0
        ),
        "free_cap": MAX_ALERTS_PER_USER,
        "effective_cap": get_effective_alert_cap(db, user),
        "cap_banner_threshold": ALERT_CAP_BANNER_THRESHOLD,
        "alerts_only_price_stars": ALERTS_ONLY_PRICE_STARS,
        "all_in_one_price_stars": ALL_IN_ONE_PRICE_STARS,
        "boost_floor_price_stars": boost_floor,
        "boost_duration_days": BOOST_DURATION_DAYS,
    }

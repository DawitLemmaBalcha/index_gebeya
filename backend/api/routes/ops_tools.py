"""
NB-54: ops console Section 10 — Support Toolkit (blueprint §2.12).

Test boosts (source='test', D3 free-string source — no schema changes),
test subscriptions (grant + revoke with cap effects), the payment-webhook
simulator (drives the REAL fulfill paths, idempotent by charge id), and
deep-link generation. All actions are audited; operator discipline is
documented in the UI.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import BOOST_DURATION_DAYS, SUBSCRIPTION_PERIOD_SECONDS, WEB_APP_URL
from database import get_db
from models import Boost, Channel, Item, Subscription, User
from schemas import SimulatePaymentRequest, TestBoostRequest, TestSubscriptionRequest
from services import settings_registry
from services.audit import record_audit
from services.boost import fulfill_boost, get_boost_eligibility
from services.subscriptions import (
    fulfill_subscription_payment,
    lapse_benefits,
    reactivate_lapsed_alerts,
)

from .ops_auth import require_ops_admin

logger = logging.getLogger("index_ops_tools")

router = APIRouter()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _admin_user(request: Request) -> str:
    return request.session.get("ops_admin", {}).get("user", "admin")


# ---------------------------------------------------------------------------
# Test boosts (Rule 4.6.1 / 8.1)
# ---------------------------------------------------------------------------

@router.post("/test-boost")
def grant_test_boost(
    body: TestBoostRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    boostable, reason = get_boost_eligibility(db, item)
    if not boostable:
        raise HTTPException(status_code=409, detail=reason or "Item cannot be boosted")

    channel = db.get(Channel, item.channel_id)
    owner_telegram_id = channel.registered_by if channel else None
    if not owner_telegram_id:
        raise HTTPException(status_code=409, detail="Channel has no registered owner")

    user = db.scalar(select(User).where(User.telegram_id == owner_telegram_id))
    if not user:
        user = User(telegram_id=owner_telegram_id, username="unknown")
        db.add(user)
        db.flush()

    now = _now_utc()
    boost = Boost(
        item_id=item.id,
        channel_id=item.channel_id,
        user_id=user.id,
        source="test",
        price_paid_stars=None,
        telegram_payment_charge_id=None,
        starts_at=now,
        ends_at=now + timedelta(days=BOOST_DURATION_DAYS),
    )
    db.add(boost)
    db.commit()
    db.refresh(boost)

    record_audit(
        db,
        admin_user=_admin_user(request),
        action="grant_test_boost",
        section="tools",
        entity_type="boost",
        entity_id=str(boost.id),
        after={"item_id": item.id, "source": "test", "ends_at": boost.ends_at.isoformat()},
    )
    return {
        "boost_id": boost.id,
        "item_id": item.id,
        "source": "test",
        "ends_at": boost.ends_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Test subscriptions (Rule 8.1)
# ---------------------------------------------------------------------------

@router.post("/test-subscription")
def grant_test_subscription(
    body: TestSubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if body.product not in {"alerts_only", "all_in_one"}:
        raise HTTPException(status_code=400, detail="Unknown subscription product")
    user = db.scalar(select(User).where(User.telegram_id == body.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = _now_utc()
    sub = Subscription(
        user_id=user.id,
        product=body.product,
        status="active",
        telegram_payment_charge_id=None,
        invoice_payload=f"s:{user.id}:{body.product}:test:{secrets.token_hex(4)}",
        current_period_start=now,
        current_period_end=now + timedelta(seconds=SUBSCRIPTION_PERIOD_SECONDS),
        is_recurring=False,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    reactivate_lapsed_alerts(db, user)  # mirrors real fulfillment

    record_audit(
        db,
        admin_user=_admin_user(request),
        action="grant_test_subscription",
        section="tools",
        entity_type="subscription",
        entity_id=str(sub.id),
        after={"user_id": user.id, "product": body.product, "source": "test"},
    )
    return {"subscription_id": sub.id, "product": body.product, "status": "active"}


@router.post("/test-subscription/{subscription_id}/revoke")
def revoke_test_subscription(
    subscription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    user = db.get(User, sub.user_id)
    before_status = sub.status
    sub.status = "canceled"
    db.commit()

    if user:
        lapse_benefits(db, user)  # mirrors real lapse

    record_audit(
        db,
        admin_user=_admin_user(request),
        action="revoke_test_subscription",
        section="tools",
        entity_type="subscription",
        entity_id=str(sub.id),
        before={"status": before_status},
        after={"status": "canceled"},
    )
    return {"subscription_id": sub.id, "status": "canceled"}


# ---------------------------------------------------------------------------
# Payment-webhook simulator (Rule 8.2) — the primary UAT tool
# ---------------------------------------------------------------------------

@router.post("/simulate-payment")
def simulate_payment(
    body: SimulatePaymentRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Drives the exact fulfillment path the listener calls, without
    Telegram. Idempotent by charge id (both fulfill functions return the
    existing row on replay). Audit-logged."""
    if not settings_registry.get_setting(db, "monetization_enabled"):
        raise HTTPException(status_code=503, detail="Monetization is currently disabled")

    prefix = body.invoice_payload[:2]
    if prefix == "b:":
        parts = body.invoice_payload.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid boost invoice payload")
        try:
            item_id = int(parts[1])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid boost invoice payload")
        item = db.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        channel = db.get(Channel, item.channel_id)
        owner_telegram_id = channel.registered_by if channel else None
        if not owner_telegram_id:
            raise HTTPException(status_code=409, detail="Channel has no registered owner")

        boost = fulfill_boost(
            db,
            telegram_user_id=owner_telegram_id,
            telegram_payment_charge_id=body.telegram_payment_charge_id,
            invoice_payload=body.invoice_payload,
            total_amount=body.total_amount,
        )
        record_audit(
            db,
            admin_user=_admin_user(request),
            action="simulate_payment",
            section="tools",
            entity_type="payment",
            entity_id=body.telegram_payment_charge_id,
            after={"boost_id": boost.id},
        )
        return {"boost_id": boost.id, "replayed": boost.created_at is not None}

    if prefix == "s:":
        parts = body.invoice_payload.split(":")
        if len(parts) != 4 or parts[2] not in {"alerts_only", "all_in_one"}:
            raise HTTPException(status_code=400, detail="Invalid subscription invoice payload")
        try:
            user_id = int(parts[1])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid subscription invoice payload")
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        sub = fulfill_subscription_payment(
            db,
            telegram_user_id=user.telegram_id,
            telegram_payment_charge_id=body.telegram_payment_charge_id,
            invoice_payload=body.invoice_payload,
            total_amount=body.total_amount,
            subscription_expiration_date=body.subscription_expiration_date,
            is_recurring=body.is_recurring,
            is_first_recurring=body.is_first_recurring,
        )
        record_audit(
            db,
            admin_user=_admin_user(request),
            action="simulate_payment",
            section="tools",
            entity_type="payment",
            entity_id=body.telegram_payment_charge_id,
            after={"subscription_id": sub.id},
        )
        return {"subscription_id": sub.id}

    raise HTTPException(status_code=400, detail="Unknown invoice payload prefix")


# ---------------------------------------------------------------------------
# Deep-link generator (Rule 8.3)
# ---------------------------------------------------------------------------

@router.get("/deep-links")
def deep_links(
    item_id: int | None = None,
    channel_id: int | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if item_id is None and channel_id is None:
        raise HTTPException(status_code=400, detail="Provide item_id and/or channel_id")
    if item_id is not None:
        item = db.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        channel_id = channel_id or item.channel_id
    elif channel_id is not None:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

    return {
        "stores_url": f"{WEB_APP_URL}/stores/{channel_id}/{item_id}",
        "item_url": f"{WEB_APP_URL}/item/{item_id}" if item_id is not None else None,
    }

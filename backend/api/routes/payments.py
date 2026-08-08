"""
Internal payments router (blueprint §2.5) — the listener's fulfillment seam.

All endpoints authenticate via the internal bypass (D6):
`X-Internal-Service: index-listener` header + digit init_data (telegram_id).
Errors are translated to HTTP: 502 (Telegram upstream), 400 (bad payload),
404 (missing item). Registered in main.py with NO prefix.

Phase 2 (TECH-27): fulfill-boost. Phase 3 (TECH-28): fulfill-subscription
and subscription-state wired here (blueprint Phase 3 step 3).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import FulfillBoostRequest, FulfillSubscriptionRequest, SubscriptionStateRequest
from services import settings_registry
from services.auth import authenticate
from services.boost import fulfill_boost
from services.subscriptions import fulfill_subscription_payment, handle_subscription_state_update

logger = logging.getLogger("index_payments_routes")

router = APIRouter()


def _monetization_enabled_or_503(db: Session):
    """Kill switch (blueprint §6.1): registry read per request — fulfillment
    endpoints 503 — nothing activates. Instant effect, no restart."""
    if not settings_registry.get_setting(db, "monetization_enabled"):
        raise HTTPException(status_code=503, detail="Monetization is currently disabled")


@router.post("/internal/payments/fulfill-boost")
def fulfill_boost_route(
    body: FulfillBoostRequest,
    init_data: str = "",
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """Idempotent boost activation on successful_payment (Rule 2.7).
    init_data travels in the query string (listener wire format, §2.6)."""
    _monetization_enabled_or_503(db)
    if not body.telegram_payment_charge_id or not body.invoice_payload:
        raise HTTPException(status_code=400, detail="Missing charge id or invoice payload")

    user = authenticate(init_data or body.init_data or "", db, x_internal_service)
    try:
        boost = fulfill_boost(
            db,
            telegram_user_id=user.telegram_id,
            telegram_payment_charge_id=body.telegram_payment_charge_id,
            invoice_payload=body.invoice_payload,
            total_amount=body.total_amount,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"fulfill-boost failed: {e}")
        raise HTTPException(status_code=502, detail="Telegram fulfillment failed")
    return {"status": "ok", "boost_id": boost.id}


@router.post("/internal/payments/fulfill-subscription")
def fulfill_subscription_route(
    body: FulfillSubscriptionRequest,
    init_data: str = "",
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """Idempotent subscription activation on successful_payment (Rule 7.1.1)."""
    _monetization_enabled_or_503(db)
    if not body.telegram_payment_charge_id or not body.invoice_payload:
        raise HTTPException(status_code=400, detail="Missing charge id or invoice payload")

    user = authenticate(init_data or body.init_data or "", db, x_internal_service)
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"fulfill-subscription failed: {e}")
        raise HTTPException(status_code=502, detail="Telegram fulfillment failed")
    return {"status": "ok", "subscription_id": sub.id}


@router.post("/internal/payments/subscription-state")
def subscription_state_route(
    body: SubscriptionStateRequest,
    init_data: str = "",
    db: Session = Depends(get_db),
    x_internal_service: Optional[str] = Header(None, alias="X-Internal-Service"),
):
    """User-side subscription updates (canceled/active/failed) from the
    PTB 22.8 api_kwargs seam (D2)."""
    _monetization_enabled_or_503(db)
    user = authenticate(init_data or body.init_data or "", db, x_internal_service)
    handle_subscription_state_update(
        db,
        telegram_user_id=user.telegram_id,
        invoice_payload=body.invoice_payload,
        state=body.state,
    )
    return {"status": "ok"}

"""
Subscriptions router (blueprint §2.5) — buyer-facing subscription endpoints.

POST /order  — create a native 30-day Star subscription invoice
GET  /status — subscription status for the UI card (extra_alerts, credit)
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from constants import MONETIZATION_ENABLED
from database import get_db
from schemas import (
    SubscriptionOrderRequest,
    SubscriptionOrderResponse,
    SubscriptionStatusResponse,
)
from services.auth import authenticate
from services.subscriptions import create_subscription_order, get_subscription_status

logger = logging.getLogger("index_subscriptions_routes")

router = APIRouter()


def _monetization_enabled_or_503():
    """Kill switch (blueprint §6.1): monetization routes 503 when disabled."""
    from fastapi import HTTPException
    if not MONETIZATION_ENABLED:
        raise HTTPException(status_code=503, detail="Monetization is currently disabled")


@router.post("/order", response_model=SubscriptionOrderResponse)
async def create_subscription_order_route(
    body: SubscriptionOrderRequest,
    init_data: str = "",
    db: Session = Depends(get_db),
):
    """Create a Stars invoice for a subscription (Rule 7.1.1)."""
    _monetization_enabled_or_503()
    user = authenticate(init_data, db)
    return await create_subscription_order(db, user, body.product)


@router.get("/status", response_model=SubscriptionStatusResponse)
def subscription_status_route(
    init_data: str,
    db: Session = Depends(get_db),
):
    """Subscription status for the UI card (blueprint §2.3)."""
    _monetization_enabled_or_503()
    user = authenticate(init_data, db)
    return get_subscription_status(db, user)

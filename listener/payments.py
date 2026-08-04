"""
Listener-side payment handling (blueprint §2.6) — the PTB side of the seam.

The listener owns the Telegram update stream. It translates payment updates
into backend calls over the internal seam (D6) and does ZERO business logic:

- handle_pre_checkout: ONLY answer(True) — the 10-second clock is running.
  No DB, no client call, no network (blueprint §6.3).
- handle_successful_payment: payload-prefix routing ('b:' boost, 's:'
  subscription). Delivery happens HERE, never in pre_checkout. Best-effort:
  failures log; the backend reconcile pass (§6) replays missed payments.
- handle_subscription_update: PTB 22.8 api_kwargs seam (D2) — Bot API 10.0
  has no Update.subscription; unknown keys land in update.api_kwargs.
"""

import os

from telegram import Update
from telegram.ext import ContextTypes

from client import fulfill_boost_api, fulfill_subscription_api, subscription_state_api
from config import logger

_SUBSCRIPTION_STATES = {"canceled", "active", "failed"}

# Kill switch (blueprint §6.1): when 0 the listener keeps its handlers
# registered but the payload-prefix routing logs-and-drops — nothing
# activates. The backend fulfillment endpoints are 503 too, so this check is
# the listener half of the same switch.
MONETIZATION_ENABLED = os.getenv("MONETIZATION_ENABLED", "1") != "0"


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ZERO-work passthrough — the 10s pre_checkout deadline is running.
    Exception -> log; Telegram cancels the transaction with zero charge
    (buyer can retry; nothing was charged)."""
    try:
        await update.pre_checkout_query.answer(True)
    except Exception as e:
        logger.warning(f"pre_checkout answer failed: {e}")


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.effective_message.successful_payment
    user_id = update.effective_user.id
    payload = sp.invoice_payload or ""
    prefix = payload[:2]

    if not MONETIZATION_ENABLED:
        logger.info(f"Payment {sp.telegram_payment_charge_id} dropped (MONETIZATION_ENABLED=0)")
        return

    if prefix == "b:":
        await fulfill_boost_api(
            user_id,
            sp.telegram_payment_charge_id,
            payload,
            sp.total_amount,
        )
    elif prefix == "s:":
        await fulfill_subscription_api(
            user_id,
            sp.telegram_payment_charge_id,
            payload,
            sp.total_amount,
            sp.subscription_expiration_date,
            sp.is_recurring,
            sp.is_first_recurring,
        )
    else:
        logger.warning(f"Unknown payment payload prefix {prefix!r} — dropped")


async def handle_subscription_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """BotSubscriptionUpdated via the PTB 22.8 api_kwargs seam (D2)."""
    sub = update.api_kwargs.get("subscription")
    if not isinstance(sub, dict) or "state" not in sub:
        return

    state = sub.get("state")
    if state not in _SUBSCRIPTION_STATES:
        logger.warning(f"Unknown subscription state {state!r} — dropped")
        return

    if not MONETIZATION_ENABLED:
        logger.info(f"Subscription state {state} dropped (MONETIZATION_ENABLED=0)")
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        logger.warning("subscription update without effective_user — dropped")
        return

    await subscription_state_api(user_id, sub.get("invoice_payload", ""), state)

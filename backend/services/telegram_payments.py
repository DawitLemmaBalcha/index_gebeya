"""
Star-payments adapter seam (blueprint §2.1, D5).

Everything the backend needs from Telegram money-wise lives behind the
StarPaymentsAdapter port. The backend has NO python-telegram-bot dependency:
this is the raw-httpx implementation (owner_dm.py pattern). The listener
does NOT import this module — it speaks PTB objects natively.

Invariants:
  - the port returns Telegram's invoice URL string only;
  - never raises without logging; network errors -> RuntimeError (route
    modules translate to HTTPException 502);
  - price amounts are always int Stars.
"""

import os
import logging
import httpx
from typing import Protocol, Optional, List, Tuple

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logger = logging.getLogger("index_payments")

_API_BASE = "https://api.telegram.org"


class StarPaymentsAdapter(Protocol):
    async def create_invoice_link(
        self, *,
        title: str,
        description: str,
        payload: str,
        currency: str = "XTR",
        prices: List[Tuple[str, int]],
        subscription_period: Optional[int] = None,
    ) -> str:
        """POST /bot{TOKEN}/createInvoiceLink — returns the invoice URL."""
        ...

    async def edit_user_star_subscription(
        self, *,
        user_id: int,
        telegram_payment_charge_id: str,
        is_canceled: bool,
    ) -> bool:
        """POST /bot{TOKEN}/editUserStarSubscription — user-side cancel."""
        ...

    async def get_star_transactions(
        self, *,
        offset: int = 0,
        limit: int = 100,
    ) -> List[dict]:
        """GET /bot{TOKEN}/getStarTransactions — ledger reconciliation.
        StarTransaction.id == telegram_payment_charge_id for incoming."""
        ...

    async def get_my_star_balance(self) -> int:
        """GET /bot{TOKEN}/getMyStarBalance."""
        ...

    async def refund_star_payment(self, *, telegram_payment_charge_id: str) -> bool:
        """POST /bot{TOKEN}/refundStarPayment — operator refunds (NB-53).
        Returns True on success; raises RuntimeError on API failure."""
        ...


class HttpxStarPaymentsAdapter:
    """The real adapter: raw httpx to api.telegram.org (D5)."""

    def __init__(self, bot_token: Optional[str] = None) -> None:
        self.bot_token = bot_token or BOT_TOKEN

    def _url(self, method: str) -> str:
        return f"{_API_BASE}/bot{self.bot_token}/{method}"

    async def _post(self, method: str, payload: dict) -> dict:
        if not self.bot_token:
            logger.warning("telegram_payments: TELEGRAM_BOT_TOKEN is not set")
            raise RuntimeError("Telegram API error: missing bot token")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._url(method), json=payload)
        if resp.status_code != 200:
            detail = resp.text[:200]
            logger.warning(f"telegram_payments: {method} failed ({resp.status_code}): {detail}")
            raise RuntimeError(f"Telegram API error: {detail}")
        data = resp.json()
        if not data.get("ok"):
            detail = str(data.get("description", data))[:200]
            logger.warning(f"telegram_payments: {method} not ok: {detail}")
            raise RuntimeError(f"Telegram API error: {detail}")
        return data.get("result", data)

    async def _get(self, method: str, params: Optional[dict] = None) -> dict:
        if not self.bot_token:
            logger.warning("telegram_payments: TELEGRAM_BOT_TOKEN is not set")
            raise RuntimeError("Telegram API error: missing bot token")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self._url(method), params=params)
        if resp.status_code != 200:
            detail = resp.text[:200]
            logger.warning(f"telegram_payments: {method} failed ({resp.status_code}): {detail}")
            raise RuntimeError(f"Telegram API error: {detail}")
        data = resp.json()
        if not data.get("ok"):
            detail = str(data.get("description", data))[:200]
            logger.warning(f"telegram_payments: {method} not ok: {detail}")
            raise RuntimeError(f"Telegram API error: {detail}")
        return data.get("result", data)

    async def create_invoice_link(
        self, *,
        title: str,
        description: str,
        payload: str,
        currency: str = "XTR",
        prices: List[Tuple[str, int]],
        subscription_period: Optional[int] = None,
    ) -> str:
        body = {
            "title": title,
            "description": description,
            "payload": payload,
            "currency": currency,
            "prices": [{"label": label, "amount": amount} for label, amount in prices],
        }
        if subscription_period is not None:
            body["subscription_period"] = subscription_period
        result = await self._post("createInvoiceLink", body)
        return result  # the invoice URL string

    async def edit_user_star_subscription(
        self, *,
        user_id: int,
        telegram_payment_charge_id: str,
        is_canceled: bool,
    ) -> bool:
        await self._post("editUserStarSubscription", {
            "user_id": user_id,
            "telegram_payment_charge_id": telegram_payment_charge_id,
            "is_canceled": is_canceled,
        })
        return True

    async def get_star_transactions(
        self, *,
        offset: int = 0,
        limit: int = 100,
    ) -> List[dict]:
        return await self._get("getStarTransactions", {
            "offset": offset,
            "limit": limit,
        })

    async def get_my_star_balance(self) -> int:
        return await self._get("getMyStarBalance")

    async def refund_star_payment(self, *, telegram_payment_charge_id: str) -> bool:
        await self._post("refundStarPayment", {
            "telegram_payment_charge_id": telegram_payment_charge_id,
        })
        return True


# module-level default instance for production;
# tests monkeypatch `services.boost.star_payments` / `services.subscriptions.star_payments`
star_payments: StarPaymentsAdapter = HttpxStarPaymentsAdapter()

"""
FakeStarPaymentsAdapter — the second adapter implementation for the
StarPaymentsAdapter port (blueprint §5.1). Makes the Telegram seam real in
tests: every call is recorded (assertable) and invoice URLs are deterministic.
No network access, ever.

Tests install it via:
    monkeypatch.setattr("services.boost.star_payments", fake)
    monkeypatch.setattr("services.subscriptions.star_payments", fake)
"""


class FakeStarPaymentsAdapter:
    """In-memory StarPaymentsAdapter for tests (blueprint §5.1)."""

    def __init__(self):
        self.calls = []          # recorded call dicts, in order
        self.invoice_counter = 0
        self.ledger = []         # seeded get_star_transactions results

    # --- Protocol implementation ---

    async def create_invoice_link(
        self, *, title, description, payload, currency="XTR",
        prices, subscription_period=None
    ):
        self.calls.append({
            "method": "create_invoice_link",
            "title": title,
            "description": description,
            "payload": payload,
            "currency": currency,
            "prices": prices,
            "subscription_period": subscription_period,
        })
        self.invoice_counter += 1
        return f"https://t.me/fake-invoice/{self.invoice_counter}"

    async def edit_user_star_subscription(self, *, user_id,
                                          telegram_payment_charge_id,
                                          is_canceled):
        self.calls.append({
            "method": "edit_user_star_subscription",
            "user_id": user_id,
            "telegram_payment_charge_id": telegram_payment_charge_id,
            "is_canceled": is_canceled,
        })
        return True

    async def get_star_transactions(self, *, offset=0, limit=100):
        return self.ledger[offset:offset + limit]

    async def get_my_star_balance(self):
        return 0

    async def refund_star_payment(self, *, telegram_payment_charge_id):
        self.calls.append({
            "method": "refund_star_payment",
            "telegram_payment_charge_id": telegram_payment_charge_id,
        })
        return True

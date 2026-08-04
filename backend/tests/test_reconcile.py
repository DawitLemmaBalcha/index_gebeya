"""
Star-payments reconciliation tests (TECH-31, blueprint §6/§5.2).

reconcile_star_payments replays missed successful_payment events from
getStarTransactions: each incoming invoice transaction whose id has no
Boost/Subscription row is re-fulfilled idempotently. The watermark is the
newest fulfillment row's created_at — DB-backed, survives restarts.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from models import User, Channel, Item, Boost, Subscription
from services.reconciliation import reconcile_star_payments
from tests.fake_telegram_payments import FakeStarPaymentsAdapter


def _make_seller_item(db, *, telegram_id=111, title="Recon Item"):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username=f"ch_recon_{telegram_id}", title="Recon Channel",
                      registered_by=telegram_id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id, title=title, category="Mobile Phones",
        price=100.0, status="active", is_active=True, image_path="r.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


def _tx(charge_id, *, amount=150, payload="b:1:abc", user_id=111,
        date=None, subscription_period=None, outgoing=False):
    tx = {
        "id": charge_id,
        "amount": amount,
        "date": int((date or datetime.now(timezone.utc)).timestamp()),
    }
    if not outgoing:
        source = {
            "type": "user",
            "transaction_type": "invoice_payment",
            "user": {"id": user_id},
            "invoice_payload": payload,
        }
        if subscription_period:
            source["subscription_period"] = subscription_period
        tx["source"] = source
    return tx


class TestReconcileStarPayments:
    def _install(self, db_session, monkeypatch, *transactions):
        fake = FakeStarPaymentsAdapter()
        fake.ledger = list(transactions)
        monkeypatch.setattr("services.reconciliation.star_payments", fake)
        return fake

    def test_replays_missed_boost(self, db_session, monkeypatch):
        _, _, item = _make_seller_item(db_session)
        tx = _tx("chg_recon_b1", payload=f"b:{item.id}:nonce")
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        boost = db_session.scalar(select(Boost).where(
            Boost.telegram_payment_charge_id == "chg_recon_b1"))
        assert boost is not None
        assert boost.item_id == item.id
        assert boost.price_paid_stars == 150
        assert summary["replayed_boost"] == 1

    def test_replay_is_idempotent_across_runs(self, db_session, monkeypatch):
        _, _, item = _make_seller_item(db_session)
        tx = _tx("chg_recon_b2", payload=f"b:{item.id}:nonce")
        self._install(db_session, monkeypatch, tx)

        first = asyncio.run(reconcile_star_payments(db_session))
        second = asyncio.run(reconcile_star_payments(db_session))

        assert first["replayed_boost"] == 1
        assert second["replayed_boost"] == 0  # watermark advanced + row exists
        count = db_session.scalar(select(Boost).where(
            Boost.telegram_payment_charge_id == "chg_recon_b2"))
        assert count is not None

    def test_replays_missed_subscription_with_period(self, db_session, monkeypatch):
        user = User(telegram_id=111, username="u111")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        charge_date = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        tx = _tx(
            "chg_recon_s1",
            payload=f"s:{user.id}:alerts_only:nonce",
            date=charge_date,
            subscription_period=2592000,
        )
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        sub = db_session.scalar(select(Subscription).where(
            Subscription.telegram_payment_charge_id == "chg_recon_s1"))
        assert sub is not None
        assert sub.product == "alerts_only"
        assert sub.status == "active"
        # period_end derived from the charge date + subscription_period
        expected = charge_date + timedelta(seconds=2592000)
        assert abs((sub.current_period_end - expected).total_seconds()) < 60
        assert summary["replayed_subscription"] == 1

    def test_skips_unknown_payload_prefix(self, db_session, monkeypatch):
        _make_seller_item(db_session)
        tx = _tx("chg_recon_x", payload="z:garbage:data")
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        assert summary["replayed_boost"] == 0
        assert summary["replayed_subscription"] == 0
        assert summary["skipped"] == 1

    def test_skips_outgoing_transactions(self, db_session, monkeypatch):
        _make_seller_item(db_session)
        tx = _tx("chg_recon_out", outgoing=True)
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        assert summary["skipped"] == 1

    def test_skips_transactions_older_than_watermark(self, db_session, monkeypatch):
        user, _, item = _make_seller_item(db_session)
        # An already-fulfilled boost defines the watermark...
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_recon_old",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()
        db_session.refresh(user)
        # ...and a transaction that predates it must NOT be replayed.
        old_date = now - timedelta(days=3)
        tx = _tx("chg_recon_older", payload=f"b:{item.id}:nonce", date=old_date)
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        assert summary["skipped"] == 1
        assert db_session.scalar(select(Boost).where(
            Boost.telegram_payment_charge_id == "chg_recon_older")) is None

    def test_replays_missed_payment_in_same_second_as_watermark(self, db_session, monkeypatch):
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        # An already-fulfilled boost defines the watermark at `now`...
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_recon_wm",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()
        # ...and a DIFFERENT missed payment timestamped in the same second
        # (Telegram dates are second-granularity) must be REPLAYED, not
        # skipped by the watermark. The charge-exists guard is the
        # idempotency backstop; the watermark only filters the ancient ledger.
        tx = _tx("chg_recon_same_sec", payload=f"b:{item.id}:nonce", date=now)
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        assert summary["replayed_boost"] == 1
        assert db_session.scalar(select(Boost).where(
            Boost.telegram_payment_charge_id == "chg_recon_same_sec")) is not None

    def test_skips_already_fulfilled_charge(self, db_session, monkeypatch):
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_recon_done",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()
        tx = _tx("chg_recon_done", payload=f"b:{item.id}:nonce", date=now + timedelta(hours=1))
        self._install(db_session, monkeypatch, tx)

        summary = asyncio.run(reconcile_star_payments(db_session))

        assert summary["replayed_boost"] == 0
        assert summary["skipped"] == 1

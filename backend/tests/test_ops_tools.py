"""
NB-54: ops console Section 10 — Support Toolkit (blueprint §2.12).

Test boosts (source='test'), test subscriptions (grant/revoke with cap
effects), the payment-webhook simulator driving the REAL fulfillment
paths (idempotent by charge id — the centerpiece), deep links.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from constants import BOOST_DURATION_DAYS
from database import get_db
from models import Alert, AuditLog, Boost, Channel, Item, Subscription, User
from tests.fake_telegram_payments import FakeStarPaymentsAdapter

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _tools_client(db_session):
    from api.routes import ops_auth, ops_tools

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_tools.router, prefix="/ops/tools")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    login = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert login.status_code == 200
    return client


def _seller(db, *, telegram_id=111, category="Mobile Phones"):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username=f"ch_t{telegram_id}", title="C", registered_by=telegram_id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id, title="iPhone", category=category,
        subcategory="Android Phones", status="active", is_active=True,
        image_path="x.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


def _lapsed_alerts(db, user, count=25):
    for i in range(count):
        db.add(Alert(
            user_id=user.id, query_text=f"q{i}", is_active=False, lapsed=True,
        ))
    db.commit()


class TestTestBoost:
    def test_grants_test_boost_with_source_test(self, db_session):
        user, channel, item = _seller(db_session)
        client = _tools_client(db_session)
        resp = client.post("/ops/tools/test-boost", json={"item_id": item.id})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source"] == "test"

        boost = db_session.get(Boost, data["boost_id"])
        assert boost.source == "test"
        assert boost.price_paid_stars is None
        assert boost.telegram_payment_charge_id is None
        assert (boost.ends_at - boost.starts_at).days == BOOST_DURATION_DAYS

        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "grant_test_boost")
        )
        assert audit is not None
        assert audit.entity_type == "boost"
        assert audit.after["source"] == "test"

    def test_double_grant_409(self, db_session):
        user, channel, item = _seller(db_session)
        client = _tools_client(db_session)
        assert client.post("/ops/tools/test-boost", json={"item_id": item.id}).status_code == 200
        assert client.post("/ops/tools/test-boost", json={"item_id": item.id}).status_code == 409

    def test_missing_item_404(self, db_session):
        client = _tools_client(db_session)
        assert client.post("/ops/tools/test-boost", json={"item_id": 99999}).status_code == 404


class TestTestSubscription:
    def test_grant_activates_and_raises_effective_cap(self, db_session):
        user, channel, item = _seller(db_session)
        _lapsed_alerts(db_session, user, count=35)  # 15 beyond the free cap
        client = _tools_client(db_session)

        resp = client.post(
            "/ops/tools/test-subscription",
            json={"user_id": user.telegram_id, "product": "all_in_one"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["product"] == "all_in_one"

        sub = db_session.get(Subscription, data["subscription_id"])
        assert sub.status == "active"
        assert sub.telegram_payment_charge_id is None
        assert ":test:" in sub.invoice_payload
        assert sub.is_recurring is False

        # lapsed alerts reactivated up to the new cap (20 + 10)
        active = db_session.scalar(
            select(Alert).where(Alert.user_id == user.id, Alert.is_active == True)
        )
        from sqlalchemy import func
        active_count = db_session.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id, Alert.is_active == True
            )
        )
        assert active_count == 30

        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "grant_test_subscription")
        )
        assert audit is not None

    def test_revoke_cancels_and_lapses_extras(self, db_session):
        user, channel, item = _seller(db_session)
        _lapsed_alerts(db_session, user, count=35)
        client = _tools_client(db_session)
        grant = client.post(
            "/ops/tools/test-subscription",
            json={"user_id": user.telegram_id, "product": "alerts_only"},
        ).json()
        sub_id = grant["subscription_id"]

        resp = client.post(f"/ops/tools/test-subscription/{sub_id}/revoke")
        assert resp.status_code == 200, resp.text
        sub = db_session.get(Subscription, sub_id)
        assert sub.status == "canceled"

        from sqlalchemy import func
        active_count = db_session.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id, Alert.is_active == True
            )
        )
        assert active_count == 20  # back to the free cap

        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "revoke_test_subscription")
        )
        assert audit is not None

    def test_unknown_user_404(self, db_session):
        client = _tools_client(db_session)
        assert client.post(
            "/ops/tools/test-subscription",
            json={"user_id": 999999, "product": "alerts_only"},
        ).status_code == 404


class TestSimulator:
    """The primary UAT tool — drives the EXACT fulfillment paths the
    listener calls, without Telegram. Idempotent by charge id."""

    def test_boost_payload_drives_real_fulfillment(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.boost.star_payments", fake)
        user, channel, item = _seller(db_session)

        client = _tools_client(db_session)
        resp = client.post("/ops/tools/simulate-payment", json={
            "telegram_payment_charge_id": "chg_sim_b",
            "invoice_payload": f"b:{item.id}:nonce",
            "total_amount": 150,
        })
        assert resp.status_code == 200, resp.text

        boost = db_session.scalar(
            select(Boost).where(Boost.telegram_payment_charge_id == "chg_sim_b")
        )
        assert boost is not None
        assert boost.source == "paid"
        assert boost.price_paid_stars == 150  # the charged amount, not a re-read

        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "simulate_payment")
        )
        assert audit is not None
        assert audit.entity_id == "chg_sim_b"
        assert audit.after["boost_id"] == boost.id

    def test_replay_same_charge_id_is_idempotent(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.boost.star_payments", fake)
        user, channel, item = _seller(db_session)

        client = _tools_client(db_session)
        body = {
            "telegram_payment_charge_id": "chg_sim_replay",
            "invoice_payload": f"b:{item.id}:nonce",
            "total_amount": 150,
        }
        first = client.post("/ops/tools/simulate-payment", json=body).json()
        second = client.post("/ops/tools/simulate-payment", json=body).json()

        assert first["boost_id"] == second["boost_id"]
        boosts = db_session.execute(
            select(Boost).where(Boost.telegram_payment_charge_id == "chg_sim_replay")
        ).scalars().all()
        assert len(boosts) == 1

    def test_subscription_payload_drives_real_fulfillment(self, db_session):
        user, channel, item = _seller(db_session)
        _lapsed_alerts(db_session, user, count=35)

        client = _tools_client(db_session)
        resp = client.post("/ops/tools/simulate-payment", json={
            "telegram_payment_charge_id": "chg_sim_s",
            "invoice_payload": f"s:{user.id}:alerts_only:nonce",
            "total_amount": 30,
            "subscription_expiration_date": (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).isoformat(),
        })
        assert resp.status_code == 200, resp.text

        sub = db_session.scalar(
            select(Subscription).where(Subscription.telegram_payment_charge_id == "chg_sim_s")
        )
        assert sub is not None
        assert sub.status == "active"

        from sqlalchemy import func
        active_count = db_session.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id, Alert.is_active == True
            )
        )
        assert active_count == 30  # lapsed alerts reactivated (real path)

    def test_simulator_503_when_monetization_disabled(self, db_session):
        from services.settings_registry import set_setting
        set_setting(db_session, "monetization_enabled", "false")
        client = _tools_client(db_session)
        resp = client.post("/ops/tools/simulate-payment", json={
            "telegram_payment_charge_id": "chg_sim_off",
            "invoice_payload": "b:1:nonce",
            "total_amount": 150,
        })
        assert resp.status_code == 503

    def test_unknown_prefix_400(self, db_session):
        client = _tools_client(db_session)
        resp = client.post("/ops/tools/simulate-payment", json={
            "telegram_payment_charge_id": "chg_sim_x",
            "invoice_payload": "x:1:nonce",
            "total_amount": 150,
        })
        assert resp.status_code == 400


class TestDeepLinks:
    def test_deep_links_shape(self, db_session):
        user, channel, item = _seller(db_session)
        client = _tools_client(db_session)
        resp = client.get(
            "/ops/tools/deep-links",
            params={"item_id": item.id},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["item_url"].endswith(f"/item/{item.id}")
        assert data["stores_url"].endswith(f"/stores/{channel.id}/{item.id}")

    def test_deep_links_derives_channel(self, db_session):
        user, channel, item = _seller(db_session)
        client = _tools_client(db_session)
        resp = client.get(
            "/ops/tools/deep-links",
            params={"item_id": item.id, "channel_id": channel.id},
        )
        assert resp.status_code == 200
        assert resp.json()["stores_url"].endswith(f"/stores/{channel.id}/{item.id}")

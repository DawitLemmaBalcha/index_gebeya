"""
NB-51: ops monetization section (blueprint §2.9) + the D11 regression gate
(503 paths preserved under registry control).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from constants import BOOST_PRICE_STARS
from database import get_db
from models import AuditLog, Boost, Channel, Item, Subscription, User
from services.boost_pricing import seed_boost_prices, set_boost_price
from services.settings_registry import get_setting
from tests.fake_telegram_payments import FakeStarPaymentsAdapter

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _monetization_client(db_session):
    from api.routes import ops_auth, ops_monetization

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_monetization.router, prefix="/ops/monetization")

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


def _seller(db, *, category="Mobile Phones", subcategory="Android Phones"):
    user = User(telegram_id=111, username="u111")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username="ch_m", title="C", registered_by=111)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id, title="iPhone", category=category,
        subcategory=subcategory, status="active", is_active=True, image_path="x.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


def _active_boost(db, item, user, *, days_ago=0, ends_in_days=7, charge_id="chg_x"):
    now = datetime.now(timezone.utc)
    boost = Boost(
        item_id=item.id, channel_id=item.channel_id, user_id=user.id,
        source="paid", price_paid_stars=150,
        telegram_payment_charge_id=charge_id,
        starts_at=now - timedelta(days=days_ago),
        ends_at=now + timedelta(days=ends_in_days),
        created_at=now - timedelta(days=days_ago),
    )
    db.add(boost)
    db.commit()
    db.refresh(boost)
    return boost


class TestPrices:
    def test_prices_include_demand_context(self, db_session):
        seed_boost_prices(db_session)
        user, channel, item = _seller(db_session)
        now = datetime.now(timezone.utc)
        # active boost (this week)
        _active_boost(db_session, item, user, days_ago=1, charge_id="chg_d1")
        # expired boost created this week
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150, telegram_payment_charge_id="chg_d2",
            starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=3),
            created_at=now - timedelta(days=5),
        ))
        # boost created > 7d ago but still active (no this-week)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="credit", price_paid_stars=None, telegram_payment_charge_id=None,
            starts_at=now - timedelta(days=10), ends_at=now + timedelta(days=2),
            created_at=now - timedelta(days=10),
        ))
        db_session.commit()

        client = _monetization_client(db_session)
        resp = client.get("/ops/monetization/prices")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "generated_at" in data
        cats = {c["category"]: c for c in data["categories"]}
        rows = {r["subcategory"]: r for r in cats["Mobile Phones"]["rows"]}
        assert rows["Android Phones"]["price_stars"] == BOOST_PRICE_STARS["Mobile Phones"]
        assert rows["Android Phones"]["active_boosts"] == 2   # two active rows (paid + credit)
        assert rows["Android Phones"]["boosts_this_week"] == 2  # chg_d1 + chg_d2
        assert rows[""]["active_boosts"] == 0

    def test_put_price_updates_row_cache_and_audit(self, db_session):
        seed_boost_prices(db_session)
        client = _monetization_client(db_session)
        old = BOOST_PRICE_STARS["Mobile Phones"]

        resp = client.put(
            f"/ops/monetization/prices/{quote('Mobile Phones')}/{quote('Android Phones')}",
            json={"price_stars": 321},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["price_stars"] == 321

        # cache invalidation -> the service sees the new price immediately
        from services.boost_pricing import get_boost_price_by_key
        assert get_boost_price_by_key(db_session, "Mobile Phones", "Android Phones") == 321

        # audit row with correct before/after
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "update_boost_price")
        )
        assert audit is not None
        assert audit.section == "monetization"
        assert audit.admin_user == ADMIN_USER
        assert audit.entity_type == "boost_price"
        assert audit.entity_id == "Mobile Phones/Android Phones"
        assert audit.before == {"price_stars": old}
        assert audit.after == {"price_stars": 321}

    def test_put_price_validation(self, db_session):
        client = _monetization_client(db_session)
        assert client.put(
            f"/ops/monetization/prices/{quote('Mobile Phones')}/{quote('Android Phones')}",
            json={"price_stars": 0},
        ).status_code == 400
        assert client.put(
            f"/ops/monetization/prices/{quote('Mobile Phones')}/{quote('Android Phones')}",
            json={"price_stars": 10001},
        ).status_code == 400


class TestBulk:
    def _seed_category(self, db_session):
        seed_boost_prices(db_session)

    def test_bulk_set_category(self, db_session):
        self._seed_category(db_session)
        client = _monetization_client(db_session)
        resp = client.post(
            "/ops/monetization/prices/bulk",
            json={"action": "set_category", "category": "Mobile Phones", "price_stars": 60},
        )
        assert resp.status_code == 200, resp.text
        for sub in ["Android Phones", "iPhones", ""]:
            from services.boost_pricing import get_boost_price_by_key
            assert get_boost_price_by_key(db_session, "Mobile Phones", sub) == 60
        # other categories untouched
        assert get_boost_price_by_key(db_session, "Other", "Mixed") == BOOST_PRICE_STARS["Other"]
        # one audit row per category
        rows = db_session.scalars(
            select(AuditLog).where(AuditLog.action == "bulk_update_boost_prices")
        ).all()
        assert len(rows) == 1
        assert rows[0].entity_id == "Mobile Phones"

    def test_bulk_percent(self, db_session):
        self._seed_category(db_session)
        client = _monetization_client(db_session)
        base = BOOST_PRICE_STARS["Mobile Phones"]  # 150
        resp = client.post(
            "/ops/monetization/prices/bulk",
            json={"action": "percent", "category": "Mobile Phones", "percent": 50},
        )
        assert resp.status_code == 200
        from services.boost_pricing import get_boost_price_by_key
        assert get_boost_price_by_key(db_session, "Mobile Phones", "Android Phones") == base * 3 // 2

    def test_bulk_reset_to_constant(self, db_session):
        self._seed_category(db_session)
        client = _monetization_client(db_session)
        client.post(
            "/ops/monetization/prices/bulk",
            json={"action": "set_category", "category": "Mobile Phones", "price_stars": 60},
        )
        resp = client.post(
            "/ops/monetization/prices/bulk",
            json={"action": "reset", "category": "Mobile Phones"},
        )
        assert resp.status_code == 200
        from services.boost_pricing import get_boost_price_by_key
        assert get_boost_price_by_key(db_session, "Mobile Phones", "Android Phones") == BOOST_PRICE_STARS["Mobile Phones"]

    def test_bulk_single_subcategory_target(self, db_session):
        self._seed_category(db_session)
        client = _monetization_client(db_session)
        resp = client.post(
            "/ops/monetization/prices/bulk",
            json={"action": "set_category", "category": "Mobile Phones",
                  "subcategory": "iPhones", "price_stars": 99},
        )
        assert resp.status_code == 200
        from services.boost_pricing import get_boost_price_by_key
        assert get_boost_price_by_key(db_session, "Mobile Phones", "iPhones") == 99
        assert get_boost_price_by_key(db_session, "Mobile Phones", "Android Phones") == BOOST_PRICE_STARS["Mobile Phones"]


class TestToggles:
    def test_toggles_surface_and_flip_instantly(self, db_session):
        client = _monetization_client(db_session)
        resp = client.get("/ops/monetization/toggles")
        assert resp.status_code == 200
        keys = {t["key"] for t in resp.json()}
        assert keys == {
            "monetization_enabled", "boost_purchases_enabled",
            "subscription_purchases_enabled", "credit_boosts_enabled",
        }

        assert get_setting(db_session, "monetization_enabled") is True
        resp = client.put("/ops/monetization/toggles/monetization_enabled", json={"value": False})
        assert resp.status_code == 200, resp.text
        assert get_setting(db_session, "monetization_enabled") is False
        # audit row
        assert db_session.scalar(
            select(AuditLog).where(AuditLog.action == "set_toggle")
        ) is not None

    def test_unknown_toggle_404(self, db_session):
        client = _monetization_client(db_session)
        assert client.put(
            "/ops/monetization/toggles/not_a_toggle", json={"value": True}
        ).status_code == 404


class TestSubscriptionSettings:
    def test_settings_surface_and_edit(self, db_session):
        client = _monetization_client(db_session)
        resp = client.get("/ops/monetization/settings")
        assert resp.status_code == 200
        keys = {s["key"] for s in resp.json()}
        assert keys == {
            "alerts_only_price_stars", "all_in_one_price_stars",
            "alerts_subscription_extra_alerts", "all_in_one_monthly_boost_credit",
        }

        resp = client.put(
            "/ops/monetization/settings/alerts_only_price_stars", json={"value": "45"}
        )
        assert resp.status_code == 200
        assert get_setting(db_session, "alerts_only_price_stars") == 45

    def test_unknown_setting_rejected(self, db_session):
        client = _monetization_client(db_session)
        assert client.put(
            "/ops/monetization/settings/not_a_key", json={"value": "1"}
        ).status_code == 404


class TestRevenue:
    def test_revenue_counts_and_expiring(self, db_session, monkeypatch):
        user, channel, item = _seller(db_session)
        now = datetime.now(timezone.utc)
        _active_boost(db_session, item, user, charge_id="chg_rev_1")
        # expiring: ends within 24h (ends_at in ~1h, still active)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_rev_2",
            starts_at=now - timedelta(days=6), ends_at=now + timedelta(hours=1),
            created_at=now - timedelta(days=6),
        ))
        db_session.add(Subscription(
            user_id=user.id, product="all_in_one", status="active",
            telegram_payment_charge_id="chg_rev_sub",
            invoice_payload=f"s:{user.id}:all_in_one:abc",
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=29),
        ))
        db_session.commit()

        fake = FakeStarPaymentsAdapter()
        fake.ledger = [
            {"id": "chg_rev_tx1", "amount": 150, "date": int(now.timestamp()),
             "source": {"transaction_type": "invoice_payment"}},
            {"id": "chg_rev_tx2", "amount": 100, "date": int(now.timestamp()),
             "source": {"transaction_type": "invoice_payment"}},
            {"id": "chg_rev_tx3", "amount": 30, "date": int(now.timestamp()),
             "source": {"transaction_type": "invoice_send"}},
        ]
        from api.routes import ops_monetization as m
        monkeypatch.setattr("api.routes.ops_monetization.star_payments", fake)

        client = _monetization_client(db_session)
        resp = client.get("/ops/monetization/revenue")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stars_earned_last_30d"] == 250  # only invoice_payment txs
        assert data["active_subscriptions"] == 1
        assert data["active_boosts"] == 2
        assert len(data["expiring_soon"]) == 1
        assert data["expiring_soon"][0]["item_id"] == item.id
        assert data["expiring_soon"][0]["title"] == "iPhone"


class TestRevenueWithRealAdapter:
    """Regression: /ops/monetization/revenue sums int(tx['amount']) — the
    REAL httpx adapter must unwrap Telegram's {"transactions": [...]} result
    and normalize dict amounts, or this endpoint 500s (int({...}) TypeError)."""

    def test_revenue_with_telegram_shaped_transactions(self, db_session, monkeypatch):
        from services.telegram_payments import HttpxStarPaymentsAdapter

        adapter = HttpxStarPaymentsAdapter(bot_token="test")

        async def _fake_get(method, params=None):
            return {
                "transactions": [
                    {"id": "chg_rev_tx1", "date": 1750000000,
                     "amount": {"amount": 150, "nanostar_amount": 0},
                     "source": {"transaction_type": "invoice_payment"}},
                    {"id": "chg_rev_tx2", "date": 1750000001,
                     "amount": {"amount": 100, "nanostar_amount": 0},
                     "source": {"transaction_type": "invoice_payment"}},
                    {"id": "chg_rev_tx3", "date": 1750000002, "amount": 30,
                     "source": {"transaction_type": "invoice_send"}},
                ],
                "transactions_count": 3,
            }

        monkeypatch.setattr(adapter, "_get", _fake_get)
        monkeypatch.setattr("api.routes.ops_monetization.star_payments", adapter)
        client = _monetization_client(db_session)
        resp = client.get("/ops/monetization/revenue")
        assert resp.status_code == 200, resp.text
        assert resp.json()["stars_earned_last_30d"] == 250


class TestBoostModeration:
    def test_boosts_list_joins_item_and_channel(self, db_session):
        user, channel, item = _seller(db_session)
        boost = _active_boost(db_session, item, user, charge_id="chg_mod_1")
        client = _monetization_client(db_session)
        resp = client.get("/ops/monetization/boosts")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == boost.id
        assert rows[0]["item_id"] == item.id
        assert rows[0]["title"] == "iPhone"
        assert rows[0]["channel_username"] == "ch_m"
        assert rows[0]["source"] == "paid"
        assert rows[0]["price_paid_stars"] == 150

    def test_end_boost_early_ends_and_audits(self, db_session):
        from services.boost import get_pinned_boosted_items

        user, channel, item = _seller(db_session)
        boost = _active_boost(db_session, item, user, charge_id="chg_mod_2")
        assert len(get_pinned_boosted_items(db_session)) == 1

        client = _monetization_client(db_session)
        resp = client.post(f"/ops/monetization/boosts/{boost.id}/end")
        assert resp.status_code == 200, resp.text

        db_session.refresh(boost)
        assert boost.ends_at <= datetime.now(timezone.utc) + timedelta(seconds=5)
        # the item leaves the pinned block
        assert get_pinned_boosted_items(db_session) == []
        # audit row
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "end_boost_early")
        )
        assert audit is not None
        assert audit.entity_id == str(boost.id)
        assert "ends_at" in audit.before and "ends_at" in audit.after

    def test_end_boost_early_on_inactive_409(self, db_session):
        user, channel, item = _seller(db_session)
        now = datetime.now(timezone.utc)
        boost = Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150, telegram_payment_charge_id="chg_mod_3",
            starts_at=now - timedelta(days=10), ends_at=now - timedelta(days=3),
        )
        db_session.add(boost)
        db_session.commit()
        db_session.refresh(boost)
        client = _monetization_client(db_session)
        assert client.post(f"/ops/monetization/boosts/{boost.id}/end").status_code == 409


class TestInflightPriceStability:
    def test_inflight_invoice_price_unchanged_by_db_edit(self, db_session, monkeypatch):
        """Rule 4.1.5: quote P → change DB price to P' → fulfill the old
        invoice → price_paid_stars == P."""
        import asyncio

        from services.boost import create_boost_order, fulfill_boost

        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.boost.star_payments", fake)

        user, channel, item = _seller(db_session)
        order = asyncio.run(create_boost_order(db_session, user, item))
        quoted_p = order["price_stars"]

        # change the DB price AFTER the quote
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="Android Phones",
            price_stars=quoted_p * 2, updated_by="admin",
        )

        boost = fulfill_boost(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_inflight",
            invoice_payload=order["payload"],
            total_amount=quoted_p,
        )
        assert boost.price_paid_stars == quoted_p


class TestKillSwitchRegression:
    """D11: the four stale monkeypatch sites migrate to registry control;
    the 503 assertions themselves stay identical."""

    def _items_client(self, db_session):
        from api.routes import items as items_router
        app = FastAPI()
        app.include_router(items_router.router, prefix="/items")
        def _override_db():
            yield db_session
        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def _payments_client(self, db_session):
        from api.routes import payments as payments_router
        app = FastAPI()
        app.include_router(payments_router.router)
        def _override_db():
            yield db_session
        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def _subscriptions_client(self, db_session):
        from api.routes import subscriptions as subscriptions_router
        app = FastAPI()
        app.include_router(subscriptions_router.router, prefix="/subscriptions")
        def _override_db():
            yield db_session
        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def test_registry_row_false_503s_quote_order_credit(self, db_session):
        from services.settings_registry import set_setting
        set_setting(db_session, "monetization_enabled", "false")
        _, _, item = _seller(db_session)
        client = self._items_client(db_session)
        init_data = f'user={json.dumps({"id": 111, "username": "u111"})}'
        q = client.get(f"/items/{item.id}/boost-quote", params={"init_data": init_data})
        o = client.post(f"/items/{item.id}/boost-order", params={"init_data": init_data})
        c = client.post(f"/items/{item.id}/boost-credit", params={"init_data": init_data})
        assert q.status_code == o.status_code == c.status_code == 503

    def test_registry_row_false_503s_fulfill(self, db_session):
        from services.settings_registry import set_setting
        set_setting(db_session, "monetization_enabled", "false")
        client = self._payments_client(db_session)
        resp = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json={"telegram_payment_charge_id": "chg_z", "invoice_payload": "b:1:abc", "total_amount": 150},
        )
        assert resp.status_code == 503

    def test_registry_row_false_503s_subscription_order(self, db_session):
        from services.settings_registry import set_setting
        set_setting(db_session, "monetization_enabled", "false")
        client = self._subscriptions_client(db_session)
        resp = client.post(
            "/subscriptions/order",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json={"product": "alerts_only"},
        )
        assert resp.status_code == 503

    def test_registry_row_false_503s_channels_boosts(self, db_session):
        from services.settings_registry import set_setting
        set_setting(db_session, "monetization_enabled", "false")
        user, channel, item = _seller(db_session)
        _active_boost(db_session, item, user)
        client = self._items_client(db_session)
        from api.routes import channels as channels_router
        app = FastAPI()
        app.include_router(channels_router.router, prefix="/channels")
        def _override_db():
            yield db_session
        app.dependency_overrides[get_db] = _override_db
        resp = TestClient(app).get(
            f"/channels/{channel.id}/boosts",
            params={"init_data": f'user={json.dumps({"id": 111, "username": "u111"})}'},
        )
        assert resp.status_code == 503

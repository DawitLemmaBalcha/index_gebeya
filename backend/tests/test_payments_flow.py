"""
Full-loop tests for the Stars payments seam (TECH-27, blueprint §2.5/§5.2).

Route-level tests run against a minimal FastAPI TestClient app that includes
only the router under test, with get_db overridden to the isolated test
session — same dependency-override seam the services use. Telegram is the
FakeStarPaymentsAdapter; no network.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import get_db
from models import User, Channel, Item, Subscription
from services.boost import create_boost_order, get_boost_status, get_pinned_boosted_items
from tests.fake_telegram_payments import FakeStarPaymentsAdapter


def _make_seller_item(db, *, telegram_id=111, category="Mobile Phones",
                      title="iPhone 13", price=100.0, image_vector=None):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(
        username=f"ch_{telegram_id}", title="Test Channel",
        registered_by=telegram_id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id,
        title=title,
        category=category,
        price=price,
        status="active",
        is_active=True,
        image_path="test.jpg",
        image_vector=image_vector,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


def _init_data(telegram_id: int) -> str:
    return f'user={json.dumps({"id": telegram_id, "username": f"u{telegram_id}"})}'


def _payments_client(db_session):
    from api.routes import payments as payments_router
    app = FastAPI()
    app.include_router(payments_router.router)

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def _items_client(db_session):
    from api.routes import items as items_router
    app = FastAPI()
    app.include_router(items_router.router, prefix="/items", tags=["Items"])

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Internal fulfillment endpoints (blueprint §2.5)
# ---------------------------------------------------------------------------

class TestInternalFulfillBoost:
    @pytest.mark.asyncio
    async def test_full_loop_order_then_fulfill_then_pinned(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.boost.star_payments", fake)
        _, _, item = _make_seller_item(db_session)
        user = db_session.scalar(select(User).where(User.telegram_id == 111))
        order = await create_boost_order(db_session, user, item)
        assert len(fake.calls) == 1

        client = _payments_client(db_session)
        body = {
            "telegram_payment_charge_id": "chg_flow_1",
            "invoice_payload": order["payload"],
            "total_amount": order["price_stars"],
        }
        resp = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json=body,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok"
        boost_id = resp.json()["boost_id"]

        status = get_boost_status(db_session, item.id)
        assert status is not None and status["active"] is True
        pinned = get_pinned_boosted_items(db_session, category="Mobile Phones")
        assert item.id in {i.id for i in pinned}

        # Replay (lost-update recovery) is a no-op returning the same boost.
        resp2 = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json=body,
        )
        assert resp2.status_code == 200
        assert resp2.json()["boost_id"] == boost_id

    def test_fulfill_missing_charge_id_400(self, db_session):
        client = _payments_client(db_session)
        resp = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json={"telegram_payment_charge_id": "", "invoice_payload": "b:1:abc", "total_amount": 150},
        )
        assert resp.status_code == 400, resp.text

    def test_fulfill_requires_internal_service_header(self, db_session):
        client = _payments_client(db_session)
        resp = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            json={"telegram_payment_charge_id": "chg_x", "invoice_payload": "b:1:abc", "total_amount": 150},
        )
        assert resp.status_code == 403, resp.text

    def test_fulfill_malformed_payload_400(self, db_session):
        client = _payments_client(db_session)
        resp = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json={"telegram_payment_charge_id": "chg_y", "invoice_payload": "garbage", "total_amount": 150},
        )
        assert resp.status_code == 400, resp.text

    def test_fulfill_kill_switch_503(self, db_session, monkeypatch):
        monkeypatch.setattr("api.routes.payments.MONETIZATION_ENABLED", 0)
        client = _payments_client(db_session)
        resp = client.post(
            "/internal/payments/fulfill-boost",
            params={"init_data": "111"},
            headers={"X-Internal-Service": "index-listener"},
            json={"telegram_payment_charge_id": "chg_z", "invoice_payload": "b:1:abc", "total_amount": 150},
        )
        assert resp.status_code == 503, resp.text


# ---------------------------------------------------------------------------
# Buyer-facing boost endpoints (blueprint §2.5)
# ---------------------------------------------------------------------------

class TestBoostRoutes:
    def test_quote_returns_price_and_active_boost(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.boost.star_payments", fake)
        _, _, item = _make_seller_item(db_session)
        client = _items_client(db_session)

        resp = client.get(
            f"/items/{item.id}/boost-quote",
            params={"init_data": _init_data(111)},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["price_stars"] == 150
        assert data["duration_days"] == 7
        assert data["category"] == "Mobile Phones"
        assert data["active_boost"] is None

    def test_quote_foreign_owner_403(self, db_session):
        _, _, item = _make_seller_item(db_session, telegram_id=111)
        client = _items_client(db_session)
        resp = client.get(
            f"/items/{item.id}/boost-quote",
            params={"init_data": _init_data(222)},  # not the channel owner
        )
        assert resp.status_code == 403, resp.text

    def test_quote_missing_item_404(self, db_session):
        client = _items_client(db_session)
        resp = client.get(
            "/items/99999/boost-quote",
            params={"init_data": _init_data(111)},
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_order_route_creates_invoice(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.boost.star_payments", fake)
        _, _, item = _make_seller_item(db_session)
        client = _items_client(db_session)

        resp = client.post(
            f"/items/{item.id}/boost-order",
            params={"init_data": _init_data(111)},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["invoice_url"].startswith("https://t.me/fake-invoice/")
        assert data["payload"].startswith("b:")
        assert data["price_stars"] == 150
        assert data["duration_days"] == 7
        assert fake.calls[0]["prices"] == [("Boost", 150)]

    def test_credit_route_returns_boost(self, db_session):
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Subscription(
            user_id=user.id, product="all_in_one", status="active",
            telegram_payment_charge_id="chg_sub_flow",
            invoice_payload=f"s:{user.id}:all_in_one:abc",
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=29),
            is_recurring=True,
        ))
        db_session.commit()
        client = _items_client(db_session)

        resp = client.post(
            f"/items/{item.id}/boost-credit",
            params={"init_data": _init_data(111)},
        )
        assert resp.status_code == 200, resp.text
        boost = resp.json()["boost"]
        assert boost["source"] == "credit"
        assert boost["id"] > 0
        assert boost["ends_at"] is not None

    def test_boost_routes_kill_switch_503(self, db_session, monkeypatch):
        monkeypatch.setattr("api.routes.items.MONETIZATION_ENABLED", 0)
        _, _, item = _make_seller_item(db_session)
        client = _items_client(db_session)

        q = client.get(f"/items/{item.id}/boost-quote", params={"init_data": _init_data(111)})
        o = client.post(f"/items/{item.id}/boost-order", params={"init_data": _init_data(111)})
        c = client.post(f"/items/{item.id}/boost-credit", params={"init_data": _init_data(111)})
        assert q.status_code == o.status_code == c.status_code == 503


# ---------------------------------------------------------------------------
# Search pin layer (blueprint D7/D8, Rules 3.3/3.4)
# ---------------------------------------------------------------------------

class TestSearchPinLayer:
    def test_search_pins_boosted_item_and_excludes_from_organic(self, db_session, monkeypatch):
        from api.routes import search as search_route
        from models import Boost
        from schemas import ItemResponse

        user, _, boosted_item = _make_seller_item(db_session, telegram_id=111, title="Pinned Phone")
        _, _, organic_item = _make_seller_item(db_session, telegram_id=112, title="Organic Phone")
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=boosted_item.id, channel_id=boosted_item.channel_id,
            user_id=user.id, source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_pin_1",
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=6),
        ))
        db_session.commit()

        captured = {}

        def fake_hybrid_search(db, query_text, limit=None, offset=0, threshold=0.2,
                               min_price=None, max_price=None, category=None,
                               exclude_unpriced=False, exclude_item_ids=None):
            captured["exclude_item_ids"] = exclude_item_ids
            return [ItemResponse.model_validate(organic_item)], 1

        monkeypatch.setattr(search_route.search_service, "perform_hybrid_search", fake_hybrid_search)

        app = FastAPI()
        app.include_router(search_route.router, prefix="/search", tags=["Search"])

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        client = TestClient(app)

        resp = client.post("/search/", json={"query": "", "category": "Mobile Phones", "limit": 10})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        items = data["items"]

        # Pinned item first, flagged, and NOT duplicated in the organic slice.
        assert items[0]["id"] == boosted_item.id
        assert items[0]["is_boosted"] is True
        assert items[1]["id"] == organic_item.id
        assert items[1]["is_boosted"] is False
        assert [i["id"] for i in items].count(boosted_item.id) == 1
        assert data["total"] == 1  # organic count stays organic
        assert captured["exclude_item_ids"] == [boosted_item.id]

    def test_exclude_item_ids_threaded_into_sql(self, db_session):
        from services.search import perform_hybrid_search
        vec = [0.1] * 512
        _, _, item_a = _make_seller_item(db_session, telegram_id=111, title="Alpha", image_vector=vec)
        _, _, item_b = _make_seller_item(db_session, telegram_id=112, title="Beta", image_vector=vec)

        all_items, _ = perform_hybrid_search(db_session, "alpha", limit=10)
        assert {i.id for i in all_items} >= {item_a.id, item_b.id}

        excluded, _ = perform_hybrid_search(db_session, "alpha", limit=10, exclude_item_ids=[item_a.id])
        assert item_a.id not in {i.id for i in excluded}
        assert item_b.id in {i.id for i in excluded}

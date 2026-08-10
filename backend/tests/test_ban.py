"""
NB-56: the ban primitive — one flag, enforced at the seams (Rule 3.1..3.5).

Six call sites: alert creation (service level), review submission, sold-
report submission, ingestion (channel-level), and the item queries — search
raw SQL, catalog browse, all five recommendation sub-queries, and the
pinned-boost layer. Plus: unban restores everything instantly, ownerless
channels stay visible (Rule 1.4), and the /ops/users/{telegram_id}
status|ban|unban endpoints with audit rows.
"""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import quote

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from models import (
    Alert,
    AuditLog,
    Boost,
    Channel,
    Item,
    Review,
    SoldReport,
    User,
    UserInteraction,
)

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_init_data(telegram_id, username="tester"):
    return f"user={quote(json.dumps({'id': telegram_id, 'username': username}))}"


def _make_crypto_init_data(telegram_id, username="tester"):
    """Cryptographically valid initData for the configured bot token."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    user_data = {"id": telegram_id, "username": username, "first_name": "T"}
    data = {
        "query_id": "q123",
        "user": json.dumps(user_data),
        "auth_date": "1700000000",
        "chat_instance": "ci1",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return "&".join(f"{k}={quote(v)}" for k, v in data.items())


def _user(db, telegram_id=111, banned=False, username=None):
    user = User(
        telegram_id=telegram_id,
        username=username or f"u{telegram_id}",
        banned=banned,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _channel(db, username, owner_tg=None):
    channel = Channel(username=username, title=username, registered_by=owner_tg)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _item(db, channel, *, title="iPhone 13", price=100.0, category="Mobile Phones", description=None):
    item = Item(
        channel_id=channel.id,
        title=title,
        description=description,
        price=price,
        category=category,
        subcategory="General",
        status="active",
        is_active=True,
        image_path="x.jpg",
        specs="{}",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _reviews_client(db_session):
    from api.routes import reviews as reviews_route

    app = FastAPI()
    app.include_router(reviews_route.router, prefix="/reviews")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def _items_client(db_session):
    from api.routes import items as items_route

    app = FastAPI()
    app.include_router(items_route.router, prefix="/items")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def _ops_client(db_session):
    from api.routes import ops_auth, ops_finalize

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_finalize.router, prefix="/ops")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    resp = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert resp.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Seam 1: alert creation (service level)
# ---------------------------------------------------------------------------
class TestAlertSeam:
    def test_create_alert_403_for_banned_and_ok_after_unban(self, db_session):
        from services.alerting import create_alert

        user = _user(db_session, telegram_id=111, banned=True)
        with pytest.raises(HTTPException) as exc:
            create_alert(db_session, user, "iphone", None, {})
        assert exc.value.status_code == 403
        assert "banned" in exc.value.detail.lower()

        user.banned = False
        db_session.commit()
        alert = create_alert(db_session, user, "iphone", None, {})
        assert alert.id is not None
        assert alert.user_id == user.id


# ---------------------------------------------------------------------------
# Seam 2: review submission
# ---------------------------------------------------------------------------
class TestReviewSeam:
    def test_review_submission_403_for_banned_user(self, db_session):
        _user(db_session, telegram_id=222, banned=True)
        channel = _channel(db_session, "ch_rev_banned")
        client = _reviews_client(db_session)

        resp = client.post(
            "/reviews/",
            json={
                "channel_id": channel.id,
                "rating": 5,
                "comment": "nice",
                "init_data": _make_crypto_init_data(222),
            },
        )
        assert resp.status_code == 403
        assert db_session.scalar(select(Review.id)) is None

    def test_review_submission_succeeds_for_clean_user(self, db_session):
        _user(db_session, telegram_id=223, banned=False)
        channel = _channel(db_session, "ch_rev_clean")
        client = _reviews_client(db_session)

        resp = client.post(
            "/reviews/",
            json={
                "channel_id": channel.id,
                "rating": 5,
                "comment": "nice",
                "init_data": _make_crypto_init_data(223),
            },
        )
        assert resp.status_code == 200, resp.text
        assert db_session.scalar(select(Review.id)) is not None


# ---------------------------------------------------------------------------
# Seam 3: sold-report submission
# ---------------------------------------------------------------------------
class TestSoldReportSeam:
    def test_report_item_as_sold_403_for_banned(self, db_session):
        _user(db_session, telegram_id=333, banned=True)
        channel = _channel(db_session, "ch_sold_banned")  # ownerless: no owner DM
        item = _item(db_session, channel)
        client = _items_client(db_session)

        resp = client.post(
            f"/items/{item.id}/report",
            json={"init_data": _make_init_data(333)},
        )
        assert resp.status_code == 403
        assert db_session.scalar(select(SoldReport.id)) is None

    def test_report_item_as_sold_succeeds_for_clean_user(self, db_session):
        _user(db_session, telegram_id=335, banned=False)
        channel = _channel(db_session, "ch_sold_clean")
        item = _item(db_session, channel)
        client = _items_client(db_session)

        resp = client.post(
            f"/items/{item.id}/report",
            json={"init_data": _make_init_data(335)},
        )
        assert resp.status_code == 200, resp.text
        assert db_session.scalar(select(SoldReport.id)) is not None


# ---------------------------------------------------------------------------
# Seam 4: ingestion (channel-level)
# ---------------------------------------------------------------------------
class TestIngestionSeam:
    def _ingest(self, db_session, channel_name):
        from api.routes import ingestion as ingestion_route

        class _FakeTelegramResponse:
            status_code = 404

        class _FakeTelegramClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                return _FakeTelegramResponse()

        body = {
            "channel_name": channel_name,
            "message_id": 999123,
            "text": "iPhone 13 for sale",
        }
        extraction_data = {
            "title": "iPhone 13",
            "price": 100,
            "currency": "ETB",
            "category": "Mobile Phones",
            "subcategory": "Smartphones",
            "item_metadata": {"storage": "128GB"},
        }

        with patch.object(ingestion_route, "extract_product_info",
                          return_value=extraction_data), \
             patch.object(ingestion_route, "process_new_item",
                          return_value=None), \
             patch.object(ingestion_route.httpx, "AsyncClient",
                          _FakeTelegramClient):
            app = FastAPI()
            app.include_router(ingestion_route.router)

            def _override_db():
                yield db_session

            app.dependency_overrides[get_db] = _override_db
            return TestClient(app).post("/parse-telegram-post", json=body)

    def test_ingestion_403_for_banned_owner_channel(self, db_session):
        _user(db_session, telegram_id=555, banned=True)
        _channel(db_session, "ch_ing_banned", owner_tg=555)
        resp = self._ingest(db_session, "ch_ing_banned")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Channel owner banned"
        assert db_session.scalar(select(Item.id)) is None

    def test_ingestion_ok_for_ownerless_channel(self, db_session):
        _channel(db_session, "ch_ing_ownerless", owner_tg=None)
        resp = self._ingest(db_session, "ch_ing_ownerless")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_ingestion_ok_for_clean_owner_channel(self, db_session):
        _user(db_session, telegram_id=556, banned=False)
        _channel(db_session, "ch_ing_clean", owner_tg=556)
        resp = self._ingest(db_session, "ch_ing_clean")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Seam 5: item queries — search, browse, feeds, pinned layer
# ---------------------------------------------------------------------------
class TestItemQuerySeams:
    def test_banned_sellers_items_absent_from_browse(self, db_session):
        banned_owner = _user(db_session, telegram_id=777, banned=True)
        ch_banned = _channel(db_session, "ch_browse_banned", owner_tg=777)
        banned_item = _item(db_session, ch_banned, title="Banned Browse Item")
        ch_clean = _channel(db_session, "ch_browse_clean", owner_tg=None)
        clean_item = _item(db_session, ch_clean, title="Clean Browse Item")

        from services.catalog import browse_category

        items, total = browse_category(db_session, "Mobile Phones", limit=50)
        ids = [i.id for i in items]
        assert banned_item.id not in ids
        assert clean_item.id in ids
        assert total == 1

    def test_banned_sellers_items_absent_from_search(self, db_session):
        banned_owner = _user(db_session, telegram_id=778, banned=True)
        ch_banned = _channel(db_session, "ch_search_banned", owner_tg=778)
        banned_item = _item(
            db_session, ch_banned,
            title="Unique Widget Alpha",
            # description required: the search loose filter runs
            # similarity() over title||description without coalesce.
            description="Alpha version of the unique widget",
        )
        ch_clean = _channel(db_session, "ch_search_clean", owner_tg=None)
        clean_item = _item(
            db_session, ch_clean,
            title="Unique Widget Beta",
            description="Beta version of the unique widget",
        )

        from services.search import perform_hybrid_search

        results, _ = perform_hybrid_search(db_session, "Unique Widget", limit=20)
        ids = [r.id for r in results]
        assert banned_item.id not in ids
        assert clean_item.id in ids

    def _seed_feed_env(self, db_session, owner_tg=880):
        """banned-seller item + ownerless clean item + a third ownerless
        extra item (so the session-feed query has a result)."""
        banned_owner = _user(db_session, telegram_id=owner_tg, banned=True)
        ch_banned = _channel(db_session, "ch_feed_banned", owner_tg=owner_tg)
        banned_item = _item(db_session, ch_banned, title="Banned Feed Item")
        ch_clean = _channel(db_session, "ch_feed_clean", owner_tg=None)
        clean_item = _item(db_session, ch_clean, title="Clean Feed Item")
        ch_extra = _channel(db_session, "ch_feed_extra", owner_tg=None)
        extra_item = _item(db_session, ch_extra, title="Extra Feed Item")
        return banned_item, clean_item, extra_item

    def test_recent_items_excludes_banned(self, db_session):
        banned_item, clean_item, extra_item = self._seed_feed_env(db_session)

        from services.recommendation import get_recent_items

        ids = [i.id for i in get_recent_items(db_session, limit=10)]
        assert banned_item.id not in ids
        assert clean_item.id in ids
        assert extra_item.id in ids

    def test_trending_items_excludes_banned(self, db_session):
        banned_item, clean_item, extra_item = self._seed_feed_env(db_session)
        buyer = _user(db_session, telegram_id=881, banned=False)
        db_session.add(UserInteraction(
            user_id=buyer.id, item_id=clean_item.id, interaction_type="view_item"
        ))
        db_session.commit()

        from services.recommendation import get_trending_items

        ids = [i.id for i in get_trending_items(db_session, limit=10)]
        assert banned_item.id not in ids

    def test_session_feed_excludes_banned(self, db_session):
        banned_item, clean_item, extra_item = self._seed_feed_env(db_session)
        buyer = _user(db_session, telegram_id=882, banned=False)
        db_session.add(UserInteraction(
            user_id=buyer.id, item_id=clean_item.id, interaction_type="view_item"
        ))
        db_session.commit()

        from services.recommendation import get_session_feed

        interactions = db_session.scalars(select(UserInteraction)).all()
        ids = [i.id for i in get_session_feed(db_session, interactions, limit=10)]
        assert banned_item.id not in ids
        assert extra_item.id in ids

    def test_discovery_feed_excludes_banned(self, db_session):
        banned_item, clean_item, extra_item = self._seed_feed_env(db_session)
        buyer = _user(db_session, telegram_id=883, banned=False)
        db_session.add(UserInteraction(
            user_id=buyer.id, item_id=clean_item.id, interaction_type="view_item"
        ))
        db_session.commit()

        from services.recommendation import get_discovery_feed

        interactions = db_session.scalars(select(UserInteraction)).all()
        ids = [i.id for i in get_discovery_feed(db_session, interactions, total_limit=10)]
        assert banned_item.id not in ids
        assert extra_item.id in ids

    def test_wildcard_feed_excludes_banned(self, db_session):
        # Four categories of history — the 4th (second-tier) category holds
        # the banned-seller item alongside a clean item.
        banned_owner = _user(db_session, telegram_id=884, banned=True)
        ch_banned = _channel(db_session, "ch_wild_banned", owner_tg=884)
        banned_item = _item(db_session, ch_banned, title="Banned Wild Item", category="D")
        ch_d = _channel(db_session, "ch_wild_d", owner_tg=None)
        clean_d = _item(db_session, ch_d, title="Clean Wild D Item", category="D")
        buyer = _user(db_session, telegram_id=885, banned=False)
        for cat, title in [("A", "Hist A"), ("B", "Hist B"), ("C", "Hist C"), ("D", "Hist D")]:
            ch = _channel(db_session, f"ch_wild_hist_{cat}", owner_tg=None)
            item = _item(db_session, ch, title=title, category=cat)
            db_session.add(UserInteraction(
                user_id=buyer.id, item_id=item.id, interaction_type="view_item"
            ))
        db_session.commit()

        from services.recommendation import get_wildcard_feed

        interactions = db_session.scalars(select(UserInteraction)).all()
        ids = [i.id for i in get_wildcard_feed(db_session, interactions, limit=10)]
        assert banned_item.id not in ids
        assert clean_d.id in ids

    def test_pinned_boost_layer_excludes_banned_seller_items(self, db_session):
        banned_owner = _user(db_session, telegram_id=900, banned=True)
        ch_banned = _channel(db_session, "ch_pin_banned", owner_tg=900)
        banned_item = _item(db_session, ch_banned)
        clean_owner = _user(db_session, telegram_id=901, banned=False)
        ch_clean = _channel(db_session, "ch_pin_clean", owner_tg=901)
        clean_item = _item(db_session, ch_clean)

        now = datetime.now(timezone.utc)
        for item, channel, owner in [
            (banned_item, ch_banned, banned_owner),
            (clean_item, ch_clean, clean_owner),
        ]:
            db_session.add(Boost(
                item_id=item.id,
                channel_id=channel.id,
                user_id=owner.id,
                source="paid",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
            ))
        db_session.commit()

        from services.boost import get_pinned_boosted_items

        pinned = get_pinned_boosted_items(db_session, category="Mobile Phones", now=now)
        ids = [i.id for i in pinned]
        assert banned_item.id not in ids
        assert clean_item.id in ids


# ---------------------------------------------------------------------------
# Unban restores everything; ownerless channels stay visible
# ---------------------------------------------------------------------------
class TestUnbanRestores:
    def test_unban_restores_items_in_browse_and_search(self, db_session):
        owner = _user(db_session, telegram_id=950, banned=True)
        ch = _channel(db_session, "ch_unban", owner_tg=950)
        item = _item(db_session, ch, title="Unban Me Widget")

        from services.catalog import browse_category

        items, total = browse_category(db_session, "Mobile Phones")
        assert item.id not in [i.id for i in items]

        owner.banned = False
        db_session.commit()
        items, total = browse_category(db_session, "Mobile Phones")
        assert item.id in [i.id for i in items]

    def test_ownerless_channel_items_remain_visible(self, db_session):
        ch = _channel(db_session, "ch_ownerless", owner_tg=None)
        item = _item(db_session, ch, title="Ownerless Item")

        from services.catalog import browse_category

        items, total = browse_category(db_session, "Mobile Phones")
        assert item.id in [i.id for i in items]


# ---------------------------------------------------------------------------
# Ops endpoints: status / ban / unban + audit
# ---------------------------------------------------------------------------
class TestOpsUserEndpoints:
    def test_status_ban_unban_endpoints_and_audit(self, db_session):
        _user(db_session, telegram_id=1010, username="banned_candidate")
        client = _ops_client(db_session)

        status = client.get("/ops/users/1010/status")
        assert status.status_code == 200, status.text
        data = status.json()
        assert data["telegram_id"] == 1010
        assert data["username"] == "banned_candidate"
        assert data["banned"] is False
        assert set(data["footprint"].keys()) == {
            "reviews", "alerts_active", "alerts_total",
            "subscriptions_active", "boosts", "sold_reports",
        }

        resp = client.post("/ops/users/1010/ban")
        assert resp.status_code == 200
        assert resp.json()["banned"] is True
        user = db_session.scalar(select(User).where(User.telegram_id == 1010))
        assert user.banned is True
        audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "ban_user"))
        assert audit is not None
        assert audit.section == "users"
        assert audit.entity_type == "user"

        resp = client.post("/ops/users/1010/unban")
        assert resp.status_code == 200
        assert resp.json()["banned"] is False
        audit2 = db_session.scalar(select(AuditLog).where(AuditLog.action == "unban_user"))
        assert audit2 is not None

        status = client.get("/ops/users/1010/status")
        assert status.json()["banned"] is False

    def test_ban_unknown_user_404(self, db_session):
        client = _ops_client(db_session)
        resp = client.post("/ops/users/999999/ban")
        assert resp.status_code == 404

    def test_status_unknown_user_404(self, db_session):
        client = _ops_client(db_session)
        resp = client.get("/ops/users/999999/status")
        assert resp.status_code == 404

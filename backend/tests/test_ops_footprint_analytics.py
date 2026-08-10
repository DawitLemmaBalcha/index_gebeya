"""
NB-60: users & items analytics (blueprint §6, §5.6).

Footprint shape from a seeded user — ratings 1-5 distribution, alert /
subscription / boost counts, interaction counts + recent-50 truncation.
Analytics shapes from seeded items/interactions/reports — the 14-day
views series (aggregate + top-20 per-item), per-category price buckets,
and the per-active-channel aggregation.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from models import (
    Alert,
    Boost,
    Channel,
    Item,
    Review,
    SoldReport,
    Subscription,
    User,
    UserInteraction,
)

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")

NOW = datetime.now(timezone.utc)


def _user(db, telegram_id=111):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", banned=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _channel(db, username, is_active=True):
    channel = Channel(
        username=username, title=username, registered_by=None,
        trust_score=0.0, indexing_paused=False, is_active=is_active,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _item(db, channel, *, price, title, is_active=True):
    item = Item(
        channel_id=channel.id, title=title, price=price,
        category="Mobile Phones", subcategory="General",
        status="active" if is_active else "removed", is_active=is_active,
        image_path="x.jpg", specs="{}",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _review(db, user, channel, rating, created_at=None):
    review = Review(
        user_id=user.id, channel_id=channel.id, rating=rating,
        comment=f"rating {rating}", created_at=created_at or NOW,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def _interaction(db, user, *, item_id, type_, created_at=None, session_id="s"):
    row = UserInteraction(
        user_id=user.id if user else None, item_id=item_id,
        interaction_type=type_, session_id=session_id,
        created_at=created_at or NOW,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
# 6.1 The user footprint
# ---------------------------------------------------------------------------
class TestFootprint:
    def _seed(self, db_session):
        user = _user(db_session, telegram_id=707)
        # 6 reviews across 6 channels (unique user+channel): ratings 5,5,4,3,2,1
        channels = [_channel(db_session, f"ch_rev{i}") for i in range(6)]
        for i, rating in enumerate([5, 5, 4, 3, 2, 1]):
            _review(db_session, user, channels[i], rating,
                    created_at=NOW - timedelta(minutes=i))
        # alerts: 2 active + 1 inactive
        for _ in range(2):
            db_session.add(Alert(
                user_id=user.id, query_text="al", query_vector=[0.0] * 512,
                best_opportunity_score=0.0, is_active=True,
            ))
        db_session.add(Alert(
            user_id=user.id, query_text="al", query_vector=[0.0] * 512,
            best_opportunity_score=0.0, is_active=False,
        ))
        # subscription: one active row
        db_session.add(Subscription(
            user_id=user.id, product="all_in_one", status="active",
            invoice_payload="x",
        ))
        # boosts: 1 active (window open) + 1 expired
        item = _item(db_session, channels[0], price=100.0, title="boosted")
        db_session.add(Boost(
            item_id=item.id, channel_id=channels[0].id, user_id=user.id,
            source="paid", price_paid_stars=10, starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=6),
        ))
        db_session.add(Boost(
            item_id=item.id, channel_id=channels[0].id, user_id=user.id,
            source="paid", price_paid_stars=10, starts_at=NOW - timedelta(days=10),
            ends_at=NOW - timedelta(days=3),
        ))
        # interactions: 70 total → recent_50 must truncate to 50
        for i in range(70):
            _interaction(db_session, user, item_id=item.id,
                         type_="view_item" if i < 40 else "view_item_card",
                         created_at=NOW - timedelta(minutes=i))
        db_session.commit()
        return user

    def test_footprint_shape(self, db_session):
        user = self._seed(db_session)
        client = _ops_client(db_session)
        resp = client.get(f"/ops/users/{user.telegram_id}/footprint")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["user"] == {
            "telegram_id": user.telegram_id, "username": "u707", "banned": False,
        }

        reviews = body["reviews"]
        assert reviews["total"] == 6
        assert reviews["rating_distribution"] == {
            "1": 1, "2": 1, "3": 1, "4": 1, "5": 2,
        }
        assert len(reviews["recent"]) == 5
        first = reviews["recent"][0]
        assert set(first) == {
            "channel_id", "channel_username", "rating", "comment", "created_at",
        }
        assert first["rating"] == 5
        assert first["channel_username"].startswith("ch_rev")

        assert body["alerts"] == {"active": 2, "total": 3}
        assert body["subscriptions"] == {"active": 1, "product": "all_in_one"}
        assert body["boosts"] == {"total": 2, "active": 1}

        interactions = body["interactions"]
        assert interactions["counts_by_type"] == {
            "view_item": 40, "view_item_card": 30,
        }
        assert len(interactions["recent_50"]) == 50
        assert set(interactions["recent_50"][0]) == {
            "id", "item_id", "interaction_type", "created_at",
        }

    def test_404_unknown_user(self, db_session):
        client = _ops_client(db_session)
        resp = client.get("/ops/users/999999/footprint")
        assert resp.status_code == 404

    def test_empty_footprint(self, db_session):
        user = _user(db_session, telegram_id=808)
        client = _ops_client(db_session)
        resp = client.get(f"/ops/users/{user.telegram_id}/footprint")
        assert resp.status_code == 200
        body = resp.json()
        assert body["reviews"]["rating_distribution"] == {
            "1": 0, "2": 0, "3": 0, "4": 0, "5": 0,
        }
        assert body["alerts"] == {"active": 0, "total": 0}
        assert body["subscriptions"] == {"active": 0, "product": None}
        assert body["boosts"] == {"total": 0, "active": 0}
        assert body["interactions"]["counts_by_type"] == {}


# ---------------------------------------------------------------------------
# 6.2 The items analytics
# ---------------------------------------------------------------------------
class TestItemsAnalytics:
    def _seed(self, db_session):
        ch1 = _channel(db_session, "ch_an1")
        ch2 = _channel(db_session, "ch_an2")
        ch3 = _channel(db_session, "ch_an3", is_active=False)

        item_a = _item(db_session, ch1, price=500.0, title="A")      # 0-1k
        item_b = _item(db_session, ch1, price=3000.0, title="B")     # 1k-5k
        item_c = _item(db_session, ch2, price=15000.0, title="C")    # 5k-20k
        item_d = _item(db_session, ch2, price=60000.0, title="D")    # 20k-100k
        item_e = _item(db_session, ch2, price=200000.0, title="E")   # 100k+
        item_f = _item(db_session, ch3, price=1000.0, title="F", is_active=False)

        day2 = NOW - timedelta(days=2)
        day1 = NOW - timedelta(days=1)
        # views: A=5 (day2), B=3 (day1), C=2 (today), D=1 (today), F=7 (day2)
        for _ in range(5):
            _interaction(db_session, None, item_id=item_a.id, type_="view_item",
                         created_at=day2)
        for _ in range(3):
            _interaction(db_session, None, item_id=item_b.id, type_="view_item_card",
                         created_at=day1)
        for _ in range(2):
            _interaction(db_session, None, item_id=item_c.id, type_="view_item",
                         created_at=NOW)
        _interaction(db_session, None, item_id=item_d.id, type_="view_item",
                     created_at=NOW)
        for _ in range(7):
            _interaction(db_session, None, item_id=item_f.id, type_="view_item",
                         created_at=day2)

        # sold reports: 2 on A (ch1), 1 on C (ch2)
        rep1 = _user(db_session, telegram_id=801)
        rep2 = _user(db_session, telegram_id=802)
        db_session.add_all([
            SoldReport(user_id=rep1.id, item_id=item_a.id),
            SoldReport(user_id=rep2.id, item_id=item_a.id),
            SoldReport(user_id=rep1.id, item_id=item_c.id),
        ])
        db_session.commit()
        return {"ch1": ch1, "ch2": ch2, "ch3": ch3,
                "a": item_a, "b": item_b, "c": item_c, "d": item_d,
                "e": item_e, "f": item_f}

    def test_views_over_time_series(self, db_session):
        ids = self._seed(db_session)
        client = _ops_client(db_session)
        body = client.get("/ops/items/analytics").json()

        series = body["views_over_time"]
        assert len(series["days"]) == 14
        assert len(series["total"]) == 14
        # the aggregate counts EVERY view event in the window (5+3+2+1 = 11
        # on live items + F's 7 on the inactive channel's item = 18); the
        # per-item series surfaces LIVE inventory only.
        assert sum(series["total"]) == 18

        # top-20 by total views, each with a 14-length daily series
        top = series["top_items"]
        assert [t["item_id"] for t in top[:4]] == [
            ids["a"].id, ids["b"].id, ids["c"].id, ids["d"].id,
        ]
        assert all(len(t["daily"]) == 14 for t in top)
        # item A's 5 views landed on the day-2 bucket
        a_row = next(t for t in top if t["item_id"] == ids["a"].id)
        assert a_row["total"] == 5
        day_index = series["days"].index((NOW - timedelta(days=2)).date().isoformat())
        assert a_row["daily"][day_index] == 5

    def test_price_distribution_buckets(self, db_session):
        self._seed(db_session)
        client = _ops_client(db_session)
        body = client.get("/ops/items/analytics").json()

        dist = body["price_distribution"]
        assert len(dist) == 1  # one category: Mobile Phones
        cat = dist[0]
        assert cat["category"] == "Mobile Phones"
        # active priced items only: F (inactive, 1000) excluded
        assert cat["buckets"] == {
            "0-1000": 1,      # A (500)
            "1000-5000": 1,   # B (3000)
            "5000-20000": 1,  # C (15000)
            "20000-100000": 1,  # D (60000)
            "100000+": 1,     # E (200000)
        }

    def test_per_channel_aggregation(self, db_session):
        self._seed(db_session)
        client = _ops_client(db_session)
        body = client.get("/ops/items/analytics").json()

        per_channel = {pc["username"]: pc for pc in body["per_channel"]}
        assert set(per_channel) == {"ch_an1", "ch_an2"}  # ch_an3 inactive
        ch1 = per_channel["ch_an1"]
        assert ch1["items"] == 2
        assert ch1["views"] == 8   # A(5) + B(3)
        assert ch1["sold_reports"] == 2
        ch2 = per_channel["ch_an2"]
        assert ch2["items"] == 3
        assert ch2["views"] == 3   # C(2) + D(1)
        assert ch2["sold_reports"] == 1

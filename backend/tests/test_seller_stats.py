"""
Seller Intelligence dashboard tests (TECH-29, blueprint §2.4/§5.2).

Deviation from the blueprint's module list: the legacy TECH-16 `tests/test_stats.py`
hits the live API at localhost:8000 and is untouched; the new seller-intelligence
tests live here (same name would clobber legacy coverage).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import get_db
from models import User, Channel, Item, UserInteraction, Notification, Alert, Subscription
from services.stats import get_channel_dashboard


def _make_channel(db, *, telegram_id=111, username="ch_stats"):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username=username, title="Stats Channel", registered_by=telegram_id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return user, channel


def _make_item(db, channel, *, title="Item", category="Mobile Phones", price=100.0,
               created_at=None):
    item = Item(
        channel_id=channel.id, title=title, category=category, price=price,
        status="active", is_active=True, image_path="s.jpg",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _make_interaction(db, item, *, type="view_item", created_at=None, user=None):
    inter = UserInteraction(
        user_id=user.id if user else None,
        item_id=item.id,
        interaction_type=type,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(inter)
    db.commit()
    return inter


def _make_alert(db, user_id, *, is_active=True):
    alert = Alert(
        user_id=user_id,
        query_text="stats alert",
        query_vector=[0.01] * 512,
        preferences=json.dumps({}),
        is_active=is_active,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _make_notification(db, item, alert, *, tier="bullseye", status="SENT"):
    notif = Notification(
        user_id=alert.user_id, item_id=item.id, alert_id=alert.id,
        match_tier=tier, match_score=0.9, status=status,
        sent_at=datetime.now(timezone.utc) if status == "SENT" else None,
    )
    db.add(notif)
    db.commit()
    return notif


def _make_subscription(db, user, *, product="all_in_one"):
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id, product=product, status="active",
        telegram_payment_charge_id=f"chg_{product}_{user.id}",
        invoice_payload=f"s:{user.id}:{product}:abc",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
        is_recurring=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


class TestCoreStats:
    def test_views_counts_only_the_two_view_event_types(self, db_session):
        user, channel = _make_channel(db_session)
        item = _make_item(db_session, channel)
        _make_interaction(db_session, item, type="view_item")
        _make_interaction(db_session, item, type="view_item_card")
        _make_interaction(db_session, item, type="search")     # not a view
        _make_interaction(db_session, item, type="view")       # legacy default, not a view event (D9)

        dash = get_channel_dashboard(db_session, channel.id, user)
        core_item = dash["core"]["items"][0]
        assert core_item["views_total"] == 2

    def test_views_daily_sparkline_last_7_days(self, db_session):
        user, channel = _make_channel(db_session)
        item = _make_item(db_session, channel)
        now = datetime.now(timezone.utc)
        for day_offset in range(0, 7):
            _make_interaction(db_session, item, created_at=now - timedelta(days=day_offset))
        _make_interaction(db_session, item, created_at=now - timedelta(days=9))  # outside window

        dash = get_channel_dashboard(db_session, channel.id, user)
        sparkline = dash["core"]["items"][0]["views_daily"]
        assert len(sparkline) == 7
        assert sum(entry["count"] for entry in sparkline) == 7

    def test_dispatched_splits_sent_notifications_by_tier(self, db_session):
        user, channel = _make_channel(db_session)
        item = _make_item(db_session, channel)
        alert = _make_alert(db_session, user.id)
        _make_notification(db_session, item, alert, tier="bullseye")
        _make_notification(db_session, item, alert, tier="bullseye")
        _make_notification(db_session, item, alert, tier="ring")
        _make_notification(db_session, item, alert, tier="ring", status="PENDING")  # not sent

        dash = get_channel_dashboard(db_session, channel.id, user)
        assert dash["core"]["total_dispatched"] == {"bullseye": 2, "ring": 1}

    def test_alert_matches_distinct_alerts_per_item(self, db_session):
        user, channel = _make_channel(db_session)
        item_a = _make_item(db_session, channel, title="A")
        item_b = _make_item(db_session, channel, title="B")
        alert_1 = _make_alert(db_session, user.id)
        alert_2 = _make_alert(db_session, user.id)
        _make_notification(db_session, item_a, alert_1)
        _make_notification(db_session, item_a, alert_1)  # same alert twice -> 1 match
        _make_notification(db_session, item_a, alert_2)
        _make_notification(db_session, item_b, alert_1)

        dash = get_channel_dashboard(db_session, channel.id, user)
        by_id = {i["item_id"]: i for i in dash["core"]["items"]}
        assert by_id[item_a.id]["alert_matches"] == 2
        assert by_id[item_b.id]["alert_matches"] == 1

    def test_matching_buyers_counts_active_alerts_with_notifications(self, db_session):
        user, channel = _make_channel(db_session)
        item = _make_item(db_session, channel)
        _make_notification(db_session, item, _make_alert(db_session, user.id))
        _make_notification(db_session, item, _make_alert(db_session, user.id))
        _make_notification(db_session, item, _make_alert(db_session, user.id, is_active=False))
        _make_alert(db_session, user.id)  # active alert, zero notifications

        dash = get_channel_dashboard(db_session, channel.id, user)
        assert dash["core"]["matching_buyers"] == 2

    def test_core_ignores_other_channels(self, db_session):
        user, channel = _make_channel(db_session)
        _, other_channel = _make_channel(db_session, telegram_id=222, username="ch_other")
        item = _make_item(db_session, channel)
        other_item = _make_item(db_session, other_channel)
        _make_interaction(db_session, item)
        _make_interaction(db_session, other_item)
        alert = _make_alert(db_session, user.id)
        _make_notification(db_session, other_item, alert)

        dash = get_channel_dashboard(db_session, channel.id, user)
        assert [i["item_id"] for i in dash["core"]["items"]] == [item.id]
        assert dash["core"]["total_dispatched"] == {"bullseye": 0, "ring": 0}


class TestProGating:
    def test_pro_null_without_subscription(self, db_session):
        user, channel = _make_channel(db_session)
        _make_item(db_session, channel)
        dash = get_channel_dashboard(db_session, channel.id, user)
        assert dash["is_pro"] is False
        assert dash["pro"] is None

    def test_alerts_only_does_not_unlock_pro(self, db_session):
        user, channel = _make_channel(db_session)
        _make_item(db_session, channel)
        _make_subscription(db_session, user, product="alerts_only")
        dash = get_channel_dashboard(db_session, channel.id, user)
        assert dash["is_pro"] is False
        assert dash["pro"] is None

    def test_all_in_one_unlocks_pro(self, db_session):
        user, channel = _make_channel(db_session)
        _make_item(db_session, channel)
        _make_subscription(db_session, user, product="all_in_one")
        dash = get_channel_dashboard(db_session, channel.id, user)
        assert dash["is_pro"] is True
        assert dash["pro"] is not None


class TestProStats:
    def test_price_positioning_median_math(self, db_session):
        user, channel = _make_channel(db_session)
        mine = _make_item(db_session, channel, title="Mine", price=150.0)
        # Same-category median over ALL active priced items in the category
        # (blueprint §2.4: no self-exclusion): [100, 150, 200, 300] -> 175
        _, ch_b = _make_channel(db_session, telegram_id=222, username="ch_b")
        _, ch_c = _make_channel(db_session, telegram_id=333, username="ch_c")
        _make_item(db_session, ch_b, title="B1", price=100.0)
        _make_item(db_session, ch_b, title="B2", price=200.0)
        _make_item(db_session, ch_c, title="C1", price=300.0)
        _make_subscription(db_session, user, product="all_in_one")

        dash = get_channel_dashboard(db_session, channel.id, user)
        row = dash["pro"]["price_positioning"][0]
        assert row["item_id"] == mine.id
        assert row["median_price"] == 175.0
        assert abs(row["pct_diff"] - (-14.29)) < 0.01  # (150-175)/175

    def test_category_pulse_week_buckets(self, db_session):
        user, channel = _make_channel(db_session)
        _make_item(db_session, channel, category="Mobile Phones")
        now = datetime.now(timezone.utc)
        _make_item(db_session, channel, title="Old", category="Mobile Phones",
                   created_at=now - timedelta(days=10))
        _make_subscription(db_session, user, product="all_in_one")

        dash = get_channel_dashboard(db_session, channel.id, user)
        pulse = {p["category"]: p for p in dash["pro"]["category_pulse"]}
        row = pulse["Mobile Phones"]
        assert row["this_week"] == 1
        assert row["last_week"] == 1  # 10 days ago is in last week's bucket (7-14d)

    def test_top_performers_limited_to_5_by_views(self, db_session):
        user, channel = _make_channel(db_session)
        items = [_make_item(db_session, channel, title=f"Item {i}") for i in range(6)]
        for i, item in enumerate(items):
            for _ in range(i + 1):  # item i has i+1 views
                _make_interaction(db_session, item)
        _make_subscription(db_session, user, product="all_in_one")

        dash = get_channel_dashboard(db_session, channel.id, user)
        top = dash["pro"]["top_performers"]
        assert len(top) == 5
        assert top[0]["item_id"] == items[5].id  # most views first
        assert top[0]["views"] == 6


class TestStatsRoute:
    def _client(self, db_session):
        from api.routes import channels as channels_router
        app = FastAPI()
        app.include_router(channels_router.router, prefix="/channels", tags=["Channels"])

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def _init_data(self, telegram_id):
        return f'user={json.dumps({"id": telegram_id, "username": f"u{telegram_id}"})}'

    def test_owner_gets_dashboard(self, db_session):
        user, channel = _make_channel(db_session)
        item = _make_item(db_session, channel)
        _make_interaction(db_session, item)
        client = self._client(db_session)

        resp = client.get(
            f"/channels/{channel.id}/stats",
            params={"init_data": self._init_data(111)},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_pro"] is False
        assert data["core"]["items"][0]["views_total"] == 1
        assert data["pro"] is None

    def test_non_owner_gets_404(self, db_session):
        _, channel = _make_channel(db_session, telegram_id=111)
        client = self._client(db_session)

        resp = client.get(
            f"/channels/{channel.id}/stats",
            params={"init_data": self._init_data(222)},  # not the owner
        )
        assert resp.status_code == 404


class TestQueryBounding:
    """UAT performance guard: stats for a channel with N items must use a
    bounded number of queries (grouped aggregates), never N+1 per-item
    loops. Instrumented with an SQLAlchemy cursor-count listener."""

    def _count_queries(self, db_session, fn):
        from sqlalchemy import event
        count = {"n": 0}
        engine = db_session.get_bind()

        def _before(conn, cursor, statement, parameters, context, executemany):
            count["n"] += 1

        event.listen(engine, "before_cursor_execute", _before)
        try:
            fn()
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        return count["n"]

    def test_core_query_count_bounded_with_many_items(self, db_session):
        user, channel = _make_channel(db_session)
        for i in range(25):
            item = _make_item(db_session, channel, title=f"I{i}")
            _make_interaction(db_session, item)

        n = self._count_queries(
            db_session, lambda: get_channel_dashboard(db_session, channel.id, user)
        )
        # 25 items with per-item loops would need >= 25 queries for views
        # alone. Grouped aggregates keep the whole core block < 20.
        assert n < 20, f"core stats issued {n} queries for a 25-item channel"

    def test_pro_query_count_bounded_with_many_items(self, db_session):
        user, channel = _make_channel(db_session)
        for i in range(25):
            _make_item(db_session, channel, title=f"I{i}", category="Mobile Phones")
        _make_subscription(db_session, user, product="all_in_one")

        n = self._count_queries(
            db_session, lambda: get_channel_dashboard(db_session, channel.id, user)
        )
        # Medians/pulse are bounded by the number of distinct categories
        # (1 here), not by item count.
        assert n < 30, f"pro stats issued {n} queries for a 25-item channel"


class TestAnalyticsOverflow:
    """UAT fix: the x-user-id header carries the 64-bit TELEGRAM id, but
    user_interactions.user_id is the INTEGER users.id PK. If the telegram id
    is inserted raw it overflows INTEGER ("integer out of range" in the API
    logs) and the view is never logged — silently undercounting the views
    this dashboard displays."""

    def test_log_interaction_resolves_telegram_id_to_user_pk(self, db_session):
        from services.analytics import AnalyticsService
        big_tg_id = 8010115796  # > 2^31 — overflows the INTEGER user_id column
        user = User(telegram_id=big_tg_id, username="big")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        AnalyticsService.log_interaction(
            user_id=big_tg_id, session_id="ovf_s1",
            interaction_type="view_item", item_id=None,
        )
        row = db_session.scalar(
            select(UserInteraction).where(UserInteraction.session_id == "ovf_s1")
        )
        assert row is not None
        assert row.user_id == user.id  # users.id PK, not the raw telegram id

    def test_log_interaction_unknown_telegram_id_logs_null_user(self, db_session):
        from services.analytics import AnalyticsService
        AnalyticsService.log_interaction(
            user_id=999999999999, session_id="ovf_s2",
            interaction_type="view_item", item_id=None,
        )
        row = db_session.scalar(
            select(UserInteraction).where(UserInteraction.session_id == "ovf_s2")
        )
        assert row is not None
        assert row.user_id is None

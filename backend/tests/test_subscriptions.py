"""
Backend tests for subscription cap math, lapse mechanism and credit accounting
(TECH-26/28 — blueprint §2.3/§5.2).

Phase 1 scope: get_effective_alert_cap, get_active_subscription,
get_credit_boosts_remaining, lapse_benefits, reactivate_lapsed_alerts.
Fulfillment/order tests land with Phase 3.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from constants import (
    MAX_ALERTS_PER_USER,
    ALERTS_SUBSCRIPTION_EXTRA_ALERTS,
    ALL_IN_ONE_MONTHLY_BOOST_CREDIT,
    ALERT_CAP_BANNER_THRESHOLD,
    ALERTS_ONLY_PRICE_STARS,
    ALL_IN_ONE_PRICE_STARS,
    BOOST_DURATION_DAYS,
    BOOST_PRICE_STARS,
)
from models import User, Subscription, Alert, Boost
from services.subscriptions import (
    get_effective_alert_cap,
    get_active_subscription,
    get_credit_boosts_remaining,
    lapse_benefits,
    reactivate_lapsed_alerts,
)


def _make_user(db, telegram_id=111):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_alert(db, user, *, is_active=True, lapsed=False, deleted=False):
    import json
    from ai_engine.vector_client import vectorize_text
    vec = vectorize_text("test alert query")
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    alert = Alert(
        user_id=user.id,
        query_text="test alert query",
        query_vector=vec,
        preferences=json.dumps({}),
        is_active=is_active,
        lapsed=lapsed,
        deleted_at=None if not deleted else datetime.now(timezone.utc),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _make_subscription(db, user, *, product="alerts_only", status="active",
                       end_delta=timedelta(days=29), charge_id="chg_sub"):
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id, product=product, status=status,
        telegram_payment_charge_id=charge_id,
        invoice_payload=f"s:{user.id}:{product}:abc",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + end_delta,
        is_recurring=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# Cap math (blueprint §2.3 — the single cap authority, D3)
# ---------------------------------------------------------------------------

class TestEffectiveAlertCap:
    def test_free_tier_cap_is_max_alerts_per_user(self, db_session):
        user = _make_user(db_session)
        assert get_effective_alert_cap(db_session, user) == MAX_ALERTS_PER_USER

    def test_cap_raised_by_active_alerts_only_subscription(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="alerts_only")
        assert get_effective_alert_cap(db_session, user) == (
            MAX_ALERTS_PER_USER + ALERTS_SUBSCRIPTION_EXTRA_ALERTS
        )

    def test_cap_raised_by_active_all_in_one_subscription(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="all_in_one")
        assert get_effective_alert_cap(db_session, user) == (
            MAX_ALERTS_PER_USER + ALERTS_SUBSCRIPTION_EXTRA_ALERTS
        )

    def test_expired_subscription_does_not_raise_cap(self, db_session):
        user = _make_user(db_session)
        _make_subscription(
            db_session, user, end_delta=timedelta(days=-1), charge_id="chg_exp")
        assert get_effective_alert_cap(db_session, user) == MAX_ALERTS_PER_USER

    def test_canceled_subscription_does_not_raise_cap(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, status="canceled", charge_id="chg_c")
        assert get_effective_alert_cap(db_session, user) == MAX_ALERTS_PER_USER


# ---------------------------------------------------------------------------
# Active subscription predicate (blueprint §2.3)
# ---------------------------------------------------------------------------

class TestGetActiveSubscription:
    def test_returns_active_subscription(self, db_session):
        user = _make_user(db_session)
        sub = _make_subscription(db_session, user)
        assert get_active_subscription(db_session, user).id == sub.id

    def test_none_without_subscription(self, db_session):
        user = _make_user(db_session)
        assert get_active_subscription(db_session, user) is None

    def test_ignores_expired_and_canceled(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, end_delta=timedelta(days=-2),
                           charge_id="chg_e")
        _make_subscription(db_session, user, status="failed", charge_id="chg_f")
        assert get_active_subscription(db_session, user) is None


# ---------------------------------------------------------------------------
# Lapse mechanism (blueprint §2.3 / Rule 7.1.2 — distinct from user pause)
# ---------------------------------------------------------------------------

class TestLapseBenefits:
    def test_lapse_pauses_alerts_beyond_free_cap_oldest_first(self, db_session):
        user = _make_user(db_session)
        alerts = [_make_alert(db_session, user) for _ in range(MAX_ALERTS_PER_USER + 5)]

        lapse_benefits(db_session, user)

        # The first MAX_ALERTS_PER_USER (by id) stay active and untouched.
        for alert in alerts[:MAX_ALERTS_PER_USER]:
            db_session.refresh(alert)
            assert alert.is_active is True
            assert alert.lapsed is False
        # The rest are lapse-deactivated: distinguishable from user pause.
        for alert in alerts[MAX_ALERTS_PER_USER:]:
            db_session.refresh(alert)
            assert alert.is_active is False
            assert alert.lapsed is True

    def test_lapse_preserves_user_pause_marker(self, db_session):
        user = _make_user(db_session)
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)
        user_paused = _make_alert(db_session, user, is_active=False, lapsed=False)
        extra = _make_alert(db_session, user)

        lapse_benefits(db_session, user)

        db_session.refresh(user_paused)
        assert user_paused.lapsed is False  # user pause stays a user pause

        db_session.refresh(extra)
        assert extra.lapsed is True  # lapse-deactivated only

    def test_lapse_uses_free_cap_even_with_active_subscription(self, db_session):
        # The blueprint is explicit: lapse deactivates alerts past the FREE
        # cap (MAX_ALERTS_PER_USER) — the effective cap never protects here.
        user = _make_user(db_session)
        _make_subscription(db_session, user)
        for _ in range(MAX_ALERTS_PER_USER + 2):
            _make_alert(db_session, user)

        lapse_benefits(db_session, user)

        active = db_session.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id, Alert.is_active == True
            )
        )
        assert active == MAX_ALERTS_PER_USER


class TestReactivateLapsedAlerts:
    def test_renewal_reactivates_lapsed_oldest_first_up_to_cap(self, db_session):
        user = _make_user(db_session)
        active = [_make_alert(db_session, user) for _ in range(MAX_ALERTS_PER_USER)]
        lapsed = [_make_alert(db_session, user, is_active=False, lapsed=True)
                  for _ in range(ALERTS_SUBSCRIPTION_EXTRA_ALERTS + 5)]
        _make_subscription(db_session, user)  # active sub -> cap raised

        reactivate_lapsed_alerts(db_session, user)

        for alert in active:
            db_session.refresh(alert)
            assert alert.is_active is True
        # Only enough to fill the raised cap: extra_alerts of them.
        for alert in lapsed[:ALERTS_SUBSCRIPTION_EXTRA_ALERTS]:
            db_session.refresh(alert)
            assert alert.is_active is True
        for alert in lapsed[ALERTS_SUBSCRIPTION_EXTRA_ALERTS:]:
            db_session.refresh(alert)
            assert alert.is_active is False
            assert alert.lapsed is True

    def test_renewal_reactivates_all_when_below_cap(self, db_session):
        user = _make_user(db_session)
        for _ in range(5):
            _make_alert(db_session, user)
        lapsed = [_make_alert(db_session, user, is_active=False, lapsed=True)
                  for _ in range(3)]
        _make_subscription(db_session, user)

        reactivate_lapsed_alerts(db_session, user)

        for alert in lapsed:
            db_session.refresh(alert)
            assert alert.is_active is True

    def test_no_subscription_reactivates_only_up_to_free_cap(self, db_session):
        # Reactivation is cap-bound, not subscription-bound: with the free cap
        # already full, a lapsed alert stays lapsed without a subscription.
        user = _make_user(db_session)
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)
        lapsed = _make_alert(db_session, user, is_active=False, lapsed=True)

        reactivate_lapsed_alerts(db_session, user)

        db_session.refresh(lapsed)
        assert lapsed.is_active is False

    def test_no_subscription_reactivates_within_free_cap(self, db_session):
        # Below the cap, renewal-free reactivation is allowed: the alert fits
        # the free tier.
        user = _make_user(db_session)
        lapsed = _make_alert(db_session, user, is_active=False, lapsed=True)

        reactivate_lapsed_alerts(db_session, user)

        db_session.refresh(lapsed)
        assert lapsed.is_active is True


# ---------------------------------------------------------------------------
# Credit accounting (blueprint §2.3 / Rule 7.3)
# ---------------------------------------------------------------------------

def _make_channel_item(db, user, telegram_id=111):
    from models import Channel, Item
    channel = Channel(
        username=f"ch_credit_{telegram_id}", title="Credit Channel",
        registered_by=telegram_id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id, title="Credit Item", category="Mobile Phones",
        price=100.0, status="active", is_active=True, image_path="c.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return channel, item


class TestCreditBoostsRemaining:
    def test_zero_without_all_in_one(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="alerts_only")
        assert get_credit_boosts_remaining(db_session, user) == 0

    def test_credit_counted_within_period(self, db_session):
        user = _make_user(db_session)
        sub = _make_subscription(db_session, user, product="all_in_one")
        channel, item = _make_channel_item(db_session, user)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=channel.id, user_id=user.id,
            source="credit", price_paid_stars=None,
            telegram_payment_charge_id=None,
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()

        remaining = get_credit_boosts_remaining(db_session, user)
        assert remaining == ALL_IN_ONE_MONTHLY_BOOST_CREDIT - 1

    def test_credit_expires_with_period(self, db_session):
        user = _make_user(db_session)
        sub = _make_subscription(db_session, user, product="all_in_one")
        # Advance the period end into the past: the credit boost no longer
        # counts, but the subscription is now inactive anyway.
        sub.current_period_end = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()
        assert get_credit_boosts_remaining(db_session, user) == 0

    def test_paid_boosts_do_not_consume_credit(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="all_in_one")
        channel, item = _make_channel_item(db_session, user)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=channel.id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_paid",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()
        assert get_credit_boosts_remaining(db_session, user) == ALL_IN_ONE_MONTHLY_BOOST_CREDIT


# ---------------------------------------------------------------------------
# Phase 3 (TECH-28): order, fulfillment, state updates
# ---------------------------------------------------------------------------

from services.subscriptions import (
    create_subscription_order,
    fulfill_subscription_payment,
    handle_subscription_state_update,
    get_subscription_status,
)
from constants import (
    ALERTS_ONLY_PRICE_STARS,
    ALL_IN_ONE_PRICE_STARS,
    SUBSCRIPTION_PERIOD_SECONDS,
)


class TestCreateSubscriptionOrder:
    @pytest.mark.asyncio
    async def test_order_alerts_only_uses_native_star_period(self, db_session, monkeypatch):
        from tests.fake_telegram_payments import FakeStarPaymentsAdapter
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.subscriptions.star_payments", fake)
        user = _make_user(db_session)

        result = await create_subscription_order(db_session, user, "alerts_only")

        assert result["invoice_url"].startswith("https://t.me/fake-invoice/")
        assert result["payload"].startswith("s:")
        assert result["price_stars"] == ALERTS_ONLY_PRICE_STARS
        call = fake.calls[0]
        assert call["method"] == "create_invoice_link"
        assert call["currency"] == "XTR"
        assert call["subscription_period"] == SUBSCRIPTION_PERIOD_SECONDS  # hard-locked 30d
        assert call["prices"] == [("Alerts Only", ALERTS_ONLY_PRICE_STARS)]

    @pytest.mark.asyncio
    async def test_order_all_in_one_price(self, db_session, monkeypatch):
        from tests.fake_telegram_payments import FakeStarPaymentsAdapter
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.subscriptions.star_payments", fake)
        user = _make_user(db_session)

        result = await create_subscription_order(db_session, user, "all_in_one")

        assert result["price_stars"] == ALL_IN_ONE_PRICE_STARS
        assert fake.calls[0]["prices"] == [("All-in-One", ALL_IN_ONE_PRICE_STARS)]

    @pytest.mark.asyncio
    async def test_order_invalid_product_400(self, db_session, monkeypatch):
        from tests.fake_telegram_payments import FakeStarPaymentsAdapter
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.subscriptions.star_payments", fake)
        user = _make_user(db_session)

        with pytest.raises(HTTPException) as exc:
            await create_subscription_order(db_session, user, "premium_plus")
        assert exc.value.status_code == 400
        assert len(fake.calls) == 0

    @pytest.mark.asyncio
    async def test_order_conflicts_with_existing_active_subscription(self, db_session, monkeypatch):
        from tests.fake_telegram_payments import FakeStarPaymentsAdapter
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.subscriptions.star_payments", fake)
        user = _make_user(db_session)
        _make_subscription(db_session, user)

        with pytest.raises(HTTPException) as exc:
            await create_subscription_order(db_session, user, "alerts_only")
        assert exc.value.status_code == 409
        assert len(fake.calls) == 0


class TestFulfillSubscriptionPayment:
    def test_fulfill_creates_active_subscription(self, db_session):
        user = _make_user(db_session)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        sub = fulfill_subscription_payment(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_sub_a",
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            total_amount=30,
            subscription_expiration_date=expires,
            is_recurring=False,
            is_first_recurring=True,
        )

        assert sub.user_id == user.id
        assert sub.product == "alerts_only"
        assert sub.status == "active"
        assert sub.telegram_payment_charge_id == "chg_sub_a"
        assert abs((sub.current_period_end - expires).total_seconds()) < 60
        assert sub.is_recurring is False

    def test_fulfill_idempotent_on_charge_id(self, db_session):
        user = _make_user(db_session)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        first = fulfill_subscription_payment(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_sub_b",
            invoice_payload=f"s:{user.id}:all_in_one:abc",
            total_amount=100,
            subscription_expiration_date=expires,
            is_recurring=False,
            is_first_recurring=True,
        )
        second = fulfill_subscription_payment(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_sub_b",
            invoice_payload=f"s:{user.id}:all_in_one:abc",
            total_amount=100,
            subscription_expiration_date=expires,
            is_recurring=False,
            is_first_recurring=True,
        )

        assert first.id == second.id
        subs = db_session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.user_id == user.id)
        )
        assert subs == 1

    def test_fulfill_renewal_updates_same_row_period_end(self, db_session):
        user = _make_user(db_session)
        now = datetime.now(timezone.utc)
        first_expires = now + timedelta(days=30)

        first = fulfill_subscription_payment(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_sub_c1",
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            total_amount=30,
            subscription_expiration_date=first_expires,
            is_recurring=False,
            is_first_recurring=True,
        )
        renewal_expires = now + timedelta(days=60)
        renewal = fulfill_subscription_payment(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_sub_c2",
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            total_amount=30,
            subscription_expiration_date=renewal_expires,
            is_recurring=True,
            is_first_recurring=False,
        )

        assert renewal.id == first.id  # SAME row
        assert renewal.is_recurring is True
        assert abs((renewal.current_period_end - renewal_expires).total_seconds()) < 60
        # period_start stays the initial purchase
        assert abs((renewal.current_period_start - first.current_period_start).total_seconds()) < 60

    def test_fulfill_requires_expiration_date(self, db_session):
        user = _make_user(db_session)
        with pytest.raises(HTTPException) as exc:
            fulfill_subscription_payment(
                db_session,
                telegram_user_id=111,
                telegram_payment_charge_id="chg_sub_d",
                invoice_payload=f"s:{user.id}:alerts_only:abc",
                total_amount=30,
                subscription_expiration_date=None,
                is_recurring=False,
                is_first_recurring=True,
            )
        assert exc.value.status_code == 400

    def test_fulfill_reactivates_lapsed_alerts(self, db_session):
        user = _make_user(db_session)
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)
        lapsed = _make_alert(db_session, user, is_active=False, lapsed=True)
        now = datetime.now(timezone.utc)

        fulfill_subscription_payment(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_sub_e",
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            total_amount=30,
            subscription_expiration_date=now + timedelta(days=30),
            is_recurring=False,
            is_first_recurring=True,
        )

        db_session.refresh(lapsed)
        assert lapsed.is_active is True  # raised cap absorbed the lapsed alert


class TestHandleSubscriptionStateUpdate:
    def test_canceled_lapses_benefits(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, charge_id="chg_state_1")
        for _ in range(MAX_ALERTS_PER_USER + 3):
            _make_alert(db_session, user)

        handle_subscription_state_update(
            db_session,
            telegram_user_id=111,
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            state="canceled",
        )

        sub = db_session.scalar(select(Subscription).where(
            Subscription.user_id == user.id))
        assert sub.status == "canceled"
        active = db_session.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id, Alert.is_active == True)
        )
        assert active == MAX_ALERTS_PER_USER
        lapsed_count = db_session.scalar(
            select(func.count(Alert.id)).where(
                Alert.user_id == user.id, Alert.lapsed == True)
        )
        assert lapsed_count == 3

    def test_unknown_state_ignored(self, db_session):
        user = _make_user(db_session)
        sub = _make_subscription(db_session, user, charge_id="chg_state_2")

        handle_subscription_state_update(
            db_session,
            telegram_user_id=111,
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            state="weird",
        )

        db_session.refresh(sub)
        assert sub.status == "active"  # untouched

    def test_active_state_reactivates(self, db_session):
        user = _make_user(db_session)
        # A subscription exists but is failed; its "active" state event arrives
        # (user re-activated via Telegram) -> benefits return.
        sub = _make_subscription(db_session, user, status="failed", charge_id="chg_state_3")
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)
        lapsed = _make_alert(db_session, user, is_active=False, lapsed=True)

        handle_subscription_state_update(
            db_session,
            telegram_user_id=111,
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            state="active",
        )

        db_session.refresh(sub)
        assert sub.status == "active"
        db_session.refresh(lapsed)
        assert lapsed.is_active is True  # raised cap absorbed the lapsed alert


class TestGetSubscriptionStatus:
    def test_status_without_subscription(self, db_session):
        user = _make_user(db_session)
        status = get_subscription_status(db_session, user)
        assert status["product"] is None
        assert status["extra_alerts"] == 0
        assert status["credit_remaining"] == 0

    def test_status_with_all_in_one(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="all_in_one", charge_id="chg_stat_1")
        status = get_subscription_status(db_session, user)
        assert status["product"] == "all_in_one"
        assert status["status"] == "active"
        assert status["extra_alerts"] == ALERTS_SUBSCRIPTION_EXTRA_ALERTS
        assert status["credit_remaining"] == ALL_IN_ONE_MONTHLY_BOOST_CREDIT
        assert status["credit_total"] == ALL_IN_ONE_MONTHLY_BOOST_CREDIT

    # ------------------------------------------------------------------
    # NB-48: the status payload is the hub's data endpoint — caps,
    # banner threshold and prices on BOTH branches (blueprint §2.2).
    # ------------------------------------------------------------------

    def test_status_without_subscription_exposes_caps_and_prices(self, db_session):
        user = _make_user(db_session)
        status = get_subscription_status(db_session, user)
        assert status["free_cap"] == MAX_ALERTS_PER_USER
        assert status["effective_cap"] == MAX_ALERTS_PER_USER
        assert status["cap_banner_threshold"] == ALERT_CAP_BANNER_THRESHOLD
        assert status["alerts_only_price_stars"] == ALERTS_ONLY_PRICE_STARS
        assert status["all_in_one_price_stars"] == ALL_IN_ONE_PRICE_STARS
        assert status["boost_floor_price_stars"] == BOOST_PRICE_STARS.get(
            "Other", min(BOOST_PRICE_STARS.values())
        )
        assert status["boost_duration_days"] == BOOST_DURATION_DAYS

    def test_status_with_all_in_one_exposes_effective_cap_and_prices(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="all_in_one", charge_id="chg_stat_2")
        status = get_subscription_status(db_session, user)
        assert status["free_cap"] == MAX_ALERTS_PER_USER
        assert status["effective_cap"] == (
            MAX_ALERTS_PER_USER + ALERTS_SUBSCRIPTION_EXTRA_ALERTS
        )
        assert status["cap_banner_threshold"] == ALERT_CAP_BANNER_THRESHOLD
        assert status["alerts_only_price_stars"] == ALERTS_ONLY_PRICE_STARS
        assert status["all_in_one_price_stars"] == ALL_IN_ONE_PRICE_STARS
        assert status["boost_floor_price_stars"] == BOOST_PRICE_STARS.get(
            "Other", min(BOOST_PRICE_STARS.values())
        )
        assert status["boost_duration_days"] == BOOST_DURATION_DAYS

    def test_status_with_alerts_only_exposes_effective_cap(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user, product="alerts_only", charge_id="chg_stat_3")
        status = get_subscription_status(db_session, user)
        assert status["product"] == "alerts_only"
        assert status["effective_cap"] == (
            MAX_ALERTS_PER_USER + ALERTS_SUBSCRIPTION_EXTRA_ALERTS
        )
        assert status["credit_total"] == 0

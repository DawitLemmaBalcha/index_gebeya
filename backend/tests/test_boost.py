"""
Backend tests for the Boost service core (TECH-26, blueprint §2.2/§5.2).

All tests run in-process against the isolated suq_test_db via the db_session
fixture. Telegram is replaced by the FakeStarPaymentsAdapter — no network.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from constants import (
    _get_config,
    _get_json_config,
    BOOST_PRICE_STARS,
    BOOST_DURATION_DAYS,
    SUBSCRIPTION_PERIOD_SECONDS,
    MAX_ALERTS_PER_USER,
    ALERT_CAP_BANNER_THRESHOLD,
)
from models import User, Channel, Item, Boost, Subscription
from services import boost as boost_service
from services.boost import (
    get_boost_price,
    create_boost_order,
    fulfill_boost,
    fulfill_credit_boost,
    get_pinned_boosted_items,
    compose_pinned_page,
    end_boost_for_item,
    transfer_boost,
    get_boost_status,
)
from tests.fake_telegram_payments import FakeStarPaymentsAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_seller_item(db, *, telegram_id=111, category="Mobile Phones",
                      status="active", is_active=True, title="iPhone 13",
                      price=100.0, channel_username=None):
    """Create seller user + channel + item. Returns (user, channel, item)."""
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(
        username=channel_username or f"ch_{telegram_id}",
        title="Test Channel",
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
        status=status,
        is_active=is_active,
        image_path="test.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


def _install_fake(db, monkeypatch):
    """Install the fake adapter on services.boost and return it."""
    fake = FakeStarPaymentsAdapter()
    monkeypatch.setattr("services.boost.star_payments", fake)
    return fake


def _active_boost(db, item_id):
    return db.scalar(
        select(Boost).where(Boost.item_id == item_id)
    )


def _count_boosts(db):
    return db.scalar(select(func.count(Boost.id)))


# ---------------------------------------------------------------------------
# Constants (blueprint §3.1 / D4)
# ---------------------------------------------------------------------------

class TestMonetizationConstants:
    def test_get_json_config_parses_env_json(self, monkeypatch):
        monkeypatch.setenv("BOOST_PRICE_STARS", '{"Mobile Phones":99}')
        assert _get_json_config("BOOST_PRICE_STARS", {}) == {"Mobile Phones": 99}

    def test_get_json_config_bad_json_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOOST_PRICE_STARS", "{definitely not json")
        default = {"Other": 25}
        assert _get_json_config("BOOST_PRICE_STARS", default) == default

    def test_get_json_config_missing_env_returns_default(self, monkeypatch):
        monkeypatch.delenv("BOOST_PRICE_STARS", raising=False)
        assert _get_json_config("BOOST_PRICE_STARS", {"Other": 25}) == {"Other": 25}

    def test_boost_price_defaults_cover_every_taxonomy_key(self):
        # Every top-level taxonomy key resolves to a positive price.
        for key in [
            "Mobile Phones", "Laptops & Computers", "Tablets", "Electronics",
            "Vehicles", "Property", "Home, Appliances & Furniture",
            "Men's Fashion", "Women's Fashion", "Shoes", "Health & Beauty",
            "Commercial & Tools", "Sports, Arts & Outdoors", "Babies & Kids",
            "Animals & Pets", "Agriculture & Food", "Services", "Other",
        ]:
            assert BOOST_PRICE_STARS.get(key, 0) > 0, f"missing price for {key}"

    def test_subscription_period_is_hard_locked_30_days(self):
        # Telegram hard-locks Star subscriptions to 2592000s. Plain constant,
        # NO env override.
        assert SUBSCRIPTION_PERIOD_SECONDS == 2592000

    # ------------------------------------------------------------------
    # NB-48: cap-banner threshold (frontend display threshold; the
    # backend contract is constants-loading + status-payload coverage).
    # ------------------------------------------------------------------

    def test_alert_cap_banner_threshold_defaults_to_2(self):
        assert ALERT_CAP_BANNER_THRESHOLD == 2

    def test_alert_cap_banner_threshold_env_override(self, monkeypatch):
        monkeypatch.setenv("ALERT_CAP_BANNER_THRESHOLD", "5")
        assert _get_config("ALERT_CAP_BANNER_THRESHOLD", 2, int) == 5

    def test_alert_cap_banner_threshold_negative_env_clamps_to_0(self, monkeypatch):
        monkeypatch.setenv("ALERT_CAP_BANNER_THRESHOLD", "-3")
        assert _get_config("ALERT_CAP_BANNER_THRESHOLD", 2, int) == 0


# ---------------------------------------------------------------------------
# Price lookup (blueprint §2.2)
# ---------------------------------------------------------------------------

class TestGetBoostPrice:
    def test_known_category_returns_configured_price(self, db_session):
        _, _, item = _make_seller_item(db_session, category="Mobile Phones")
        assert get_boost_price(db_session, item) == BOOST_PRICE_STARS["Mobile Phones"]

    def test_unknown_category_uses_other_floor(self, db_session):
        _, _, item = _make_seller_item(db_session, category="Quantum Gadgets")
        assert get_boost_price(db_session, item) == BOOST_PRICE_STARS["Other"]

    def test_price_is_always_positive_int(self, db_session):
        _, _, item = _make_seller_item(db_session, category="")
        price = get_boost_price(db_session, item)
        assert isinstance(price, int) and price > 0


# ---------------------------------------------------------------------------
# Order creation (blueprint §2.2 — purchase)
# ---------------------------------------------------------------------------

class TestCreateBoostOrder:
    @pytest.mark.asyncio
    async def test_order_creates_invoice_with_one_labeled_price(self, db_session, monkeypatch):
        fake = _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session)
        user = db_session.scalar(select(User).where(User.telegram_id == 111))

        result = await create_boost_order(db_session, user, item)

        assert result["invoice_url"].startswith("https://t.me/fake-invoice/")
        assert result["payload"].startswith("b:")
        assert len(result["payload"].encode()) <= 128  # Telegram payload limit
        assert result["price_stars"] == BOOST_PRICE_STARS["Mobile Phones"]
        assert result["duration_days"] == BOOST_DURATION_DAYS

        call = fake.calls[0]
        assert call["method"] == "create_invoice_link"
        assert call["currency"] == "XTR"
        assert call["prices"] == [("Boost", BOOST_PRICE_STARS["Mobile Phones"])]
        assert call["payload"] == result["payload"]
        assert call["subscription_period"] is None

    @pytest.mark.asyncio
    async def test_order_foreign_channel_forbidden(self, db_session, monkeypatch):
        _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session, telegram_id=111)
        other = User(telegram_id=222, username="u222")
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        with pytest.raises(HTTPException) as exc:
            await create_boost_order(db_session, other, item)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_order_sold_item_rejected(self, db_session, monkeypatch):
        _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session, status="sold")
        user = db_session.scalar(select(User).where(User.telegram_id == 111))

        with pytest.raises(HTTPException) as exc:
            await create_boost_order(db_session, user, item)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_order_soft_deleted_item_rejected(self, db_session, monkeypatch):
        _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session, is_active=False)
        user = db_session.scalar(select(User).where(User.telegram_id == 111))

        with pytest.raises(HTTPException) as exc:
            await create_boost_order(db_session, user, item)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_order_existing_active_boost_conflict(self, db_session, monkeypatch):
        fake = _install_fake(db_session, monkeypatch)
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_existing",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await create_boost_order(db_session, user, item)
        assert exc.value.status_code == 409
        assert len(fake.calls) == 0  # no invoice for a blocked order

    @pytest.mark.asyncio
    async def test_order_kill_switch_returns_503(self, db_session, monkeypatch):
        fake = _install_fake(db_session, monkeypatch)
        monkeypatch.setattr("services.boost.MONETIZATION_ENABLED", 0)
        user, _, item = _make_seller_item(db_session)

        with pytest.raises(HTTPException) as exc:
            await create_boost_order(db_session, user, item)
        assert exc.value.status_code == 503
        assert len(fake.calls) == 0


# ---------------------------------------------------------------------------
# Fulfillment (blueprint §2.2 — internal, idempotent)
# ---------------------------------------------------------------------------

class TestFulfillBoost:
    @pytest.mark.asyncio
    async def test_fulfill_activates_boost_with_charged_amount(self, db_session, monkeypatch):
        _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session)
        user = db_session.scalar(select(User).where(User.telegram_id == 111))
        order = await create_boost_order(db_session, user, item)
        charged = 150

        boost = fulfill_boost(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_123",
            invoice_payload=order["payload"],
            total_amount=charged,
        )

        assert boost.item_id == item.id
        assert boost.source == "paid"
        assert boost.price_paid_stars == charged
        assert boost.telegram_payment_charge_id == "chg_123"
        assert (boost.ends_at - boost.starts_at).days == BOOST_DURATION_DAYS

    @pytest.mark.asyncio
    async def test_fulfill_replay_returns_same_row_and_keeps_order_price(
            self, db_session, monkeypatch):
        fake = _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session)
        user = db_session.scalar(select(User).where(User.telegram_id == 111))
        order = await create_boost_order(db_session, user, item)

        # The category price changes AFTER the order was placed — fulfillment
        # must still record the charged amount, never re-read the price.
        monkeypatch.setattr("services.boost.BOOST_PRICE_STARS", {"Mobile Phones": 999, "Other": 999})

        first = fulfill_boost(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_replay",
            invoice_payload=order["payload"],
            total_amount=150,
        )
        second = fulfill_boost(
            db_session,
            telegram_user_id=111,
            telegram_payment_charge_id="chg_replay",
            invoice_payload=order["payload"],
            total_amount=150,
        )

        assert first.id == second.id
        assert _count_boosts(db_session) == 1
        assert first.price_paid_stars == 150

    @pytest.mark.asyncio
    async def test_fulfill_foreign_channel_owner_rejected(self, db_session, monkeypatch):
        _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session, telegram_id=111)
        other = User(telegram_id=222, username="u222")
        db_session.add(other)
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            fulfill_boost(
                db_session,
                telegram_user_id=222,  # not the channel owner
                telegram_payment_charge_id="chg_foreign",
                invoice_payload=f"b:{item.id}:abcd",
                total_amount=150,
            )
        assert exc.value.status_code == 403
        assert _count_boosts(db_session) == 0

    @pytest.mark.asyncio
    async def test_fulfill_malformed_payload_rejected(self, db_session, monkeypatch):
        _install_fake(db_session, monkeypatch)
        _, _, item = _make_seller_item(db_session)

        with pytest.raises(HTTPException) as exc:
            fulfill_boost(
                db_session,
                telegram_user_id=111,
                telegram_payment_charge_id="chg_bad",
                invoice_payload="not-a-boost-payload",
                total_amount=150,
            )
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Credit boosts (blueprint §2.2 / Rule 7.3)
# ---------------------------------------------------------------------------

class TestCreditBoost:
    def _all_in_one_subscription(self, db, user):
        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user.id, product="all_in_one", status="active",
            telegram_payment_charge_id="chg_sub_1",
            invoice_payload="s:1:all_in_one:abc",
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=29),
            is_recurring=True,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    def test_credit_boost_requires_subscription(self, db_session):
        _, _, item = _make_seller_item(db_session)
        user = db_session.scalar(select(User).where(User.telegram_id == 111))

        with pytest.raises(HTTPException) as exc:
            fulfill_credit_boost(db_session, user, item)
        assert exc.value.status_code == 400

    def test_credit_boost_consumes_credit_and_is_placement_indistinguishable(
            self, db_session):
        user, _, item = _make_seller_item(db_session)
        self._all_in_one_subscription(db_session, user)

        boost = fulfill_credit_boost(db_session, user, item)

        assert boost.source == "credit"
        assert boost.telegram_payment_charge_id is None
        assert boost.price_paid_stars is None
        assert (boost.ends_at - boost.starts_at).days == BOOST_DURATION_DAYS

        # Second credit boost exceeds the monthly credit (default 2? no —
        # one boost used, one left; this second one is the 2nd, then 0 left)
        item2 = Item(
            channel_id=item.channel_id, title="Second", category="Mobile Phones",
            price=50.0, status="active", is_active=True, image_path="t2.jpg",
        )
        db_session.add(item2)
        db_session.commit()
        db_session.refresh(item2)
        boost2 = fulfill_credit_boost(db_session, user, item2)
        assert boost2.id != boost.id

        item3 = Item(
            channel_id=item.channel_id, title="Third", category="Mobile Phones",
            price=50.0, status="active", is_active=True, image_path="t3.jpg",
        )
        db_session.add(item3)
        db_session.commit()
        db_session.refresh(item3)
        with pytest.raises(HTTPException) as exc:
            fulfill_credit_boost(db_session, user, item3)
        assert exc.value.status_code == 400

        # Both credit boosts appear in the pinned block alongside paid ones.
        paid = Boost(
            item_id=item3.id, channel_id=item3.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_paid_1",
            starts_at=datetime.now(timezone.utc),
            ends_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(paid)
        db_session.commit()

        pinned = get_pinned_boosted_items(db_session, category="Mobile Phones")
        pinned_ids = {i.id for i in pinned}
        assert item.id in pinned_ids      # credit #1
        assert item2.id in pinned_ids     # credit #2
        assert item3.id in pinned_ids     # paid

    def test_credit_boost_foreign_channel_forbidden(self, db_session):
        _, _, item = _make_seller_item(db_session, telegram_id=111)
        other = User(telegram_id=222, username="u222")
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)
        self._all_in_one_subscription(db_session, other)

        with pytest.raises(HTTPException) as exc:
            fulfill_credit_boost(db_session, other, item)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Pinned placement + rotation (blueprint §2.2 / Rules 3.x/4.x)
# ---------------------------------------------------------------------------

class TestPinnedBoostedItems:
    def _boost(self, db, item, user, *, days_left=7, charge=None):
        now = datetime.now(timezone.utc)
        b = Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=100,
            telegram_payment_charge_id=charge,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=days_left),
        )
        db.add(b)
        return b

    def test_pinned_returns_only_active_eligible_items(self, db_session):
        user, _, item_a = _make_seller_item(db_session, telegram_id=111, title="Alpha")
        _, _, item_b = _make_seller_item(db_session, telegram_id=112, title="Beta", status="sold")
        _, _, item_c = _make_seller_item(db_session, telegram_id=113, title="Gamma", is_active=False)
        _, _, item_d = _make_seller_item(db_session, telegram_id=114, title="Delta")
        self._boost(db_session, item_a, user, charge="chg_a")
        self._boost(db_session, item_b, user, charge="chg_b")   # sold -> excluded
        self._boost(db_session, item_c, user, charge="chg_c")   # soft-deleted -> excluded
        self._boost(db_session, item_d, user, charge="chg_d", days_left=-1)  # expired -> excluded
        db_session.commit()

        pinned = get_pinned_boosted_items(db_session)
        assert [i.id for i in pinned] == [item_a.id]

    def test_pinned_filters_by_category(self, db_session):
        user, _, phone = _make_seller_item(db_session, telegram_id=111, category="Mobile Phones", title="Phone")
        _, _, shoes = _make_seller_item(db_session, telegram_id=112, category="Shoes", title="Sneakers")
        self._boost(db_session, phone, user, charge="chg_p")
        self._boost(db_session, shoes, user, charge="chg_s")
        db_session.commit()

        pinned = get_pinned_boosted_items(db_session, category="Shoes")
        assert [i.id for i in pinned] == [shoes.id]

    def test_pinned_filters_by_query_text_case_insensitive(self, db_session):
        user, _, iphone = _make_seller_item(db_session, telegram_id=111, title="iPhone 13 Pro")
        _, _, samsung = _make_seller_item(db_session, telegram_id=112, title="Samsung Galaxy")
        self._boost(db_session, iphone, user, charge="chg_1")
        self._boost(db_session, samsung, user, charge="chg_2")
        db_session.commit()

        pinned = get_pinned_boosted_items(db_session, query_text="iphone")
        assert [i.id for i in pinned] == [iphone.id]

    def test_pinned_rotation_is_time_sliced_permutation(self, db_session):
        user, _, a = _make_seller_item(db_session, telegram_id=111, title="A")
        _, _, b = _make_seller_item(db_session, telegram_id=112, title="B")
        _, _, c = _make_seller_item(db_session, telegram_id=113, title="C")
        self._boost(db_session, a, user, charge="chg_a")
        self._boost(db_session, b, user, charge="chg_b")
        self._boost(db_session, c, user, charge="chg_c")
        db_session.commit()

        base = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        order_1 = [i.id for i in get_pinned_boosted_items(db_session, now=base)]
        order_2 = [i.id for i in get_pinned_boosted_items(
            db_session, now=base + timedelta(minutes=30))]
        order_3 = [i.id for i in get_pinned_boosted_items(db_session, now=base)]

        # Same clock -> same order; 30 minutes later -> rotated order.
        assert order_1 == order_3
        assert order_1 != order_2
        # Rotation is a permutation: same members, no duplicates.
        assert sorted(order_1) == sorted(order_2) == [a.id, b.id, c.id]
        assert len(order_1) == len(set(order_1))

    def test_pinned_empty_when_no_candidates(self, db_session):
        assert get_pinned_boosted_items(db_session) == []


# ---------------------------------------------------------------------------
# Shared pin composition (browse-seam blueprint §2.2 — the ONE application
# point for the pin layer across eligible surfaces: category browse and
# search results). Duck-typed over objects exposing .id + writable
# .is_boosted (ORM Item in browse, ItemResponse in search).
# ---------------------------------------------------------------------------

class TestComposePinnedPage:
    def _boost(self, db, item, user, *, days_left=7, charge=None):
        now = datetime.now(timezone.utc)
        b = Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=100,
            telegram_payment_charge_id=charge,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=days_left),
        )
        db.add(b)
        return b

    def test_pinned_first_in_rotation_order_and_flagged(self, db_session):
        user, _, boosted = _make_seller_item(db_session, telegram_id=111, title="Pinned")
        _, _, organic = _make_seller_item(db_session, telegram_id=112, title="Organic")
        self._boost(db_session, boosted, user, charge="chg_pin")
        db_session.commit()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

        page, pinned_ids = compose_pinned_page(
            db_session, category="Mobile Phones", items=[organic, boosted], now=now)

        # Pinned first in rotation order, then organic; every pinned element
        # flagged True, organic flagged False.
        assert [i.id for i in page] == [boosted.id, organic.id]
        assert pinned_ids == {boosted.id}
        assert boosted.is_boosted is True
        assert organic.is_boosted is False

    def test_no_duplicates_when_pinned_overlaps_organic(self, db_session):
        user, _, boosted = _make_seller_item(db_session, telegram_id=111, title="Pinned")
        self._boost(db_session, boosted, user, charge="chg_overlap")
        db_session.commit()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

        # Rule 3.4: an item present in BOTH pinned and items appears once.
        page, pinned_ids = compose_pinned_page(
            db_session, category="Mobile Phones", items=[boosted], now=now)

        assert [i.id for i in page] == [boosted.id]
        assert len(page) == len({i.id for i in page})
        assert pinned_ids == {boosted.id}
        assert boosted.is_boosted is True

    def test_no_pinned_case_returns_input_unchanged_all_false(self, db_session):
        _, _, a = _make_seller_item(db_session, telegram_id=111, title="A")
        _, _, b = _make_seller_item(db_session, telegram_id=112, title="B")
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

        page, pinned_ids = compose_pinned_page(
            db_session, category="Mobile Phones", items=[a, b], now=now)

        assert [i.id for i in page] == [a.id, b.id]
        assert pinned_ids == set()
        assert a.is_boosted is False
        assert b.is_boosted is False

    def test_category_filtered_pins_only(self, db_session):
        user, _, phone = _make_seller_item(db_session, telegram_id=111,
                                           category="Mobile Phones", title="Phone")
        _, _, shoes = _make_seller_item(db_session, telegram_id=112,
                                        category="Shoes", title="Sneakers")
        _, _, other_phone = _make_seller_item(db_session, telegram_id=113,
                                              category="Mobile Phones", title="Other Phone")
        self._boost(db_session, phone, user, charge="chg_phone")
        self._boost(db_session, shoes, user, charge="chg_shoes")
        self._boost(db_session, other_phone, user, charge="chg_other")
        db_session.commit()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

        page, pinned_ids = compose_pinned_page(
            db_session, category="Mobile Phones", items=[other_phone], now=now)

        # Pinned block contains ONLY same-category boosted items (no Shoes);
        # rotation order is clock-derived (Rule 4.2), so assert membership.
        assert pinned_ids == {phone.id, other_phone.id}
        assert {i.id for i in page} == {phone.id, other_phone.id}
        assert all(i.is_boosted for i in page)

    def test_query_text_pins_case_insensitive(self, db_session):
        user, _, iphone = _make_seller_item(db_session, telegram_id=111, title="iPhone 13 Pro")
        _, _, samsung = _make_seller_item(db_session, telegram_id=112, title="Samsung Galaxy")
        self._boost(db_session, iphone, user, charge="chg_iphone")
        self._boost(db_session, samsung, user, charge="chg_samsung")
        db_session.commit()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

        page, pinned_ids = compose_pinned_page(
            db_session, query_text="IPHONE", items=[samsung, iphone], now=now)

        assert pinned_ids == {iphone.id}
        assert [i.id for i in page] == [iphone.id, samsung.id]
        assert iphone.is_boosted is True
        assert samsung.is_boosted is False

    def test_pinned_presupplied_identical_to_internal_query_for_fixed_now(self, db_session):
        user, _, a = _make_seller_item(db_session, telegram_id=111, title="A")
        _, _, b = _make_seller_item(db_session, telegram_id=112, title="B")
        _, _, c = _make_seller_item(db_session, telegram_id=113, title="C")
        self._boost(db_session, a, user, charge="chg_a")
        self._boost(db_session, b, user, charge="chg_b")
        self._boost(db_session, c, user, charge="chg_c")
        db_session.commit()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        organic = [b, c]  # organic list may itself contain boosted items

        internal_page, internal_ids = compose_pinned_page(
            db_session, category="Mobile Phones", items=organic, now=now)
        pre = get_pinned_boosted_items(db_session, category="Mobile Phones", now=now)
        supplied_page, supplied_ids = compose_pinned_page(
            db_session, category="Mobile Phones", items=organic, now=now, pinned=pre)

        # Same clock + same category -> identical pinned order, identical page.
        assert [i.id for i in pre] == [i.id for i in get_pinned_boosted_items(
            db_session, category="Mobile Phones", now=now)]
        assert [i.id for i in supplied_page] == [i.id for i in internal_page]
        assert supplied_ids == internal_ids
        assert supplied_ids == {i.id for i in pre}

    def test_duck_typed_over_item_response_objects(self, db_session):
        # The search caller passes serialized ItemResponse instances
        # (perform_hybrid_search output) — compose must not require ORM.
        from schemas import ItemResponse
        user, _, boosted = _make_seller_item(db_session, telegram_id=111, title="Pinned")
        _, _, organic = _make_seller_item(db_session, telegram_id=112, title="Organic")
        self._boost(db_session, boosted, user, charge="chg_duck")
        db_session.commit()
        now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        boosted_resp = ItemResponse.model_validate(boosted)
        organic_resp = ItemResponse.model_validate(organic)

        page, pinned_ids = compose_pinned_page(
            db_session, category="Mobile Phones",
            items=[organic_resp, boosted_resp], now=now)

        assert [i.id for i in page] == [boosted.id, organic.id]
        assert pinned_ids == {boosted.id}
        assert boosted_resp.is_boosted is True
        assert organic_resp.is_boosted is False



# ---------------------------------------------------------------------------
# Lifecycle hooks (blueprint §2.2 / Rules 6.1/6.2)
# ---------------------------------------------------------------------------

class TestBoostLifecycle:
    def test_end_boost_for_item_expires_boost(self, db_session):
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=100,
            telegram_payment_charge_id="chg_end",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()

        end_boost_for_item(db_session, item.id)

        assert get_pinned_boosted_items(db_session) == []
        assert get_boost_status(db_session, item.id) is None

    def test_transfer_boost_moves_to_replacement_preserving_clock(self, db_session):
        user, channel, old_item = _make_seller_item(db_session, telegram_id=111, title="Old")
        new_item = Item(
            channel_id=channel.id, title="New", category="Mobile Phones",
            price=100.0, status="active", is_active=True, image_path="new.jpg",
        )
        db_session.add(new_item)
        db_session.commit()
        db_session.refresh(new_item)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=old_item.id, channel_id=channel.id, user_id=user.id,
            source="paid", price_paid_stars=100,
            telegram_payment_charge_id="chg_transfer",
            starts_at=now - timedelta(days=2), ends_at=now + timedelta(days=5),
        ))
        db_session.commit()

        transfer_boost(db_session, old_item.id, new_item.id)
        db_session.commit()  # ingestion commits atomically after the hook

        row = _active_boost(db_session, new_item.id)
        assert row is not None
        assert row.item_id == new_item.id
        # Wall-clock duration preserved: starts/ends untouched by transfer.
        assert (row.ends_at - row.starts_at).days == 7
        assert _active_boost(db_session, old_item.id) is None


# ---------------------------------------------------------------------------
# Status (blueprint §2.2)
# ---------------------------------------------------------------------------

class TestBoostStatus:
    def test_status_returns_active_boost_details(self, db_session):
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="credit", price_paid_stars=None,
            telegram_payment_charge_id=None,
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()

        status = get_boost_status(db_session, item.id)
        assert status["active"] is True
        assert status["source"] == "credit"
        assert status["ends_at"] is not None

    def test_status_none_without_boost(self, db_session):
        _, _, item = _make_seller_item(db_session)
        assert get_boost_status(db_session, item.id) is None


# ---------------------------------------------------------------------------
# Quote route boostability (UAT regression: the quote must expose boostable
# + reason so the frontend can HIDE the boost section for non-active items
# instead of showing a dead-end 400 "Only active items can be boosted").
# ---------------------------------------------------------------------------

class TestBoostQuoteRoute:
    """GET /items/{item_id}/boost-quote — boostability surfaced to the UI."""

    def _client(self, db_session):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from database import get_db
        from api.routes import items as items_router

        app = FastAPI()
        app.include_router(items_router.router, prefix="/items", tags=["Items"])

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def _init_data(self, telegram_id):
        return f'user={json.dumps({"id": telegram_id, "username": f"u{telegram_id}"})}'

    def _quote(self, db_session, item_id, telegram_id=111):
        return self._client(db_session).get(
            f"/items/{item_id}/boost-quote",
            params={"init_data": self._init_data(telegram_id)},
        )

    def test_quote_active_item_is_boostable(self, db_session):
        _, _, item = _make_seller_item(db_session)
        resp = self._quote(db_session, item.id)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["boostable"] is True
        assert data["reason"] is None
        assert data["price_stars"] > 0
        assert data["duration_days"] == BOOST_DURATION_DAYS
        assert data["active_boost"] is None

    def test_quote_sold_item_not_boostable(self, db_session):
        _, _, item = _make_seller_item(db_session, status="sold")
        resp = self._quote(db_session, item.id)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["boostable"] is False
        assert data["reason"]  # non-empty human-readable reason

    def test_quote_reported_sold_item_not_boostable(self, db_session):
        _, _, item = _make_seller_item(db_session, status="reported_sold")
        data = self._quote(db_session, item.id).json()
        assert data["boostable"] is False
        assert data["reason"]

    def test_quote_soft_deleted_item_not_boostable(self, db_session):
        _, _, item = _make_seller_item(db_session, is_active=False)
        data = self._quote(db_session, item.id).json()
        assert data["boostable"] is False
        assert data["reason"]

    def test_quote_item_with_active_boost_conflict(self, db_session):
        user, _, item = _make_seller_item(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source="paid", price_paid_stars=10,
            telegram_payment_charge_id="chg_quote_conflict",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.commit()
        data = self._quote(db_session, item.id).json()
        assert data["boostable"] is False
        assert "boost" in data["reason"].lower()

    def test_quote_price_still_returned_for_non_boostable_item(self, db_session):
        # Additive contract: even a non-boostable item keeps its quote fields
        # (price is contextual, Rule 2.4) so the UI can decide how to render.
        _, _, item = _make_seller_item(db_session, status="sold")
        data = self._quote(db_session, item.id).json()
        assert data["price_stars"] > 0
        assert data["category"] == "Mobile Phones"

    def test_quote_non_owner_forbidden(self, db_session):
        _, _, item = _make_seller_item(db_session, telegram_id=111)
        resp = self._quote(db_session, item.id, telegram_id=222)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# NB-48: GET /channels/{channel_id}/boosts — owner-scoped active-boost summary
# (blueprint §2.3). Router include pattern mirrors TestBoostQuoteRoute.
# ---------------------------------------------------------------------------

class TestChannelBoostsRoute:
    """GET /channels/{channel_id}/boosts — active boosts for the Stores card."""

    def _client(self, db_session):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from database import get_db
        from api.routes import channels as channels_router

        app = FastAPI()
        app.include_router(channels_router.router, prefix="/channels", tags=["Channels"])

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def _init_data(self, telegram_id):
        return f'user={json.dumps({"id": telegram_id, "username": f"u{telegram_id}"})}'

    def _boosts(self, db_session, channel_id, telegram_id=111):
        return self._client(db_session).get(
            f"/channels/{channel_id}/boosts",
            params={"init_data": self._init_data(telegram_id)},
        )

    def _active_boost_row(self, db, item, user, *, ends_in_days=3, source="paid",
                          charge_id=None):
        now = datetime.now(timezone.utc)
        boost = Boost(
            item_id=item.id, channel_id=item.channel_id, user_id=user.id,
            source=source, price_paid_stars=10,
            telegram_payment_charge_id=charge_id or f"chg_boost_{item.id}",
            starts_at=now, ends_at=now + timedelta(days=ends_in_days),
        )
        db.add(boost)
        db.commit()
        db.refresh(boost)
        return boost

    def test_owner_sees_active_boost_summary_shape(self, db_session):
        user, channel, item = _make_seller_item(db_session)
        self._active_boost_row(db_session, item, user)
        resp = self._boosts(db_session, channel.id)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert set(row.keys()) == {"item_id", "title", "ends_at", "source"}
        assert row["item_id"] == item.id
        assert row["title"] == item.title
        assert row["source"] == "paid"
        assert row["ends_at"] is not None

    def test_expired_boost_excluded(self, db_session):
        user, channel, item = _make_seller_item(db_session)
        self._active_boost_row(db_session, item, user, ends_in_days=-1)
        resp = self._boosts(db_session, channel.id)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_sold_item_boost_excluded(self, db_session):
        user, channel, item = _make_seller_item(db_session)
        self._active_boost_row(db_session, item, user)
        end_boost_for_item(db_session, item.id)  # Rule 6.1: sold -> boost ends
        resp = self._boosts(db_session, channel.id)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_sorted_ends_at_ascending(self, db_session):
        user, channel, item_a = _make_seller_item(db_session, title="Item A")
        item_b = Item(
            channel_id=channel.id, title="Item B", category="Mobile Phones",
            price=50.0, status="active", is_active=True, image_path="b.jpg",
        )
        db_session.add(item_b)
        db_session.commit()
        db_session.refresh(item_b)
        self._active_boost_row(db_session, item_a, user, ends_in_days=5, charge_id="chg_a")
        self._active_boost_row(db_session, item_b, user, ends_in_days=1, charge_id="chg_b")
        resp = self._boosts(db_session, channel.id)
        assert resp.status_code == 200, resp.text
        assert [r["item_id"] for r in resp.json()] == [item_b.id, item_a.id]

    def test_dedupes_per_item_latest_boost_wins(self, db_session):
        user, channel, item = _make_seller_item(db_session)
        self._active_boost_row(db_session, item, user, ends_in_days=1, charge_id="chg_old")
        self._active_boost_row(db_session, item, user, ends_in_days=3, charge_id="chg_new")
        resp = self._boosts(db_session, channel.id)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        assert data[0]["item_id"] == item.id
        assert data[0]["ends_at"] is not None

    def test_non_owner_forbidden(self, db_session):
        user, channel, item = _make_seller_item(db_session, telegram_id=111)
        self._active_boost_row(db_session, item, user)
        resp = self._boosts(db_session, channel.id, telegram_id=222)
        assert resp.status_code == 403

    def test_kill_switch_returns_503(self, db_session, monkeypatch):
        user, channel, item = _make_seller_item(db_session)
        self._active_boost_row(db_session, item, user)
        monkeypatch.setattr("api.routes.channels.MONETIZATION_ENABLED", 0)
        resp = self._boosts(db_session, channel.id)
        assert resp.status_code == 503

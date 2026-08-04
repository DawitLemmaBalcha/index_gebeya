"""
Backend tests for the Boost service core (TECH-26, blueprint §2.2/§5.2).

All tests run in-process against the isolated suq_test_db via the db_session
fixture. Telegram is replaced by the FakeStarPaymentsAdapter — no network.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from constants import (
    _get_json_config,
    BOOST_PRICE_STARS,
    BOOST_DURATION_DAYS,
    SUBSCRIPTION_PERIOD_SECONDS,
    MAX_ALERTS_PER_USER,
)
from models import User, Channel, Item, Boost, Subscription
from services import boost as boost_service
from services.boost import (
    get_boost_price,
    create_boost_order,
    fulfill_boost,
    fulfill_credit_boost,
    get_pinned_boosted_items,
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

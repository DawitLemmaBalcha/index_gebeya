"""
NB-51: DB-first boost pricing (Rule 4.1.1/4.1.2, blueprint §2.4).

Seed idempotency, the fallback chain, cache invalidation + TTL.
"""
import time

import pytest
from sqlalchemy import func, select

from ai_engine.prompts import TAXONOMY_STRUCTURE
from constants import BOOST_PRICE_STARS
from models import BoostPrice, Channel, Item
from services.boost_pricing import (
    get_boost_floor,
    get_boost_price,
    get_boost_price_by_key,
    seed_boost_prices,
    set_boost_price,
)

EXPECTED_ROWS = sum(len(subs) for subs in TAXONOMY_STRUCTURE.values()) + len(TAXONOMY_STRUCTURE)


def _item(db, *, category="Mobile Phones", subcategory="Android Phones"):
    channel = Channel(username="ch_pricing", title="C", registered_by=111)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id, title="t", category=category, subcategory=subcategory,
        status="active", is_active=True, image_path="x.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _count(db):
    return db.scalar(select(func.count()).select_from(BoostPrice))


class TestSeed:
    def test_seed_creates_subcategory_and_category_rows(self, db_session):
        inserted = seed_boost_prices(db_session)
        assert inserted == EXPECTED_ROWS  # 95 subcategories + 18 category rows
        assert _count(db_session) == EXPECTED_ROWS

    def test_seed_is_idempotent_second_call_inserts_zero(self, db_session):
        seed_boost_prices(db_session)
        assert seed_boost_prices(db_session) == 0
        assert _count(db_session) == EXPECTED_ROWS

    def test_seed_never_overwrites_operator_edits(self, db_session):
        set_boost_price(
            db_session, category="Other", subcategory="Mixed",
            price_stars=99, updated_by="admin",
        )
        seed_boost_prices(db_session)
        row = db_session.scalar(
            select(BoostPrice).where(
                BoostPrice.category == "Other", BoostPrice.subcategory == "Mixed"
            )
        )
        assert row.price_stars == 99

    def test_every_taxonomy_subcategory_gets_a_row(self, db_session):
        seed_boost_prices(db_session)
        for category, subs in TAXONOMY_STRUCTURE.items():
            for sub in subs:
                assert db_session.scalar(
                    select(func.count()).select_from(BoostPrice).where(
                        BoostPrice.category == category, BoostPrice.subcategory == sub
                    )
                ) == 1, f"missing row for {category}/{sub}"

    def test_seeded_rows_match_constant_prices(self, db_session):
        seed_boost_prices(db_session)
        for category, subs in TAXONOMY_STRUCTURE.items():
            expected = int(BOOST_PRICE_STARS.get(category, 25))
            for sub in [""] + subs:
                row = db_session.scalar(
                    select(BoostPrice).where(
                        BoostPrice.category == category, BoostPrice.subcategory == sub
                    )
                )
                assert row.price_stars == expected


class TestFallbackChain:
    def test_subcategory_row_wins(self, db_session):
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="Android Phones",
            price_stars=111, updated_by="admin",
        )
        item = _item(db_session, subcategory="Android Phones")
        assert get_boost_price(db_session, item) == 111

    def test_category_empty_row_wins_for_missing_subcategory(self, db_session):
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="",
            price_stars=77, updated_by="admin",
        )
        item = _item(db_session, subcategory="Unseeded Sub")
        assert get_boost_price(db_session, item) == 77

    def test_category_empty_row_wins_for_item_without_subcategory(self, db_session):
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="",
            price_stars=77, updated_by="admin",
        )
        item = _item(db_session, subcategory=None)
        assert get_boost_price(db_session, item) == 77

    def test_unseeded_subcategory_falls_back_to_constant(self, db_session):
        item = _item(db_session, subcategory="Nonexistent Sub")
        assert get_boost_price(db_session, item) == BOOST_PRICE_STARS["Mobile Phones"]

    def test_unknown_category_uses_other_floor(self, db_session):
        item = _item(db_session, category="Quantum Gadgets", subcategory="Q")
        assert get_boost_price(db_session, item) == BOOST_PRICE_STARS.get("Other", 25)

    def test_floor_constant_is_25(self, db_session):
        assert get_boost_floor(db_session) == BOOST_PRICE_STARS.get("Other", 25)

    def test_price_by_key_mirrors_item_price(self, db_session):
        set_boost_price(
            db_session, category="Vehicles", subcategory="Cars",
            price_stars=200, updated_by="admin",
        )
        assert get_boost_price_by_key(db_session, "Vehicles", "Cars") == 200
        assert get_boost_price_by_key(
            db_session, "Vehicles", "No Such Sub"
        ) == BOOST_PRICE_STARS["Vehicles"]


class TestCache:
    def test_set_price_invalidates_cache_immediately(self, db_session):
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="Android Phones",
            price_stars=111, updated_by="admin",
        )
        item = _item(db_session, subcategory="Android Phones")
        assert get_boost_price(db_session, item) == 111
        # edit -> next read reflects it instantly (no TTL wait)
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="Android Phones",
            price_stars=222, updated_by="admin",
        )
        assert get_boost_price(db_session, item) == 222

    def test_ttl_expiry_refreshes_from_db(self, db_session, monkeypatch):
        set_boost_price(
            db_session, category="Mobile Phones", subcategory="Android Phones",
            price_stars=111, updated_by="admin",
        )
        item = _item(db_session, subcategory="Android Phones")
        assert get_boost_price(db_session, item) == 111

        # raw SQL edit (bypasses set_boost_price -> no invalidation)
        row = db_session.scalar(
            select(BoostPrice).where(
                BoostPrice.category == "Mobile Phones",
                BoostPrice.subcategory == "Android Phones",
            )
        )
        row.price_stars = 222
        db_session.commit()

        # cache still fresh -> stale 111
        assert get_boost_price(db_session, item) == 111

        # advance the clock past the 60s TTL -> fresh read 222
        monkeypatch.setattr(
            "services.boost_pricing._now_ts",
            lambda: time.monotonic() + 120,
        )
        assert get_boost_price(db_session, item) == 222

    def test_set_price_validates_positive_int(self, db_session):
        with pytest.raises(ValueError):
            set_boost_price(
                db_session, category="Other", subcategory="Mixed",
                price_stars=0, updated_by="admin",
            )
        with pytest.raises(ValueError):
            set_boost_price(
                db_session, category="Other", subcategory="Mixed",
                price_stars="150", updated_by="admin",
            )

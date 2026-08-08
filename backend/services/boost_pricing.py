"""
NB-51: DB-first boost pricing — the single price authority (Rule 4.1.1).

Fallback chain (Rule 4.1.2): DB row (category, subcategory) → DB row
(category, "") category-level fallback → constant BOOST_PRICE_STARS
exact-key → Other floor 25. Seed over ai_engine.prompts.TAXONOMY_STRUCTURE
(113 rows: 95 subcategories + 18 category rows), INSERT ... ON CONFLICT
DO NOTHING — operator price edits are never overwritten by later seeds.

Cache: module-level {(category, subcategory): (price, monotonic_ts)};
reads younger than 60s TTL are served from cache; edits invalidate the
touched keys immediately. Cycle-free by construction (D12): imports
models + constants ONLY — subscriptions.py reads the floor from here.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from constants import BOOST_PRICE_STARS
from models import BoostPrice

logger = logging.getLogger("index_boost_pricing")

_FLOOR = 25
_TTL_SECONDS = 60

# {(category, subcategory): (price_stars, monotonic_ts)}
_cache: dict[tuple[str, str], tuple[int, float]] = {}


def _now_ts() -> float:
    return time.monotonic()


def _read(db: Session, category: str, subcategory: str) -> int | None:
    """DB row read with TTL cache. Returns None when no row exists."""
    key = (category, subcategory)
    hit = _cache.get(key)
    if hit is not None and _now_ts() - hit[1] < _TTL_SECONDS:
        return hit[0]
    row = db.scalar(
        select(BoostPrice).where(
            BoostPrice.category == category,
            BoostPrice.subcategory == subcategory,
        )
    )
    if row is None:
        return None
    _cache[key] = (row.price_stars, _now_ts())
    return row.price_stars


def _constant_price(category: str) -> int:
    price = BOOST_PRICE_STARS.get(category)
    if not price:
        price = BOOST_PRICE_STARS.get("Other", _FLOOR)
    return max(1, int(price))


def get_boost_price(db: Session, item) -> int:
    """The interface boost.py re-exports (items.py callers unchanged, D14).
    Fallback chain per Rule 4.1.2."""
    sub = (item.subcategory or "").strip()
    if sub:
        price = _read(db, item.category, sub)
        if price is not None:
            return price
    price = _read(db, item.category, "")
    if price is not None:
        return price
    return _constant_price(item.category)


def get_boost_price_by_key(db: Session, category: str, subcategory: str) -> int:
    """Same fallback chain keyed explicitly (ops monetization surface)."""
    sub = (subcategory or "").strip()
    if sub:
        price = _read(db, category, sub)
        if price is not None:
            return price
    price = _read(db, category, "")
    if price is not None:
        return price
    return _constant_price(category)


def get_boost_floor(db: Session) -> int:
    """The subscription-hub floor: 'Other' row, else constant floor 25.
    subscriptions.py's new source (D12 cycle rule)."""
    price = _read(db, "Other", "")
    if price is not None:
        return price
    return int(BOOST_PRICE_STARS.get("Other", _FLOOR))


def set_boost_price(
    db: Session, *,
    category: str,
    subcategory: str,
    price_stars: int,
    updated_by: str | None = None,
) -> BoostPrice:
    """Upsert one row; invalidates the touched cache key immediately so
    the next quote/order reflects the edit (Rule 4.1.1)."""
    if not isinstance(price_stars, int) or price_stars < 1:
        raise ValueError("price_stars must be a positive int")
    row = db.scalar(
        select(BoostPrice).where(
            BoostPrice.category == category,
            BoostPrice.subcategory == subcategory,
        )
    )
    if row is None:
        row = BoostPrice(
            category=category,
            subcategory=subcategory,
            price_stars=price_stars,
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.price_stars = price_stars
        row.updated_by = updated_by
    db.commit()
    db.refresh(row)
    _cache.pop((category, subcategory), None)
    return row


def set_boost_price_bulk(
    db: Session, *,
    category: str,
    subcategory: str,
    price_stars: int,
    updated_by: str | None = None,
) -> None:
    """Bulk-ops convenience (one row per call from the route loop); same
    invalidation semantics as set_boost_price."""
    set_boost_price(
        db, category=category, subcategory=subcategory,
        price_stars=price_stars, updated_by=updated_by,
    )


def invalidate_boost_price_cache() -> None:
    """Clear the whole cache (bulk edits + tests)."""
    _cache.clear()


def seed_boost_prices(db: Session) -> int:
    """Idempotent startup seed over TAXONOMY_STRUCTURE: one row per
    subcategory + one (category, '') fallback row per category = 113 rows.
    INSERT ... ON CONFLICT DO NOTHING — returns the inserted count."""
    from ai_engine.prompts import TAXONOMY_STRUCTURE

    inserted = 0
    for category, subs in TAXONOMY_STRUCTURE.items():
        price = _constant_price(category)
        for subcategory in [""] + list(subs):
            stmt = pg_insert(BoostPrice).values(
                category=category,
                subcategory=subcategory,
                price_stars=price,
            ).on_conflict_do_nothing(index_elements=["category", "subcategory"])
            result = db.execute(stmt)
            inserted += result.rowcount or 0
    db.commit()
    if inserted:
        logger.info(f"🌱 Seeded {inserted} boost price rows")
    return inserted

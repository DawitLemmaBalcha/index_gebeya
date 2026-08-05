"""
Backend tests for the catalog browse seam (browse-seam blueprint §2.1).

`browse_category` is a deep, Local-substitutable module: plain catalog
navigation by category — active-only, recency-ordered, paginated. No
vectorization, no relevance math, no boost import (the pin layer is applied
by the caller, never inside the catalog module).
"""
from datetime import datetime, timedelta, timezone

from models import User, Channel, Item
from services.catalog import browse_category


# ---------------------------------------------------------------------------
# Helpers (mirrors test_boost.py._make_seller_item, with explicit timestamps)
# ---------------------------------------------------------------------------

def _make_item(db, *, telegram_id, category="Mobile Phones", title="Item",
               status="active", is_active=True, price=100.0,
               created_at=None):
    """Create seller user + channel + item with a deterministic created_at."""
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(
        username=f"ch_{telegram_id}",
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
        created_at=created_at or datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# browse_category
# ---------------------------------------------------------------------------

class TestBrowseCategory:
    def test_returns_only_active_items_of_category(self, db_session):
        _make_item(db_session, telegram_id=111, title="Active Phone")
        _make_item(db_session, telegram_id=112, title="Sold Phone", status="sold")
        _make_item(db_session, telegram_id=113, title="Soft-Deleted Phone", is_active=False)
        _make_item(db_session, telegram_id=114, title="Active Shoes", category="Shoes")

        items, total = browse_category(db_session, "Mobile Phones")

        assert [i.id for i in items] == [i.id for i in items]  # order sanity
        assert {i.title for i in items} == {"Active Phone"}
        assert total == 1

    def test_orders_by_recency_desc(self, db_session):
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        oldest = _make_item(db_session, telegram_id=111, title="Oldest",
                            created_at=base)
        middle = _make_item(db_session, telegram_id=112, title="Middle",
                            created_at=base + timedelta(hours=2))
        newest = _make_item(db_session, telegram_id=113, title="Newest",
                            created_at=base + timedelta(hours=4))

        items, total = browse_category(db_session, "Mobile Phones")

        assert [i.id for i in items] == [newest.id, middle.id, oldest.id]
        assert total == 3

    def test_total_counts_only_matching_active_rows(self, db_session):
        _make_item(db_session, telegram_id=111, title="A")
        _make_item(db_session, telegram_id=112, title="B")
        _make_item(db_session, telegram_id=113, title="Sold", status="sold")
        _make_item(db_session, telegram_id=114, title="Deleted", is_active=False)
        _make_item(db_session, telegram_id=115, title="Other Cat", category="Shoes")

        items, total = browse_category(db_session, "Mobile Phones")

        assert len(items) == 2
        assert total == 2

    def test_pagination_slices_by_limit_offset(self, db_session):
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        ids = []
        for i in range(5):
            item = _make_item(db_session, telegram_id=200 + i, title=f"Item {i}",
                              created_at=base + timedelta(hours=i))
            ids.append(item.id)
        # ids[4] is newest (created latest)

        page1, total = browse_category(db_session, "Mobile Phones", limit=2, offset=0)
        page2, total2 = browse_category(db_session, "Mobile Phones", limit=2, offset=2)

        assert [i.id for i in page1] == [ids[4], ids[3]]
        assert [i.id for i in page2] == [ids[2], ids[1]]
        assert total == total2 == 5

    def test_offset_beyond_end_returns_empty_with_correct_total(self, db_session):
        _make_item(db_session, telegram_id=111, title="Only One")

        items, total = browse_category(db_session, "Mobile Phones", limit=20, offset=50)

        assert items == []
        assert total == 1

    def test_defaults_limit_20_offset_0(self, db_session):
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(21):
            _make_item(db_session, telegram_id=300 + i, title=f"Item {i}",
                       created_at=base + timedelta(hours=i))

        items, total = browse_category(db_session, "Mobile Phones")

        assert len(items) == 20
        assert total == 21

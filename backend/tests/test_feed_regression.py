"""
User-verified regression (NB-55): the Explore feed showed a limited set of
items and scrolling stopped. Backend half of the root cause: when the
trending set overlaps the most-recent set, `get_trending_items`'s
recent-backfill skips already-included ids WITHOUT extending the fetch — a
40-item catalog yields a 15-item first page (< LIMIT) and the frontend
flips hasMore=false. The frontend half (sticky _feedCache) is covered by
frontend/src/__tests__/FeedCacheStickiness.test.jsx.
"""
from datetime import datetime, timedelta, timezone

from models import Channel, Item, UserInteraction
from services.recommendation import build_feed, get_trending_items


def _seed_catalog(db, n_items=40, n_interacted=5):
    """n_interacted items that are ALSO the most recent — the worst case
    for the trending backfill (deterministic overlap)."""
    now = datetime.now(timezone.utc)
    ch = Channel(username="feed_reg_ch", title="reg", registered_by=888)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    items = []
    for i in range(n_items):
        it = Item(
            channel_id=ch.id, title=f"reg item {i}",
            category="Mobile Phones", subcategory="Android Phones",
            price=100.0 + i, status="active", is_active=True,
            image_path=f"r{i}.jpg",
            created_at=now - timedelta(minutes=i),
        )
        db.add(it)
        items.append(it)
    db.commit()
    for it in items:
        db.refresh(it)
    for i, it in enumerate(items[:n_interacted]):
        db.add(UserInteraction(
            session_id="feed-reg-session", item_id=it.id,
            interaction_type="view", created_at=now - timedelta(minutes=5 * i),
        ))
    db.commit()
    return items


class TestTrendingBackfillUnderfill:
    def test_trending_returns_full_page_when_interacted_items_are_recent(self, db_session):
        _seed_catalog(db_session)
        feed = get_trending_items(db_session, 20, set())
        assert len(feed) == 20  # pre-fix: 15 (backfill skips 5 without extending)

    def test_cold_start_feed_returns_full_first_page(self, db_session):
        _seed_catalog(db_session)
        page1 = build_feed(db_session, limit=20, offset=0)
        assert len(page1) == 20  # pre-fix: 15 -> hasMore=false after one scroll

    def test_pages_are_full_and_disjoint(self, db_session):
        _seed_catalog(db_session)
        page1 = build_feed(db_session, limit=20, offset=0)
        page2 = build_feed(
            db_session, limit=20, offset=20,
            exclude_ids_str=",".join(str(i.id) for i in page1),
        )
        assert len(page2) == 20
        assert {i.id for i in page1}.isdisjoint({i.id for i in page2})

    def test_exhaustion_returns_empty(self, db_session):
        items = _seed_catalog(db_session)
        all_ids = ",".join(str(i.id) for i in items)
        out = build_feed(db_session, limit=20, offset=0, exclude_ids_str=all_ids)
        assert out == []

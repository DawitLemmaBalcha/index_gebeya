"""
Route tests for GET /items/browse (browse-seam blueprint §2.3).

Server-side category browse: unauthenticated (read-route convention),
`category` required else 400, `{items, total}` shape, boosted items pinned
first with `is_boosted: true`, sold/soft-deleted absent, limit/offset
respected. TestClient pattern mirrors TestBoostQuoteRoute (test_boost.py).
"""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from models import User, Channel, Item, Boost
from api.routes import items as items_router


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


class TestBrowseRoute:
    def _client(self, db_session):
        app = FastAPI()
        app.include_router(items_router.router, prefix="/items", tags=["Items"])

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def _browse(self, db_session, **params):
        return self._client(db_session).get("/items/browse", params=params)

    # -- category required (Deviation 3: Optional param + explicit 400) ----

    def test_browse_missing_category_returns_400(self, db_session):
        resp = self._browse(db_session)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "category is required"

    def test_browse_blank_category_returns_400(self, db_session):
        for blank in ("", "   ", "\t"):
            resp = self._browse(db_session, category=blank)
            assert resp.status_code == 400, repr(blank)

    # -- happy path ----------------------------------------------------------

    def test_browse_returns_items_and_total_shape(self, db_session):
        _, _, item_a = _make_seller_item(db_session, telegram_id=111, title="Alpha")
        _, _, item_b = _make_seller_item(db_session, telegram_id=112, title="Beta")
        client = self._client(db_session)

        resp = client.get("/items/browse", params={"category": "Mobile Phones"})

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert set(data.keys()) == {"items", "total"}
        assert data["total"] == 2
        assert {i["id"] for i in data["items"]} == {item_a.id, item_b.id}

    def test_browse_boosted_item_first_with_flag(self, db_session):
        user, _, boosted = _make_seller_item(db_session, telegram_id=111,
                                             title="Boosted Phone")
        _, _, organic = _make_seller_item(db_session, telegram_id=112,
                                          title="Organic Phone")
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=boosted.id, channel_id=boosted.channel_id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_browse_pin",
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=6),
        ))
        db_session.commit()

        resp = self._browse(db_session, category="Mobile Phones")

        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert items[0]["id"] == boosted.id
        assert items[0]["is_boosted"] is True
        assert items[1]["id"] == organic.id
        assert items[1]["is_boosted"] is False
        # Rule 3.4: no duplicates on the page
        assert [i["id"] for i in items].count(boosted.id) == 1

    def test_browse_sold_and_soft_deleted_absent(self, db_session):
        _, _, active = _make_seller_item(db_session, telegram_id=111, title="Active")
        _, _, sold = _make_seller_item(db_session, telegram_id=112,
                                       title="Sold", status="sold")
        _, _, deleted = _make_seller_item(db_session, telegram_id=113,
                                          title="Deleted", is_active=False)

        resp = self._browse(db_session, category="Mobile Phones")

        data = resp.json()
        assert {i["id"] for i in data["items"]} == {active.id}
        assert data["total"] == 1

    def test_browse_limit_offset_respected(self, db_session):
        for i in range(5):
            _make_seller_item(db_session, telegram_id=200 + i, title=f"Item {i}")

        page1 = self._browse(db_session, category="Mobile Phones", limit=2, offset=0)
        page2 = self._browse(db_session, category="Mobile Phones", limit=2, offset=2)

        assert page1.status_code == page2.status_code == 200
        ids1 = [i["id"] for i in page1.json()["items"]]
        ids2 = [i["id"] for i in page2.json()["items"]]
        assert len(ids1) == 2 and len(ids2) == 2
        assert not (set(ids1) & set(ids2))
        assert page2.json()["total"] == 5

    def test_browse_unauthenticated_ok(self, db_session):
        # Read-route convention: no init_data, no auth header required.
        _, _, item = _make_seller_item(db_session, telegram_id=111, title="Public")
        resp = self._browse(db_session, category="Mobile Phones")
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["id"] == item.id

    def test_browse_strips_whitespace_category(self, db_session):
        _, _, item = _make_seller_item(db_session, telegram_id=111,
                                       title="Trimmed", category="Shoes")
        resp = self._browse(db_session, category="  Shoes  ")
        assert resp.status_code == 200, resp.text
        assert {i["id"] for i in resp.json()["items"]} == {item.id}

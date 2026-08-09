"""
NB-17 + NB-19: item `condition`/`location` persistence + gallery consistency.

- Ingestion persists condition/location from the extraction payload
  (missing keys → NULL, graceful path).
- ItemResponse serializes both fields.
- The search surface (services/search.py `_execute_search_sql`) carries
  condition/location AND the FULL gallery (ItemImage rows), falling back to
  the legacy single `image_path` thumbnail when no ItemImage rows exist.
- Gallery consistency parametrized over the item-bearing routes
  (recent / browse / {id} / search).

House patterns: `db_session` fixture from conftest; TestClient override
pattern from test_items_browse.py / test_payments_flow.py; ingestion route
driven in-process with patched `extract_product_info` + `process_new_item`
(the live-API test_ingestion_dedup.py pattern adapted to the isolated DB).
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from models import Item, ItemImage, Channel, User
from schemas import ItemResponse

TEST_VEC = [0.1] * 512


def _seed_item(db, *, condition=None, location=None,
               image_path="thumb.jpg", gallery=(), title="iPhone 13 Pro"):
    """Seller user + channel + item (active, vectorized). Returns the item."""
    user = User(telegram_id=999001, username="u_cond")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username="ch_cond_loc", title="Test Channel", registered_by=999001)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id,
        title=title,
        description="Selling my phone",
        price=100.0,
        category="Mobile Phones",
        status="active",
        is_active=True,
        image_path=image_path,
        image_vector=TEST_VEC,
        condition=condition,
        location=location,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    for path in gallery:
        db.add(ItemImage(item_id=item.id, image_path=path))
    db.commit()
    return item


# ---------------------------------------------------------------------------
# 1. Ingestion persists condition/location (incl. missing-key NULL path)
# ---------------------------------------------------------------------------

class TestIngestionPersistsConditionLocation:
    def _ingest(self, db_session, extraction_data, post_extra=None):
        from api.routes import ingestion as ingestion_route

        class _FakeTelegramResponse:
            status_code = 404

        class _FakeTelegramClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                return _FakeTelegramResponse()

        body = {
            "channel_name": "ch_cond_loc",
            "message_id": 424242,
            "text": "iPhone 13 Pro for sale 128GB",
        }
        if post_extra:
            body.update(post_extra)

        with patch.object(ingestion_route, "extract_product_info",
                          return_value=extraction_data), \
             patch.object(ingestion_route, "process_new_item",
                          return_value=None), \
             patch.object(ingestion_route.httpx, "AsyncClient",
                          _FakeTelegramClient):
            app = FastAPI()
            app.include_router(ingestion_route.router, tags=["ingestion"])

            def _override_db():
                yield db_session

            app.dependency_overrides[get_db] = _override_db
            client = TestClient(app)
            return client.post("/parse-telegram-post", json=body)

    def test_ingestion_persists_condition_and_location(self, db_session):
        resp = self._ingest(db_session, {
            "title": "iPhone 13 Pro",
            "price": 100,
            "currency": "ETB",
            "category": "Mobile Phones",
            "subcategory": "Smartphones",
            "item_metadata": {"storage": "128GB"},
            "condition": "Used",
            "location": "Addis Ababa, Bole",
        })

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "success", data
        item = db_session.get(Item, data["item_id"])
        assert item is not None
        assert item.condition == "Used"
        assert item.location == "Addis Ababa, Bole"

    def test_ingestion_without_keys_leaves_both_null(self, db_session):
        resp = self._ingest(db_session, {
            "title": "iPhone 13 Pro",
            "price": 100,
            "currency": "ETB",
            "category": "Mobile Phones",
            "subcategory": "Smartphones",
            "item_metadata": {"storage": "128GB"},
        })

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "success", data
        item = db_session.get(Item, data["item_id"])
        assert item.condition is None
        assert item.location is None


# ---------------------------------------------------------------------------
# 2. ItemResponse serializes condition/location
# ---------------------------------------------------------------------------

class TestItemResponseSerialization:
    def test_model_validate_carries_both_fields(self, db_session):
        item = _seed_item(db_session, condition="New", location="Bole")
        resp = ItemResponse.model_validate(item)
        assert resp.condition == "New"
        assert resp.location == "Bole"

    def test_model_validate_nulls_when_absent(self, db_session):
        item = _seed_item(db_session)
        resp = ItemResponse.model_validate(item)
        assert resp.condition is None
        assert resp.location is None


# ---------------------------------------------------------------------------
# 3. Search surface: condition/location + full gallery (NB-17 fix)
# ---------------------------------------------------------------------------

class TestSearchSurface:
    def test_search_carries_condition_location_and_full_gallery(self, db_session):
        from services.search import perform_hybrid_search

        item = _seed_item(db_session, condition="Used", location="Addis Ababa, Bole",
                          image_path="thumb.jpg", gallery=["g1.jpg", "g2.jpg"])

        items, _ = perform_hybrid_search(db_session, "iphone", limit=10)
        found = next(i for i in items if i.id == item.id)
        assert found.condition == "Used"
        assert found.location == "Addis Ababa, Bole"
        assert found.images == ["g1.jpg", "g2.jpg"]

    def test_search_legacy_item_falls_back_to_single_image_path(self, db_session):
        from services.search import perform_hybrid_search

        item = _seed_item(db_session, image_path="legacy.jpg", gallery=())

        items, _ = perform_hybrid_search(db_session, "iphone", limit=10)
        found = next(i for i in items if i.id == item.id)
        assert found.images == ["legacy.jpg"]
        assert found.condition is None
        assert found.location is None


# ---------------------------------------------------------------------------
# 4. Gallery consistency parametrized over item-bearing routes
# ---------------------------------------------------------------------------

class TestGalleryConsistencyAcrossRoutes:
    def _client(self, db_session):
        from api.routes import items as items_router
        from api.routes import search as search_router

        app = FastAPI()
        app.include_router(items_router.router, prefix="/items", tags=["Items"])
        app.include_router(search_router.router, prefix="/search", tags=["Search"])

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    @pytest.mark.parametrize("which", ["recent", "browse", "by_id", "search"])
    def test_every_item_bearing_route_returns_full_gallery(self, db_session, which):
        item = _seed_item(db_session, gallery=["g1.jpg", "g2.jpg"])
        client = self._client(db_session)

        if which == "recent":
            resp = client.get("/items/recent")
            data = resp.json()
        elif which == "browse":
            resp = client.get("/items/browse", params={"category": "Mobile Phones"})
            data = resp.json()["items"]
        elif which == "by_id":
            resp = client.get(f"/items/{item.id}")
            data = [resp.json()]
        else:  # search — POST body per the SearchQuery seam
            resp = client.post("/search/", json={"query": "", "limit": 10})
            data = resp.json()["items"]

        assert resp.status_code == 200, (which, resp.text)
        assert [i["id"] for i in data] == [item.id]
        for i in data:
            assert i["images"] == ["g1.jpg", "g2.jpg"], which

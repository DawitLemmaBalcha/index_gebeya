"""
NB-55: the Quality Events surface (ops_finalize) + the internal item fetch
seam the owner DM depends on.

Covers:
  - GET /ops/quality/events — joined title/username, ordering (timestamp
    DESC, id DESC), full per-row shape.
  - POST /ops/quality/events/{id}/revert — per-field restore semantics
    (price float, specs canonical JSON, verbatim strings, NULL restore),
    the revert-is-itself-an-event rule, the console-admin sentinel
    (telegram_id=-1), the audit row, the 400/404 error modes, and the
    re-trigger of alert matching on price/specs/category/subcategory.
  - GET /internal/items/{item_id} — header gate, shape with gallery, 404.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from ai_engine.vector_client import vectorize_text
from database import get_db
from models import Alert, AuditLog, Channel, Item, ItemEdit, ItemImage, Notification, User

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _ops_client(db_session):
    from api.routes import ops_auth, ops_finalize

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_finalize.router, prefix="/ops")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    resp = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert resp.status_code == 200
    return client


def _owned_item(db, *, owner_tg=101, price=100.0, category="Mobile Phones", specs=None):
    user = User(telegram_id=owner_tg, username=f"owner{owner_tg}")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username=f"ch_owner{owner_tg}", title="C", registered_by=owner_tg)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id,
        title="iPhone 13 128GB",
        category=category,
        subcategory="Android Phones",
        status="active",
        is_active=True,
        price=price,
        specs=specs or '{"brand": "Apple", "model": "iPhone 13"}',
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


def _log_edit(db, item, user, field, old_value, new_value):
    edit = ItemEdit(
        item_id=item.id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        edited_by=user.id,
    )
    db.add(edit)
    db.commit()
    db.refresh(edit)
    return edit


class TestQualityEventsList:
    def test_events_shape_and_ordering(self, db_session):
        user, channel, item = _owned_item(db_session)
        edit_a = _log_edit(db_session, item, user, "price", "100.0", "250.0")
        edit_b = _log_edit(db_session, item, user, "category", "Mobile Phones", "Vehicles")
        client = _ops_client(db_session)

        resp = client.get("/ops/quality/events")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert [r["id"] for r in rows] == [edit_b.id, edit_a.id]

        first = rows[0]
        assert first["item_id"] == item.id
        assert first["title"] == "iPhone 13 128GB"
        assert first["field"] == "category"
        assert first["old_value"] == "Mobile Phones"
        assert first["new_value"] == "Vehicles"
        assert first["edited_by"] == user.id
        assert first["edited_by_username"] == "owner101"
        assert "timestamp" in first

    def test_events_limit_offset(self, db_session):
        user, channel, item = _owned_item(db_session)
        for i in range(3):
            _log_edit(db_session, item, user, "title", f"t{i}", f"t{i+1}")
        client = _ops_client(db_session)
        resp = client.get("/ops/quality/events", params={"limit": 2, "offset": 1})
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 2


class TestRevert:
    def test_revert_price_restores_float_and_writes_new_event_and_audit(self, db_session):
        user, channel, item = _owned_item(db_session, price=250.0)  # post-edit state
        edit = _log_edit(db_session, item, user, "price", "50.0", "250.0")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/quality/events/{edit.id}/revert")
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        restored = db_session.get(Item, item.id)
        assert restored.price == 50.0

        # Revert is itself an edit event (Rule 2.1), authored by the
        # reserved console-admin sentinel (telegram_id=-1).
        events = db_session.scalars(select(ItemEdit).order_by(ItemEdit.id)).all()
        assert len(events) == 2
        new_event = events[-1]
        assert new_event.field == "price"
        assert new_event.old_value == "250.0"
        assert new_event.new_value == "50.0"
        sentinel = db_session.scalar(select(User).where(User.telegram_id == -1))
        assert sentinel is not None
        assert new_event.edited_by == sentinel.id

        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "revert_item_edit")
        )
        assert audit is not None
        assert audit.section == "quality"
        assert audit.entity_type == "item_edit"
        assert audit.entity_id == str(edit.id)

    def test_revert_specs_stores_canonical_json(self, db_session):
        user, channel, item = _owned_item(db_session, specs='{"brand": "Apple"}')
        edit = _log_edit(db_session, item, user, "specs", '{"brand": "Nokia"}', '{"brand": "Apple"}')
        client = _ops_client(db_session)

        resp = client.post(f"/ops/quality/events/{edit.id}/revert")
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        restored = db_session.get(Item, item.id)
        assert json.loads(restored.specs) == {"brand": "Nokia"}
        assert restored.specs == '{"brand": "Nokia"}'

    def test_revert_category_verbatim_and_retriggers_matching(self, db_session):
        user, channel, item = _owned_item(db_session)
        # Seeded matching alert: speed-pass BULLSEYE against the item title.
        alert = Alert(
            user_id=user.id,
            query_text="iphone13",
            query_vector=vectorize_text("iphone13"),
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db_session.add(alert)
        db_session.commit()

        edit = _log_edit(db_session, item, user, "category", "Vehicles", "Mobile Phones")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/quality/events/{edit.id}/revert")
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        restored = db_session.get(Item, item.id)
        assert restored.category == "Vehicles"
        notif = db_session.scalar(select(Notification))
        assert notif is not None, "revert of category must re-trigger matching"
        assert notif.alert_id == alert.id
        assert notif.item_id == item.id

    def test_revert_null_old_value_restores_null(self, db_session):
        user, channel, item = _owned_item(db_session)
        edit = _log_edit(db_session, item, user, "category", None, "Mobile Phones")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/quality/events/{edit.id}/revert")
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert db_session.get(Item, item.id).category is None

    def test_revert_unrevertible_field_400(self, db_session):
        user, channel, item = _owned_item(db_session)
        edit = _log_edit(db_session, item, user, "phone_number", "0911", "0912")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/quality/events/{edit.id}/revert")
        assert resp.status_code == 400
        assert "not revertible" in resp.json()["detail"]

    def test_revert_unparseable_price_400(self, db_session):
        user, channel, item = _owned_item(db_session)
        edit = _log_edit(db_session, item, user, "price", "not-a-number", "250.0")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/quality/events/{edit.id}/revert")
        assert resp.status_code == 400

    def test_revert_unknown_event_404(self, db_session):
        client = _ops_client(db_session)
        resp = client.post("/ops/quality/events/99999/revert")
        assert resp.status_code == 404


class TestInternalItemFetch:
    def _internal_client(self, db_session):
        from api.routes import internal as internal_router

        app = FastAPI()
        app.include_router(internal_router.router)

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def test_internal_item_requires_internal_header(self, db_session):
        user, channel, item = _owned_item(db_session)
        client = self._internal_client(db_session)
        resp = client.get(f"/internal/items/{item.id}")
        assert resp.status_code == 403

    def test_internal_item_shape_with_gallery(self, db_session):
        user, channel, item = _owned_item(db_session)
        db_session.add(ItemImage(item_id=item.id, image_path="g1.jpg"))
        db_session.add(ItemImage(item_id=item.id, image_path="g2.jpg"))
        db_session.commit()
        client = self._internal_client(db_session)

        resp = client.get(
            f"/internal/items/{item.id}",
            headers={"X-Internal-Service": "index-listener"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == item.id
        assert data["title"] == "iPhone 13 128GB"
        assert data["price"] == 100.0
        assert data["currency"] == "ETB"
        assert data["category"] == "Mobile Phones"
        assert data["subcategory"] == "Android Phones"
        assert data["images"] == ["g1.jpg", "g2.jpg"]
        assert data["specs"] == '{"brand": "Apple", "model": "iPhone 13"}'

    def test_internal_item_404(self, db_session):
        client = self._internal_client(db_session)
        resp = client.get(
            "/internal/items/99999",
            headers={"X-Internal-Service": "index-listener"},
        )
        assert resp.status_code == 404

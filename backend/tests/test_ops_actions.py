"""
NB-59: engine actions — re-run, retry, trigger (blueprint §5, §5.5).

Every action: require_ops_admin, audit row, result feedback. The radar
references the retry verb through this shared registry (§5.2 — one endpoint
per verb, never duplicated).

Covers: reprocess invokes process_new_item (spy) and runs twice safely;
retry flips FAILED→PENDING with an audit row and 409s on PENDING/terminal
statuses; reconcile invokes reconcile_star_payments (async spy) and records
the scheduler run; audit rows written for every action.
"""
import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from models import AuditLog, Channel, Item, Notification, SchedulerRun, User

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _user(db, telegram_id=111):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", banned=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _channel(db, username="ch_actions"):
    channel = Channel(
        username=username, title=username, registered_by=None,
        trust_score=0.0, indexing_paused=False, is_active=True,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _item(db, channel, *, title="iPhone 13", price=100.0):
    item = Item(
        channel_id=channel.id, title=title, price=price,
        category="Mobile Phones", subcategory="General", status="active",
        is_active=True, image_path="x.jpg", specs="{}",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _notification(db, user, status="FAILED"):
    notif = Notification(
        user_id=user.id, item_id=None, alert_id=None,
        match_tier="bullseye", match_score=1.0, status=status,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


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


def _audit_rows(db, action):
    return db.scalars(
        select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
    ).all()


class TestReprocess:
    def test_invokes_process_new_item_and_audits(self, db_session, monkeypatch):
        from api.routes import ops_finalize

        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        calls = []
        monkeypatch.setattr(ops_finalize, "process_new_item",
                            lambda db, item_id: calls.append(item_id))
        client = _ops_client(db_session)

        resp = client.post(f"/ops/actions/items/{item.id}/reprocess")
        assert resp.status_code == 200, resp.text
        assert calls == [item.id]
        audit = _audit_rows(db_session, "reprocess_item")
        assert len(audit) == 1
        assert audit[0].section == "alerts"
        assert audit[0].entity_id == str(item.id)

    def test_runs_twice_safely(self, db_session, monkeypatch):
        from api.routes import ops_finalize

        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        calls = []
        monkeypatch.setattr(ops_finalize, "process_new_item",
                            lambda db, item_id: calls.append(item_id))
        client = _ops_client(db_session)

        for _ in range(2):
            resp = client.post(f"/ops/actions/items/{item.id}/reprocess")
            assert resp.status_code == 200
        # idempotent by design: the pipeline's duplicate suppression and
        # throttle guard re-dispatch (blueprint §5.1) — the verb itself runs
        # the pipeline each time without error.
        assert calls == [item.id, item.id]
        assert len(_audit_rows(db_session, "reprocess_item")) == 2

    def test_404_unknown_item(self, db_session):
        client = _ops_client(db_session)
        resp = client.post("/ops/actions/items/99999/reprocess")
        assert resp.status_code == 404


class TestRetry:
    def test_failed_flips_to_pending_with_audit(self, db_session):
        user = _user(db_session)
        notif = _notification(db_session, user, status="FAILED")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/actions/notifications/{notif.id}/retry")
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(Notification, notif.id).status == "PENDING"
        audit = _audit_rows(db_session, "retry_notification")
        assert len(audit) == 1
        assert audit[0].entity_id == str(notif.id)
        assert audit[0].before == {"status": "FAILED"}
        assert audit[0].after == {"status": "PENDING"}

    def test_409_on_pending_and_terminal(self, db_session):
        user = _user(db_session)
        pending = _notification(db_session, user, status="PENDING")
        sent = _notification(db_session, user, status="SENT")
        replaced = _notification(db_session, user, status="REPLACED")
        client = _ops_client(db_session)

        resp = client.post(f"/ops/actions/notifications/{pending.id}/retry")
        assert resp.status_code == 409
        assert "pending" in resp.json()["detail"].lower()

        resp = client.post(f"/ops/actions/notifications/{sent.id}/retry")
        assert resp.status_code == 409
        assert "terminal" in resp.json()["detail"].lower()

        resp = client.post(f"/ops/actions/notifications/{replaced.id}/retry")
        assert resp.status_code == 409

        # no audit rows were written for the rejected transitions
        assert _audit_rows(db_session, "retry_notification") == []

    def test_404_unknown_notification(self, db_session):
        client = _ops_client(db_session)
        resp = client.post("/ops/actions/notifications/99999/retry")
        assert resp.status_code == 404


class TestReconcile:
    def test_invokes_reconcile_records_run_and_audits(self, db_session, monkeypatch):
        from api.routes import ops_finalize

        calls = {}

        async def _fake_reconcile(db, *, limit=100):
            calls["limit"] = limit
            return {"fetched": 2, "replayed_boost": 1, "replayed_subscription": 0,
                    "skipped": 1, "errors": 0}

        recorded = {}
        monkeypatch.setattr(ops_finalize, "reconcile_star_payments", _fake_reconcile)
        monkeypatch.setattr(
            ops_finalize, "record_scheduler_run",
            lambda db, **kw: recorded.update(kw),
        )
        client = _ops_client(db_session)

        resp = client.post("/ops/actions/reconcile")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["summary"]["fetched"] == 2
        assert body["summary"]["replayed_boost"] == 1

        # the run-now scheduler bookkeeping (NB-50 pattern)
        assert recorded["scheduler"] == "reconciliation"
        assert recorded["success"] is True
        assert recorded["result"]["fetched"] == 2

        audit = _audit_rows(db_session, "reconcile_now")
        assert len(audit) == 1
        assert audit[0].section == "payments"

    def test_records_scheduler_run_row(self, db_session, monkeypatch):
        from api.routes import ops_finalize

        async def _fake_reconcile(db, *, limit=100):
            return {"fetched": 0, "replayed_boost": 0, "replayed_subscription": 0,
                    "skipped": 0, "errors": 0}

        monkeypatch.setattr(ops_finalize, "reconcile_star_payments", _fake_reconcile)
        client = _ops_client(db_session)
        resp = client.post("/ops/actions/reconcile")
        assert resp.status_code == 200

        row = db_session.scalar(select(SchedulerRun).where(SchedulerRun.scheduler == "reconciliation"))
        assert row is not None
        assert row.last_run_at is not None
        assert row.last_success_at is not None

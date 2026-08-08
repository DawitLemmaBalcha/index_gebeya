"""
NB-50: the listener heartbeat seam (backend half, blueprint §2.7).

The heartbeat is the ONLY listener signal — no fake data; its absence
means "down/unknown".
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import get_db
from models import ListenerHeartbeat


def _client(db_session):
    from api.routes import internal as internal_router

    app = FastAPI()
    app.include_router(internal_router.router)

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def test_heartbeat_requires_internal_header(db_session):
    client = _client(db_session)
    resp = client.post("/internal/heartbeat", json={"queue_depth": 3})
    assert resp.status_code == 403
    assert db_session.scalar(select(ListenerHeartbeat.id)) is None


def test_heartbeat_wrong_internal_service_rejected(db_session):
    client = _client(db_session)
    resp = client.post(
        "/internal/heartbeat",
        json={"queue_depth": 3},
        headers={"X-Internal-Service": "someone-else"},
    )
    assert resp.status_code == 403


def test_heartbeat_upserts_the_single_row(db_session):
    client = _client(db_session)
    payload = {"queue_depth": 4, "items_processed_total": 12, "started_at": "2026-08-08T00:00:00Z"}
    resp = client.post(
        "/internal/heartbeat",
        json=payload,
        headers={"X-Internal-Service": "index-listener"},
    )
    assert resp.status_code == 200
    row = db_session.get(ListenerHeartbeat, 1)
    assert row is not None
    assert row.payload["queue_depth"] == 4
    assert row.payload["items_processed_total"] == 12
    assert row.last_seen_at is not None

    # second beat updates the SAME row (id fixed 1), payload replaced
    resp = client.post(
        "/internal/heartbeat",
        json={"queue_depth": 1},
        headers={"X-Internal-Service": "index-listener"},
    )
    assert resp.status_code == 200
    rows = db_session.execute(select(ListenerHeartbeat)).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload == {"queue_depth": 1}

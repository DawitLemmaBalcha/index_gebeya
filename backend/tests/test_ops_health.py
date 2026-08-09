"""
NB-50: GET /ops/health — Section 1 Overview (blueprint §2.8).

Per-signal honesty: the endpoint always 200s, failures are per-signal,
sources are never fabricated. Auth gate: 401 without an ops session.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from models import Boost, Channel, Item, ListenerHeartbeat, SchedulerRun, Subscription, User
from tests.fake_telegram_payments import FakeStarPaymentsAdapter

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")

_REQUIRED_SIGNALS = [
    "services.api", "services.db", "services.frontend", "services.listener",
    "bot.connection", "bot.update_lag_seconds", "bot.handler_error_rate",
    "ingestion.queue_depth", "ingestion.items_per_hour",
    "ingestion.rate_limit_headroom", "ingestion.ai_providers",
    "schedulers.cleanup", "schedulers.reconciliation",
    "schedulers.photo_refresher", "money.star_balance", "money.pending_payments",
]


def _client(db_session, monkeypatch, fake=None, probe_result=True):
    from api.routes import ops_auth, ops_health

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware, secret_key="t", session_cookie="ops_session"
    )
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_health.router, prefix="/ops/health")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    if fake is not None:
        monkeypatch.setattr("api.routes.ops_health.star_payments", fake)

    async def _fake_probe() -> bool:
        return probe_result

    monkeypatch.setattr("api.routes.ops_health._probe_frontend", _fake_probe)

    client = TestClient(app)
    login = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert login.status_code == 200
    return client


def _heartbeat(db_session, *, age_seconds=10, payload=None):
    hb = ListenerHeartbeat(
        id=1,
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        payload=payload or {
            "queue_depth": 2,
            "items_processed_total": 60,
            "last_update_at": (
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
            "started_at": (
                datetime.now(timezone.utc) - timedelta(hours=1)
            ).isoformat(),
            "photo_refresher": {
                "last_run_at": "2026-08-08T10:00:00+00:00",
                "last_success_at": "2026-08-08T10:00:00+00:00",
                "last_error": None,
            },
        },
    )
    db_session.add(hb)
    db_session.commit()


def _seller(db_session):
    user = User(telegram_id=111, username="u111")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    channel = Channel(username="ch_111", title="C", registered_by=111)
    db_session.add(channel)
    db_session.commit()
    db_session.refresh(channel)
    item = Item(
        channel_id=channel.id, title="t", category="Mobile Phones",
        status="active", is_active=True, image_path="x.jpg",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return user, channel, item


class TestHealthGate:
    def test_401_without_session(self, db_session, monkeypatch):
        from api.routes import ops_health

        app = FastAPI()
        app.add_middleware(
            SessionMiddleware, secret_key="t", session_cookie="ops_session"
        )
        app.include_router(ops_health.router, prefix="/ops/health")

        def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db
        resp = TestClient(app).get("/ops/health")
        assert resp.status_code == 401


class TestHealthShape:
    def test_has_generated_at_and_all_signals(self, db_session, monkeypatch):
        _heartbeat(db_session)
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        resp = client.get("/ops/health")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "generated_at" in data
        for name in _REQUIRED_SIGNALS:
            assert name in data["services"], f"missing signal {name}"
            assert "status" in data["services"][name]

    def test_sources_are_never_fabricated(self, db_session, monkeypatch):
        # Signals without a data source render unavailable + reason
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        data = client.get("/ops/health").json()["services"]
        assert data["bot.handler_error_rate"]["status"] == "unavailable"
        assert data["ingestion.rate_limit_headroom"]["status"] == "unavailable"
        assert data["ingestion.ai_providers"]["status"] == "unavailable"
        assert "reason" in data["ingestion.ai_providers"] or data["ingestion.ai_providers"].get("note")


class TestListenerSignals:
    def test_listener_up_when_heartbeat_fresh(self, db_session, monkeypatch):
        _heartbeat(db_session, age_seconds=10)
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        services = client.get("/ops/health").json()["services"]
        assert services["services.listener"]["status"] == "up"
        assert services["bot.connection"]["status"] == "up"
        assert services["ingestion.queue_depth"]["value"] == 2
        assert services["ingestion.items_per_hour"]["value"] == 60  # 60 items / 1h

    def test_listener_down_when_heartbeat_stale(self, db_session, monkeypatch):
        _heartbeat(db_session, age_seconds=120)
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        services = client.get("/ops/health").json()["services"]
        assert services["services.listener"]["status"] == "down"
        assert services["bot.connection"]["status"] == "down"

    def test_listener_unknown_when_no_heartbeat_row(self, db_session, monkeypatch):
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        services = client.get("/ops/health").json()["services"]
        assert services["services.listener"]["status"] == "unknown"
        assert services["bot.connection"]["status"] == "unknown"
        assert services["ingestion.queue_depth"]["value"] is None

    def test_photo_refresher_derived_from_heartbeat_payload(self, db_session, monkeypatch):
        _heartbeat(db_session)
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        services = client.get("/ops/health").json()["services"]
        pr = services["schedulers.photo_refresher"]
        assert pr["value"] is not None
        assert pr["value"]["last_success_at"] == "2026-08-08T10:00:00+00:00"


class TestFrontendProbe:
    def test_probe_failure_reports_down(self, db_session, monkeypatch):
        client = _client(db_session, monkeypatch, probe_result=False)
        services = client.get("/ops/health").json()["services"]
        assert services["services.frontend"]["status"] == "down"

    def test_probe_success_reports_up(self, db_session, monkeypatch):
        client = _client(db_session, monkeypatch, probe_result=True)
        services = client.get("/ops/health").json()["services"]
        assert services["services.frontend"]["status"] == "up"


class TestMoneySignals:
    def test_star_balance_from_adapter(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        client = _client(db_session, monkeypatch, fake=fake)
        services = client.get("/ops/health").json()["services"]
        assert services["money.star_balance"]["status"] == "ok"
        assert services["money.star_balance"]["value"] == 0

    def test_star_balance_value_is_int_with_real_adapter(self, db_session, monkeypatch):
        """Regression: the real httpx adapter must expose the star balance as
        an int (Telegram returns {"amount": N}) — the Overview signal value
        must not be a dict."""
        from services.telegram_payments import HttpxStarPaymentsAdapter

        adapter = HttpxStarPaymentsAdapter(bot_token="test")

        async def _fake_get(method, params=None):
            return {"amount": 42}

        monkeypatch.setattr(adapter, "_get", _fake_get)
        client = _client(db_session, monkeypatch, fake=adapter)
        signal = client.get("/ops/health").json()["services"]["money.star_balance"]
        assert signal["status"] == "ok"
        assert signal["value"] == 42
        assert isinstance(signal["value"], int)

    def test_pending_payments_unwraps_wrapped_transactions(self, db_session, monkeypatch):
        """Regression: getStarTransactions returns {"transactions": [...]};
        the health signal must see the list, not an empty ledger."""
        from services.telegram_payments import HttpxStarPaymentsAdapter

        adapter = HttpxStarPaymentsAdapter(bot_token="test")

        async def _fake_get(method, params=None):
            return {
                "transactions": [
                    {"id": "chg_wrap_1", "date": 1750000000,
                     "amount": {"amount": 150, "nanostar_amount": 0},
                     "source": {"transaction_type": "invoice_payment"}},
                ],
                "transactions_count": 1,
            }

        monkeypatch.setattr(adapter, "_get", _fake_get)
        client = _client(db_session, monkeypatch, fake=adapter)
        signal = client.get("/ops/health").json()["services"]["money.pending_payments"]
        assert signal["status"] == "ok"
        assert signal["value"]["count"] == 1

    def test_star_balance_error_is_signal_level(self, db_session, monkeypatch):
        class _BrokenAdapter(FakeStarPaymentsAdapter):
            async def get_my_star_balance(self):
                raise RuntimeError("Telegram API error: boom")

        client = _client(db_session, monkeypatch, fake=_BrokenAdapter())
        resp = client.get("/ops/health")
        assert resp.status_code == 200  # never a 500 for one signal
        services = resp.json()["services"]
        assert services["money.star_balance"]["status"] == "error"

    def test_pending_payments_counts_unfulfilled_transactions(self, db_session, monkeypatch):
        user, channel, item = _seller(db_session)
        now = datetime.now(timezone.utc)
        db_session.add(Boost(
            item_id=item.id, channel_id=channel.id, user_id=user.id,
            source="paid", price_paid_stars=150,
            telegram_payment_charge_id="chg_fulfilled_boost",
            starts_at=now, ends_at=now + timedelta(days=7),
        ))
        db_session.add(Subscription(
            user_id=user.id, product="alerts_only", status="active",
            telegram_payment_charge_id="chg_fulfilled_sub",
            invoice_payload=f"s:{user.id}:alerts_only:abc",
            current_period_start=now, current_period_end=now + timedelta(days=30),
        ))
        db_session.commit()

        fake = FakeStarPaymentsAdapter()
        fake.ledger = [
            {"id": "chg_fulfilled_boost", "amount": -150, "date": 1750000000,
             "source": {"transaction_type": "invoice_payment"}},
            {"id": "chg_unfulfilled", "amount": -150, "date": 1750000000,
             "source": {"transaction_type": "invoice_payment"}},
            {"id": "chg_outgoing", "amount": 30, "date": 1750000000,
             "source": {"transaction_type": "invoice_send"}},
        ]
        client = _client(db_session, monkeypatch, fake=fake)
        services = client.get("/ops/health").json()["services"]
        pending = services["money.pending_payments"]
        assert pending["status"] == "ok"
        assert pending["value"]["count"] == 1  # only the unfulfilled invoice_payment


class TestSchedulerSignals:
    def test_cleanup_row_written_by_instrumented_path(self, db_session, monkeypatch):
        from services.cleanup import run_cleanup_and_log

        run_cleanup_and_log()
        row = db_session.scalar(
            select(SchedulerRun).where(SchedulerRun.scheduler == "cleanup")
        )
        assert row is not None
        assert row.last_success_at is not None
        assert row.last_result is not None

    def test_reconciliation_row_written_by_scheduler_closure(self, db_session, monkeypatch):
        from main import _schedule_reconcile

        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("services.reconciliation.star_payments", fake)

        class _NoopTimer:
            def start(self):
                pass

        monkeypatch.setattr("main.threading.Timer", lambda *a, **k: _NoopTimer())

        _schedule_reconcile()
        row = db_session.scalar(
            select(SchedulerRun).where(SchedulerRun.scheduler == "reconciliation")
        )
        assert row is not None
        assert row.last_success_at is not None
        assert row.last_result is not None

    def test_never_run_schedulers_report_honestly(self, db_session, monkeypatch):
        client = _client(db_session, monkeypatch, fake=FakeStarPaymentsAdapter())
        services = client.get("/ops/health").json()["services"]
        assert services["schedulers.cleanup"]["status"] == "never run"
        assert services["schedulers.reconciliation"]["status"] == "never run"

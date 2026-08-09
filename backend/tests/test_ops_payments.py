"""
NB-53: ops console Section 7 — Payments (blueprint §2.11).

Ledger, balance, reconciliation run-now (drives the REAL reconcile path),
refunds via the adapter (recorded + audited).
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from database import get_db
from models import AuditLog, Channel, Item, SchedulerRun, User
from services.reconciliation import reconcile_star_payments
from tests.fake_telegram_payments import FakeStarPaymentsAdapter

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _payments_client(db_session):
    from api.routes import ops_auth, ops_payments

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_payments.router, prefix="/ops/payments")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    login = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert login.status_code == 200
    return client


def _tx(charge_id, *, amount=150, payload="b:1:abc", user_id=111, date=None):
    return {
        "id": charge_id,
        "amount": amount,
        "date": int((date or datetime.now(timezone.utc)).timestamp()),
        "source": {
            "type": "user",
            "transaction_type": "invoice_payment",
            "user": {"id": user_id},
            "invoice_payload": payload,
        },
    }


def _seller(db):
    user = User(telegram_id=111, username="u111")
    db.add(user)
    db.commit()
    db.refresh(user)
    channel = Channel(username="ch_p", title="C", registered_by=111)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    item = Item(
        channel_id=channel.id, title="iPhone", category="Mobile Phones",
        status="active", is_active=True, image_path="x.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return user, channel, item


class TestLedgerAndBalance:
    def test_ledger_flattens_transactions(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        fake.ledger = [
            _tx("chg_led_1", amount=150, payload="b:7:nonce"),
            _tx("chg_led_2", amount=100, payload="s:9:alerts_only:nonce"),
        ]
        monkeypatch.setattr("api.routes.ops_payments.star_payments", fake)
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/ledger")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 2
        assert rows[0]["id"] == "chg_led_1"
        assert rows[0]["amount"] == 150
        assert rows[0]["transaction_type"] == "invoice_payment"
        assert rows[0]["payload_prefix"] == "b:"
        assert rows[0]["user_id"] == 111

    def test_balance(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("api.routes.ops_payments.star_payments", fake)
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/balance")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"balance_stars": 0}

    def test_ledger_error_502(self, db_session, monkeypatch):
        class _Broken(FakeStarPaymentsAdapter):
            async def get_star_transactions(self, *, offset=0, limit=100):
                raise RuntimeError("Telegram API error: boom")

        monkeypatch.setattr("api.routes.ops_payments.star_payments", _Broken())
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/ledger")
        assert resp.status_code == 502


class TestReconciliation:
    def test_run_now_drives_real_reconcile_and_records(self, db_session, monkeypatch):
        user, channel, item = _seller(db_session)
        fake = FakeStarPaymentsAdapter()
        fake.ledger = [_tx("chg_run_1", payload=f"b:{item.id}:nonce")]
        monkeypatch.setattr("services.reconciliation.star_payments", fake)

        client = _payments_client(db_session)
        resp = client.post("/ops/payments/reconciliation/run")
        assert resp.status_code == 200, resp.text
        summary = resp.json()
        assert summary["replayed_boost"] == 1

        # the boost was actually created by the REAL reconcile path
        from models import Boost
        boost = db_session.scalar(select(Boost).where(Boost.telegram_payment_charge_id == "chg_run_1"))
        assert boost is not None

        # scheduler_runs row with the summary in last_result
        row = db_session.scalar(
            select(SchedulerRun).where(SchedulerRun.scheduler == "reconciliation")
        )
        assert row is not None
        assert row.last_success_at is not None
        assert row.last_result["replayed_boost"] == 1

        # audit row
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "run_reconciliation")
        )
        assert audit is not None
        assert audit.section == "payments"
        assert audit.entity_type == "scheduler"

    def test_reconciliation_status_never_run(self, db_session):
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/reconciliation")
        assert resp.status_code == 200
        assert resp.json()["status"] == "never run"

    def test_reconciliation_status_shows_row(self, db_session):
        from services.scheduler_runs import record_scheduler_run
        record_scheduler_run(
            db_session, scheduler="reconciliation", success=True,
            result={"fetched": 1, "replayed_boost": 1},
        )
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/reconciliation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["last_result"]["replayed_boost"] == 1


class TestRefund:
    def test_refund_calls_adapter_and_audits(self, db_session, monkeypatch):
        fake = FakeStarPaymentsAdapter()
        monkeypatch.setattr("api.routes.ops_payments.star_payments", fake)
        client = _payments_client(db_session)

        resp = client.post(
            "/ops/payments/refund",
            json={"telegram_payment_charge_id": "chg_refund_1"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["result"] is True

        # the adapter was called with the charge id
        assert any(
            c["method"] == "refund_star_payment"
            and c["telegram_payment_charge_id"] == "chg_refund_1"
            for c in fake.calls
        )

        # audit row
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "refund_star_payment")
        )
        assert audit is not None
        assert audit.entity_type == "payment"
        assert audit.entity_id == "chg_refund_1"
        assert audit.after == {"result": True}

    def test_refund_missing_charge_id_400(self, db_session):
        client = _payments_client(db_session)
        resp = client.post("/ops/payments/refund", json={"telegram_payment_charge_id": ""})
        assert resp.status_code == 400


class TestHttpxAdapterContract:
    """Regression (ops-console white screen, React #31): the real
    HttpxStarPaymentsAdapter must honor the StarPaymentsAdapter Protocol
    return SHAPES. Telegram's raw API returns `{"amount": N}` for
    getMyStarBalance and `{"transactions": [...], "transactions_count": N}`
    for getStarTransactions — the adapter must unwrap to int / List[dict]
    with int `amount` (a dict rendered as a JSX child crashes the console)."""

    @staticmethod
    def _adapter(monkeypatch, responses):
        from services.telegram_payments import HttpxStarPaymentsAdapter

        adapter = HttpxStarPaymentsAdapter(bot_token="test")

        async def _fake_get(method, params=None):
            return responses[method]

        monkeypatch.setattr(adapter, "_get", _fake_get)
        return adapter

    def test_get_my_star_balance_returns_int_from_result_dict(self, monkeypatch):
        adapter = self._adapter(monkeypatch, {"getMyStarBalance": {"amount": 42}})
        balance = asyncio.run(adapter.get_my_star_balance())
        assert isinstance(balance, int)
        assert balance == 42

    def test_get_my_star_balance_passes_through_int_result(self, monkeypatch):
        adapter = self._adapter(monkeypatch, {"getMyStarBalance": 7})
        assert asyncio.run(adapter.get_my_star_balance()) == 7

    def test_get_my_star_balance_missing_amount_returns_zero(self, monkeypatch):
        adapter = self._adapter(monkeypatch, {"getMyStarBalance": {}})
        assert asyncio.run(adapter.get_my_star_balance()) == 0

    def test_get_star_transactions_unwraps_result_and_normalizes_amounts(self, monkeypatch):
        adapter = self._adapter(monkeypatch, {
            "getStarTransactions": {
                "transactions": [
                    {"id": "chg_t1", "date": 1750000000,
                     "amount": {"amount": 150, "nanostar_amount": 0},
                     "source": {"transaction_type": "invoice_payment"}},
                    {"id": "chg_t2", "date": 1750000001, "amount": 30,
                     "source": {"transaction_type": "invoice_send"}},
                ],
                "transactions_count": 2,
            }
        })
        txs = asyncio.run(adapter.get_star_transactions(limit=100))
        assert isinstance(txs, list)  # not the {"transactions": [...]} wrapper
        assert txs[0]["amount"] == 150
        assert isinstance(txs[0]["amount"], int)
        assert txs[1]["amount"] == 30

    def test_get_star_transactions_empty_result_returns_empty_list(self, monkeypatch):
        adapter = self._adapter(monkeypatch, {"getStarTransactions": {}})
        assert asyncio.run(adapter.get_star_transactions()) == []


class TestHttpxAdapterThroughRoutes:
    """The full real-bug chain: the REAL httpx adapter (not the fake) mounted
    in the routes, fed Telegram-shaped API responses. This is the seam that
    crashed the ops console after login."""

    @staticmethod
    def _install_real_adapter(monkeypatch, responses, module="api.routes.ops_payments"):
        from services.telegram_payments import HttpxStarPaymentsAdapter

        adapter = HttpxStarPaymentsAdapter(bot_token="test")

        async def _fake_get(method, params=None):
            return responses[method]

        monkeypatch.setattr(adapter, "_get", _fake_get)
        monkeypatch.setattr(f"{module}.star_payments", adapter)
        return adapter

    def test_balance_route_returns_int_with_real_adapter(self, db_session, monkeypatch):
        self._install_real_adapter(monkeypatch, {"getMyStarBalance": {"amount": 42}})
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/balance")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"balance_stars": 42}
        assert isinstance(body["balance_stars"], int)

    def test_ledger_route_unwraps_and_normalizes_with_real_adapter(self, db_session, monkeypatch):
        self._install_real_adapter(monkeypatch, {
            "getStarTransactions": {
                "transactions": [
                    {"id": "chg_rt_1", "date": 1750000000,
                     "amount": {"amount": 150, "nanostar_amount": 0},
                     "source": {"type": "user", "transaction_type": "invoice_payment",
                                "user": {"id": 111}, "invoice_payload": "b:7:nonce"}},
                ],
                "transactions_count": 1,
            }
        })
        client = _payments_client(db_session)
        resp = client.get("/ops/payments/ledger")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1  # NOT silently emptied by the isinstance list guard
        assert rows[0]["amount"] == 150
        assert isinstance(rows[0]["amount"], int)


class TestAdapterMethodPresence:
    """D4: refund_star_payment on the Protocol, the httpx adapter and the
    fake (needed by Phase 1, asserted here at the port level)."""

    def test_protocol_and_httpx_adapter_have_refund(self):
        from services.telegram_payments import HttpxStarPaymentsAdapter, StarPaymentsAdapter

        assert hasattr(StarPaymentsAdapter, "refund_star_payment")
        assert callable(getattr(HttpxStarPaymentsAdapter, "refund_star_payment"))

    def test_fake_has_refund(self):
        assert hasattr(FakeStarPaymentsAdapter, "refund_star_payment")

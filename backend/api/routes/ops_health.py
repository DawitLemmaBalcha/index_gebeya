"""
NB-50: GET /ops/health — Section 1 Overview data (blueprint §2.8).

Always 200; per-signal statuses inside. Honest sources only: every signal
carries {status, value?, source, note?} and the response carries
generated_at for the frontend's age labeling. Failures are per-signal —
the endpoint never fabricates and never 500s the whole page. Missing
sources render `unavailable` with a reason; the listener signal is the
heartbeat row alone (its absence = down/unknown, never fake data).
"""

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import engine, get_db
from models import Boost, ListenerHeartbeat, SchedulerRun, Subscription
from services.telegram_payments import star_payments

from .ops_auth import require_ops_admin

logger = logging.getLogger("index_ops_health")

router = APIRouter()

_LISTENER_STALE_SECONDS = 90
_FRONTEND_PROBE_TIMEOUT = 2.5


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _probe_frontend() -> bool:
    """HTTP GET probe of the frontend container (2.5s timeout). Factored so
    tests can monkeypatch it."""
    url = os.getenv("FRONTEND_PROBE_URL", "http://frontend:5173/")
    try:
        async with httpx.AsyncClient(timeout=_FRONTEND_PROBE_TIMEOUT) as client:
            resp = await client.get(url)
        return resp.status_code < 500
    except Exception as e:
        logger.warning(f"ops/health: frontend probe failed: {e}")
        return False


def _signal(status: str, *, value=None, source: str | None = None, note: str | None = None) -> dict:
    out = {"status": status, "value": value}
    if source is not None:
        out["source"] = source
    if note is not None:
        out["note"] = note
    return out


def _heartbeat_payload(db: Session) -> dict | None:
    row = db.get(ListenerHeartbeat, 1)
    if row is None:
        return None
    return {
        "last_seen_at": row.last_seen_at,
        "payload": row.payload or {},
    }


def _scheduler_signal(db: Session, name: str) -> dict:
    row = db.scalar(select(SchedulerRun).where(SchedulerRun.scheduler == name))
    if row is None:
        return _signal("never run", value=None, source=f"scheduler_runs[{name}]")
    return _signal(
        "ok" if row.last_success_at is not None else "error",
        value={
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
            "last_error": row.last_error,
            "last_result": row.last_result,
        },
        source="scheduler_runs",
    )


@router.get("")
async def get_health(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    services: dict[str, dict] = {}

    # --- services.api: the endpoint itself responding ---
    services["services.api"] = _signal("up", source="endpoint")

    # --- services.db: SELECT 1 ---
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        services["services.db"] = _signal("up", source="database.engine")
    except Exception as e:
        logger.warning(f"ops/health: db probe failed: {e}")
        services["services.db"] = _signal("down", source="database.engine", note=str(e))

    # --- services.frontend: HTTP probe ---
    frontend_up = await _probe_frontend()
    services["services.frontend"] = _signal(
        "up" if frontend_up else "down",
        source="http probe",
    )

    # --- listener + bot + ingestion: heartbeat-derived (D9) ---
    hb = _heartbeat_payload(db)
    now = _now_utc()
    if hb is None:
        services["services.listener"] = _signal("unknown", value=None, source="listener_heartbeat")
        services["bot.connection"] = _signal("unknown", value=None, source="listener_heartbeat")
        services["bot.update_lag_seconds"] = _signal("unknown", value=None, source="listener_heartbeat")
        services["ingestion.queue_depth"] = _signal("unknown", value=None, source="listener_heartbeat")
        services["ingestion.items_per_hour"] = _signal("unknown", value=None, source="listener_heartbeat")
    else:
        age = (now - hb["last_seen_at"]).total_seconds()
        alive = age < _LISTENER_STALE_SECONDS
        payload = hb["payload"]
        services["services.listener"] = _signal(
            "up" if alive else "down",
            value={"age_seconds": round(age, 1)},
            source="listener_heartbeat",
        )
        services["bot.connection"] = _signal(
            "up" if alive else "down", source="heartbeat freshness (polling loop alive = connected)"
        )

        # update lag: now - payload.last_update_at
        lag = None
        lag_raw = payload.get("last_update_at")
        if lag_raw:
            try:
                lag = (now - datetime.fromisoformat(str(lag_raw).replace("Z", "+00:00"))).total_seconds()
                lag = round(lag, 1)
            except (ValueError, TypeError):
                lag = None
        services["bot.update_lag_seconds"] = _signal(
            "ok" if lag is not None else "unknown",
            value=lag,
            source="heartbeat payload last_update_at",
        )

        # queue depth
        services["ingestion.queue_depth"] = _signal(
            "ok" if payload.get("queue_depth") is not None else "unknown",
            value=payload.get("queue_depth"),
            source="heartbeat payload queue_depth",
        )

        # items per hour: rate since start, labeled
        rate = None
        total = payload.get("items_processed_total")
        started_raw = payload.get("started_at")
        if total is not None and started_raw:
            try:
                started = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
                hours = max((now - started).total_seconds() / 3600, 0.001)
                rate = round(total / hours, 1)
            except (ValueError, TypeError):
                rate = None
        services["ingestion.items_per_hour"] = _signal(
            "ok" if rate is not None else "unknown",
            value=rate,
            source="items_processed_total / hours since started_at (rate since start)",
        )

        # photo refresher scheduler stats ride the payload (D9)
        pr = payload.get("photo_refresher")
        services["schedulers.photo_refresher"] = _signal(
            "ok" if pr and pr.get("last_success_at") else ("error" if pr and pr.get("last_error") else "never run"),
            value=pr,
            source="heartbeat payload photo_refresher",
        )

    # --- signals without a data source (honest unavailable, NB-20 future) ---
    services["bot.handler_error_rate"] = _signal(
        "unavailable", source=None, note="no data source — handler errors are not tracked"
    )
    services["ingestion.rate_limit_headroom"] = _signal(
        "unavailable", source=None, note="no data source — 429s are not tracked"
    )
    services["ingestion.ai_providers"] = _signal(
        "unavailable", source=None,
        note="no health endpoint for groq/gemini (raw HTTP, no status tracking) — NB-20 is the future surface",
    )

    # --- schedulers ---
    services["schedulers.cleanup"] = _scheduler_signal(db, "cleanup")
    services["schedulers.reconciliation"] = _scheduler_signal(db, "reconciliation")

    # --- money ---
    try:
        balance = await star_payments.get_my_star_balance()
        services["money.star_balance"] = _signal(
            "ok", value=balance, source="getMyStarBalance"
        )
    except Exception as e:
        logger.warning(f"ops/health: star balance failed: {e}")
        services["money.star_balance"] = _signal(
            "error", value=None, source="getMyStarBalance", note=str(e)
        )

    try:
        transactions = await star_payments.get_star_transactions(limit=100)
        if not isinstance(transactions, list):
            transactions = []
        fulfilled = set()
        for charge_id in db.scalars(
            select(Boost.telegram_payment_charge_id).where(
                Boost.telegram_payment_charge_id.isnot(None)
            )
        ):
            fulfilled.add(charge_id)
        for charge_id in db.scalars(
            select(Subscription.telegram_payment_charge_id).where(
                Subscription.telegram_payment_charge_id.isnot(None)
            )
        ):
            fulfilled.add(charge_id)
        pending = [
            tx for tx in transactions
            if (tx.get("source") or {}).get("transaction_type") == "invoice_payment"
            and tx.get("id") not in fulfilled
        ]
        services["money.pending_payments"] = _signal(
            "ok",
            value={"count": len(pending)},
            source="star_transactions_vs_fulfillment",
        )
    except Exception as e:
        logger.warning(f"ops/health: pending payments failed: {e}")
        services["money.pending_payments"] = _signal(
            "unavailable", value=None,
            source="star_transactions_vs_fulfillment", note=str(e),
        )

    return {"generated_at": now.isoformat(), "services": services}

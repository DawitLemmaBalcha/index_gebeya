"""
NB-53: ops console Section 7 — Payments (blueprint §2.11).

Star ledger + balance, reconciliation status + run-now (drives the REAL
reconcile path via asyncio.run), refunds via the StarPaymentsAdapter
port (D4). Every mutation audited; the backend never refunds without the
audited call.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import SchedulerRun
from schemas import OpsRefundRequest
from services.audit import record_audit
from services.reconciliation import reconcile_star_payments
from services.scheduler_runs import record_scheduler_run
from services.telegram_payments import star_payments

from .ops_auth import require_ops_admin

logger = logging.getLogger("index_ops_payments")

router = APIRouter()


def _admin_user(request: Request) -> str:
    return request.session.get("ops_admin", {}).get("user", "admin")


@router.get("/ledger")
async def get_ledger(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    try:
        transactions = await star_payments.get_star_transactions(limit=100)
    except Exception as e:
        logger.warning(f"ops/payments: ledger failed: {e}")
        raise HTTPException(status_code=502, detail=f"Star ledger unavailable: {e}")
    if not isinstance(transactions, list):
        transactions = []
    rows = []
    for tx in transactions:
        source = tx.get("source") or {}
        payload = source.get("invoice_payload") or ""
        rows.append({
            "id": tx.get("id"),
            "date": tx.get("date"),
            "amount": tx.get("amount"),
            "transaction_type": source.get("transaction_type"),
            "payload_prefix": payload[:2] if payload else None,
            "user_id": (source.get("user") or {}).get("id"),
        })
    return rows


@router.get("/balance")
async def get_balance(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    try:
        balance = await star_payments.get_my_star_balance()
    except Exception as e:
        logger.warning(f"ops/payments: balance failed: {e}")
        raise HTTPException(status_code=502, detail=f"Star balance unavailable: {e}")
    return {"balance_stars": balance}


@router.get("/reconciliation")
def get_reconciliation(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    row = db.scalar(select(SchedulerRun).where(SchedulerRun.scheduler == "reconciliation"))
    if row is None:
        return {"status": "never run"}
    return {
        "status": "ok" if row.last_success_at is not None else "error",
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
        "last_error": row.last_error,
        "last_result": row.last_result,
    }


@router.post("/reconciliation/run")
def run_reconciliation(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    try:
        summary = asyncio.run(reconcile_star_payments(db))
        success = True
        error = None
    except Exception as e:
        logger.warning(f"ops/payments: run-now reconcile failed: {e}")
        summary = {"error": str(e)}
        success = False
        error = str(e)

    record_scheduler_run(
        db, scheduler="reconciliation", success=success,
        error=error, result=summary,
    )
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="run_reconciliation",
        section="payments",
        entity_type="scheduler",
        entity_id="reconciliation",
        after={"summary": summary},
    )
    return summary


@router.post("/refund")
async def refund(
    body: OpsRefundRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if not body.telegram_payment_charge_id:
        raise HTTPException(status_code=400, detail="Missing telegram_payment_charge_id")
    try:
        result = await star_payments.refund_star_payment(
            telegram_payment_charge_id=body.telegram_payment_charge_id
        )
    except Exception as e:
        logger.warning(f"ops/payments: refund failed: {e}")
        raise HTTPException(status_code=502, detail=f"Refund failed: {e}")

    record_audit(
        db,
        admin_user=_admin_user(request),
        action="refund_star_payment",
        section="payments",
        entity_type="payment",
        entity_id=body.telegram_payment_charge_id,
        after={"result": result},
    )
    return {"result": result}

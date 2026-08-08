"""
NB-50: scheduler-run bookkeeping for the ops console Overview (Rule 3.4).

One row per scheduler name (cleanup, reconciliation, photo_refresher),
upserted by the instrumented jobs themselves. `last_result` carries the
run-now summary JSON (additive, D5).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import SchedulerRun

logger = logging.getLogger("index_scheduler_runs")


def record_scheduler_run(
    db: Session, *,
    scheduler: str,
    success: bool,
    error: str | None = None,
    result: dict | None = None,
) -> None:
    """Upsert on scheduler name; last_run_at always, last_success_at on
    success, last_error on failure, last_result when provided. Commits."""
    row = db.scalar(select(SchedulerRun).where(SchedulerRun.scheduler == scheduler))
    now = datetime.now(timezone.utc)
    if row is None:
        row = SchedulerRun(scheduler=scheduler, last_run_at=now)
        db.add(row)
    else:
        row.last_run_at = now
    if success:
        row.last_success_at = now
        row.last_error = None
    else:
        row.last_error = error or "unknown error"
    if result is not None:
        row.last_result = result
    db.commit()

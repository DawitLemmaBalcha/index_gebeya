"""
NB-58: engine diagnostics — per-item decision traces (blueprint §4.1).

`build_item_trace` REPLAYS the per-alert pipeline stages as pure logic over
the same read-only queries the real orchestrator (services/alerting.py)
uses — duplication of the per-alert stages is the chosen honesty (the
instrumented-trace-mode alternative was rejected as riskier in the locked
blueprint).

Side-effect-free contract:
  - NO `_dispatch_notification`, NO `_create_system_notification`,
    NO `_apply_auto_pause`, NO best_opportunity_score writes, NO judge
    counter increment, NO commit. The whole replay never mutates the DB
    session.
  - The LLM judge call (`verify_match_with_llm`) is the ONLY external side
    effect — identical to the real pipeline's call; acceptable.

The outcome enum is the locked nine plus `expired` and `unknown_verdict`
(additive — the trace reflects the real pipeline; omitting them would
fabricate).

Import map (strict, blueprint §3): datetime/timezone/timedelta, Session,
select, Alert/Item/Notification, evaluate_match/MatchTier,
verify_match_with_llm/JudgeVerdict, RING_TOLERANCE/
NOTIFICATION_THROTTLE_SECONDS, json.
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_engine.llm_client import JudgeVerdict, verify_match_with_llm
from ai_engine.matcher import MatchTier, evaluate_match
from constants import NOTIFICATION_THROTTLE_SECONDS, RING_TOLERANCE
from models import Alert, Item, Notification


def _to_list(vector) -> list | None:
    """The exact vector conversion the orchestrator uses (alerting.py
    L58-64 / L83-86): pgvector rows expose a `.tolist()`; plain lists pass
    through."""
    if vector is None:
        return None
    if hasattr(vector, "tolist"):
        return vector.tolist()
    return list(vector)


def _stage(alert: Alert, outcome: str, *, score=0.0, tier=None, reason="") -> dict:
    return {
        "alert_id": alert.id,
        "query_text": alert.query_text,
        "outcome": outcome,
        "score": round(float(score), 4),
        "tier": tier,
        "reason": reason,
    }


def build_item_trace(db: Session, item_id: int, now: datetime | None = None) -> dict | None:
    """Replay the alert pipeline for one item; None when the item is missing
    (the route turns that into the 404). Never mutates the session."""
    item = db.get(Item, item_id)
    if not item:
        return None

    now_utc = now or datetime.now(timezone.utc)
    item_vec = _to_list(item.image_vector)
    alerts = db.scalars(select(Alert).where(Alert.is_active == True)).all()

    stages = []
    for alert in alerts:
        # ---------------------------------------------------------------
        # 1. Expiry gate — same comparison as alerting.py L172-184, but
        #    read-only: the real pipeline deactivates + queues a system DM;
        #    the trace only records the outcome.
        # ---------------------------------------------------------------
        if alert.expires_at:
            expiry = alert.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < now_utc:
                stages.append(_stage(
                    alert, "expired",
                    reason="Alert expired before the pipeline gates",
                ))
                continue

        # ---------------------------------------------------------------
        # 2. Price gate — alerting.py L190-201, read-only.
        # ---------------------------------------------------------------
        if alert.max_price is not None and item.price is not None:
            if item.price > alert.max_price:
                stages.append(_stage(
                    alert, "price_gate",
                    reason=f"Item price {item.price} > alert max {alert.max_price}",
                ))
                continue

        # ---------------------------------------------------------------
        # 3. Matching — the SAME computation as the real pipeline
        #    (evaluate_match + vector conversion, alerting.py L80-96).
        # ---------------------------------------------------------------
        alert_vec = _to_list(alert.query_vector)
        result = evaluate_match(
            item_vector=item_vec,
            alert_vector=alert_vec,
            item_price=item.price,
            alert_max_price=alert.max_price,
            item_title=item.title,
            alert_query_text=alert.query_text,
        )
        if result.tier == MatchTier.MISS:
            stages.append(_stage(
                alert, "threshold_miss",
                score=result.score, tier=result.tier.value,
                reason=result.reason,
            ))
            continue

        # ---------------------------------------------------------------
        # 4. Judge — conditional on NOT speed_pass (Rule 3.1). The LLM call
        #    is the only external side effect; an ERRORED verdict here does
        #    NOT bump the process-local counter (the real pipeline does).
        # ---------------------------------------------------------------
        if result.speed_pass:
            stages.append(_stage(
                alert, "speed_pass",
                score=1.0, tier=MatchTier.BULLSEYE.value,
                reason="Speed pass (deterministic normalized match) — LLM judge skipped",
            ))
            continue

        preferences = json.loads(alert.preferences) if alert.preferences else {}
        verdict = verify_match_with_llm(item.title, alert.query_text, preferences)
        if verdict is JudgeVerdict.REJECTED:
            stages.append(_stage(
                alert, "judge_rejected",
                score=result.score, tier=result.tier.value,
                reason="LLM judge rejected the match",
            ))
            continue
        if verdict is JudgeVerdict.ERRORED:
            stages.append(_stage(
                alert, "judge_errored",
                score=result.score, tier=result.tier.value,
                reason="LLM judge errored (fail-open in the real pipeline, "
                       "counter NOT incremented by the trace)",
            ))
            continue
        if verdict is not JudgeVerdict.APPROVED:
            # Defensive: a non-enum return fails CLOSED (alerting.py L128-132).
            stages.append(_stage(
                alert, "unknown_verdict",
                score=result.score, tier=result.tier.value,
                reason=f"LLM judge returned unknown verdict {verdict!r} — skipped",
            ))
            continue

        # ---------------------------------------------------------------
        # 5. Dispatch decision — alerting.py L207-226. BULLSEYE is always a
        #    candidate (the real pipeline ALSO raises the high water mark —
        #    the trace only READS it). RING compares against the STORED
        #    best_opportunity_score.
        # ---------------------------------------------------------------
        candidate = True
        suppress_reason = ""
        if result.tier == MatchTier.RING:
            if result.score < (alert.best_opportunity_score - RING_TOLERANCE):
                candidate = False
                suppress_reason = (
                    f"Ring score {result.score:.3f} below high water mark "
                    f"{alert.best_opportunity_score:.3f} - {RING_TOLERANCE}"
                )
        if not candidate:
            stages.append(_stage(
                alert, "high_water_suppressed",
                score=result.score, tier=result.tier.value,
                reason=suppress_reason,
            ))
            continue

        # ---------------------------------------------------------------
        # 6. Throttle — ring-only, same read as alerting.py L234-239.
        # ---------------------------------------------------------------
        if (
            result.tier == MatchTier.RING
            and NOTIFICATION_THROTTLE_SECONDS > 0
            and alert.last_triggered_at is not None
        ):
            elapsed = (now_utc - alert.last_triggered_at).total_seconds()
            if elapsed < NOTIFICATION_THROTTLE_SECONDS:
                stages.append(_stage(
                    alert, "throttled",
                    score=result.score, tier=result.tier.value,
                    reason=(
                        f"Ring match inside {NOTIFICATION_THROTTLE_SECONDS}s "
                        f"cooldown (last triggered {elapsed:.0f}s ago)"
                    ),
                ))
                continue

        # ---------------------------------------------------------------
        # 7. Dedup / duplicate suppression — the same read-only existence
        #    queries as alerting.py L243-269.
        # ---------------------------------------------------------------
        suppressed = False
        if item.is_dedup:
            one_hour_ago = now_utc - timedelta(hours=1)
            existing_from_channel = db.scalar(
                select(Notification.id).join(Item, Notification.item_id == Item.id).where(
                    Notification.alert_id == alert.id,
                    Item.channel_id == item.channel_id,
                    Notification.created_at >= one_hour_ago,
                    Notification.item_id != item.id,
                ).limit(1)
            )
            if existing_from_channel is not None:
                suppressed = True
                stages.append(_stage(
                    alert, "dedup_suppressed",
                    score=result.score, tier=result.tier.value,
                    reason="Alert already notified from this channel within the hour",
                ))
        else:
            existing = db.scalar(
                select(Notification).where(
                    Notification.alert_id == alert.id,
                    Notification.item_id == item.id,
                ).limit(1)
            )
            if existing is not None:
                suppressed = True
                stages.append(_stage(
                    alert, "dedup_suppressed",
                    score=result.score, tier=result.tier.value,
                    reason="Alert already notified for this item",
                ))
        if suppressed:
            continue

        # ---------------------------------------------------------------
        # 8. Dispatched — the real pipeline would queue a notification,
        #    bump counters, and auto-pause; the trace only records it.
        # ---------------------------------------------------------------
        stages.append(_stage(
            alert, "dispatched",
            score=result.score, tier=result.tier.value,
            reason="All gates passed — the pipeline would dispatch",
        ))

    return {
        "item_id": item.id,
        "generated_at": now_utc.isoformat(),
        "alerts_evaluated": len(stages),
        "stages": stages,
    }

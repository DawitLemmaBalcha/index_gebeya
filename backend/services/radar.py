"""
NB-57: the Anomaly Radar — the platform finds its own problems (Rule 4.1).

Five detections, each a pure query over `db`, each returning anomaly records
{type, severity, entity_id, summary, actions: [{verb, endpoint, method}]}.
Every anomaly ends in at least one one-click verb (Rule 4.2 — an anomaly
with no action is just another sqladmin table). Dismissals are persisted
state over radar_dismissals (ops state, not audit).

Process-local reads: the judge-error detection reads
`services.alerting.JUDGE_ERROR_COUNT / JUDGE_ERROR_LAST_TS` — module state
reset on API restart, documented (the radar reads the same module the
ops_health surface already exposes).
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import (
    CROWDSOURCE_SOLD_THRESHOLD,
    RADAR_DEAD_CHAT_SEVERITY_HIGH,
    RADAR_DEAD_CHAT_SEVERITY_MEDIUM,
    RADAR_PRICE_ANOMALY_MAX_X_MEDIAN,
    RADAR_SCAM_CHANNEL_MAX_TRUST,
    RADAR_SCAM_CHANNEL_MIN_REPORTS,
    RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X,
)
from models import Channel, Item, Notification, RadarDismissal, SoldReport, User
from services import alerting


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

def _category_medians(db: Session) -> dict[str, float]:
    """Median price per category over ACTIVE, priced items — the verified
    percentile_cont pattern (stats.py L154-155)."""
    rows = db.execute(
        select(
            Item.category,
            func.percentile_cont(0.5).within_group(Item.price),
        )
        .where(
            Item.status == "active",
            Item.price.isnot(None),
            Item.category.isnot(None),
        )
        .group_by(Item.category)
    ).all()
    return {cat: float(med) for cat, med in rows if med is not None}


def _item_report_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(SoldReport.item_id, func.count(SoldReport.id)).group_by(
            SoldReport.item_id
        )
    ).all()
    return {item_id: int(count) for item_id, count in rows}


def _dismiss_action():
    return {"verb": "Dismiss", "endpoint": "/ops/radar/resolve", "method": "POST"}


# ---------------------------------------------------------------------------
# The five detections
# ---------------------------------------------------------------------------

def detect_dead_chat_buyers(db: Session) -> list[dict]:
    """FAILED notifications (the honest rows from §3.4 instrumentation),
    one anomaly per user; severity by FAILED count. Actions: retry (the
    NB-59 shared verb) + dismiss."""
    rows = db.execute(
        select(Notification, User.telegram_id)
        .join(User, Notification.user_id == User.id)
        .where(Notification.status == "FAILED")
        .order_by(Notification.id.desc())
    ).all()
    by_user: dict[int, list[int]] = {}
    for notif, tg_id in rows:
        by_user.setdefault(tg_id, []).append(notif.id)

    anomalies = []
    for tg_id, ids in by_user.items():
        count = len(ids)
        if count < RADAR_DEAD_CHAT_SEVERITY_MEDIUM:
            continue
        severity = "high" if count >= RADAR_DEAD_CHAT_SEVERITY_HIGH else "medium"
        anomalies.append({
            "type": "dead_chat_buyer",
            "severity": severity,
            "entity_id": str(tg_id),
            "summary": (
                f"Buyer {tg_id} has {count} failed notification "
                f"deliveries (ids: {ids[:3]}) — chat unreachable."
            ),
            "actions": [
                {
                    "verb": "Retry delivery",
                    "endpoint": f"/ops/actions/notifications/{ids[0]}/retry",
                    "method": "POST",
                },
                _dismiss_action(),
            ],
        })
    return anomalies


def detect_judge_error_spikes(db: Session) -> list[dict]:
    """Process-local judge counters (reset on API restart). Dismiss-only:
    no pause-matching kill switch exists (v1 locked decision, UI copy)."""
    count = getattr(alerting, "JUDGE_ERROR_COUNT", 0)
    if not count:
        return []
    last_ts = getattr(alerting, "JUDGE_ERROR_LAST_TS", None)
    ts = last_ts.isoformat() if last_ts else "unknown"
    return [{
        "type": "judge_error_spike",
        "severity": "medium",
        "entity_id": "judge",
        "summary": (
            f"{count} LLM judge errors since API restart (last at {ts}). "
            f"Dismiss-only: no pause-matching kill switch exists (v1 locked)."
        ),
        "actions": [_dismiss_action()],
    }]


def detect_report_spikes(db: Session) -> list[dict]:
    """Active items with sold-report counts at/near the take-down threshold.
    At-threshold → high; near → medium."""
    report_counts = _item_report_counts(db)
    anomalies = []
    for item_id, count in report_counts.items():
        if count < CROWDSOURCE_SOLD_THRESHOLD - 1:
            continue
        item = db.get(Item, item_id)
        if not item or item.status != "active":
            continue
        severity = "high" if count >= CROWDSOURCE_SOLD_THRESHOLD else "medium"
        anomalies.append({
            "type": "report_spike",
            "severity": severity,
            "entity_id": str(item_id),
            "summary": (
                f"Item #{item_id} ('{item.title}') has {count}/"
                f"{CROWDSOURCE_SOLD_THRESHOLD} sold reports — "
                f"{'at' if count >= CROWDSOURCE_SOLD_THRESHOLD else 'near'} "
                f"the take-down threshold."
            ),
            "actions": [
                {
                    "verb": "Clear reports",
                    "endpoint": f"/ops/radar/items/{item_id}/clear-reports",
                    "method": "POST",
                },
                {"verb": "View item", "endpoint": f"/item/{item_id}", "method": "GET"},
                _dismiss_action(),
            ],
        })
    return anomalies


def detect_scam_pattern_channels(db: Session) -> list[dict]:
    """The composite watchlist: low trust + at least one active price
    outlier (≥ RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X × category median) +
    channel-level report count ≥ RADAR_SCAM_CHANNEL_MIN_REPORTS."""
    medians = _category_medians(db)
    report_counts = _item_report_counts(db)
    anomalies = []
    for channel in db.scalars(select(Channel)).all():
        if (
            channel.trust_score is None
            or channel.trust_score > RADAR_SCAM_CHANNEL_MAX_TRUST
        ):
            continue
        items = db.scalars(
            select(Item).where(
                Item.channel_id == channel.id,
                Item.status == "active",
            )
        ).all()
        outlier_found = False
        for item in items:
            if item.price is None or item.price <= 0 or not item.category:
                continue
            median = medians.get(item.category)
            if median and median > 0 and item.price >= RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X * median:
                outlier_found = True
                break
        if not outlier_found:
            continue
        channel_reports = sum(report_counts.get(i.id, 0) for i in items)
        if channel_reports < RADAR_SCAM_CHANNEL_MIN_REPORTS:
            continue

        actions = [
            {
                "verb": "Pause indexing",
                "endpoint": f"/ops/radar/channels/{channel.id}/pause",
                "method": "POST",
            },
        ]
        if channel.registered_by is not None:
            # the shared Package-2 ban endpoint (one verb per action, never
            # duplicated — blueprint §5.2)
            actions.append({
                "verb": "Ban owner",
                "endpoint": f"/ops/users/{channel.registered_by}/ban",
                "method": "POST",
            })
        actions.append(_dismiss_action())

        anomalies.append({
            "type": "scam_pattern_channel",
            "severity": "high",
            "entity_id": str(channel.id),
            "summary": (
                f"Channel @{channel.username} (trust {channel.trust_score}) "
                f"has a price outlier vs its category median and "
                f"{channel_reports} sold reports."
            ),
            "actions": actions,
        })
    return anomalies


def detect_price_anomalies(db: Session) -> list[dict]:
    """0-ETB items (medium) and items ≥ RADAR_PRICE_ANOMALY_MAX_X_MEDIAN ×
    category median (high). Items with no computable median are skipped."""
    medians = _category_medians(db)
    anomalies = []
    for item in db.scalars(select(Item).where(Item.status == "active")).all():
        if item.price is None:
            continue
        if item.price == 0:
            anomalies.append({
                "type": "price_anomaly",
                "severity": "medium",
                "entity_id": str(item.id),
                "summary": f"Item #{item.id} ('{item.title}') is listed at 0 ETB.",
                "actions": [
                    {
                        "verb": "Hide item",
                        "endpoint": f"/ops/radar/items/{item.id}/hide",
                        "method": "POST",
                    },
                    _dismiss_action(),
                ],
            })
            continue
        median = medians.get(item.category) if item.category else None
        if median and median > 0 and item.price >= RADAR_PRICE_ANOMALY_MAX_X_MEDIAN * median:
            anomalies.append({
                "type": "price_anomaly",
                "severity": "high",
                "entity_id": str(item.id),
                "summary": (
                    f"Item #{item.id} ('{item.title}') is priced "
                    f"{item.price:.0f} ETB — ≥ {RADAR_PRICE_ANOMALY_MAX_X_MEDIAN:.0f}× "
                    f"the {item.category} median ({median:.0f} ETB)."
                ),
                "actions": [
                    {
                        "verb": "Hide item",
                        "endpoint": f"/ops/radar/items/{item.id}/hide",
                        "method": "POST",
                    },
                    _dismiss_action(),
                ],
            })
    return anomalies


# ---------------------------------------------------------------------------
# The radar surface
# ---------------------------------------------------------------------------

def get_radar(db: Session) -> dict:
    """Runs all five detections, drops dismissed (type, entity_id) pairs,
    returns the merged list (Rule 4.3 — the admin's daily driver)."""
    detections = (
        detect_dead_chat_buyers(db)
        + detect_judge_error_spikes(db)
        + detect_report_spikes(db)
        + detect_scam_pattern_channels(db)
        + detect_price_anomalies(db)
    )
    dismissed = {
        (row.type, row.entity_id)
        for row in db.scalars(select(RadarDismissal)).all()
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anomalies": [
            a for a in detections
            if (a["type"], a["entity_id"]) not in dismissed
        ],
    }


def is_dismissed(db: Session, type_: str, entity_id: str) -> bool:
    return db.scalar(
        select(RadarDismissal.id).where(
            RadarDismissal.type == type_,
            RadarDismissal.entity_id == str(entity_id),
        )
    ) is not None


def dismiss(db: Session, type_: str, entity_id: str, dismissed_by: str | None = None) -> None:
    """Idempotent dismissal state write (UNIQUE type+entity_id)."""
    if is_dismissed(db, type_, entity_id):
        return
    db.add(RadarDismissal(
        type=type_,
        entity_id=str(entity_id),
        dismissed_by=dismissed_by,
    ))
    db.commit()

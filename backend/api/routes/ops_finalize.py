"""
NB-55..NB-60 / TECH-40..45: the ops-finalization router — the four stub
sections become real action centers (ops-finalization blueprint §2).

Reframe (diagnose-and-act): sqladmin edits rows; the ops console computes,
diagnoses, and makes the engine act. Every surface ends in at least one
verb; nothing reduces to row-editing.

Sections:
  - /ops/quality/*        — Quality Events (NB-55) + Items analytics (NB-60)
  - /ops/users/*          — ban lever + footprint (NB-56, NB-60)
  - /ops/radar/*          — anomaly radar + action chain (NB-57)
  - /ops/diagnostics/*    — engine decision traces (NB-58)
  - /ops/actions/*        — engine verbs: reprocess/retry/reconcile (NB-59)

Every mutation records an audit row (ops-console.md Rule 1.4).
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Alert,
    Boost,
    Channel,
    Item,
    ItemEdit,
    Notification,
    Review,
    SoldReport,
    Subscription,
    User,
    UserInteraction,
)
from schemas import ItemEditResponse, RadarResolveRequest
from services.audit import record_audit
from services.alerting import process_new_item
from services.ban import ban_user, unban_user
from services.radar import dismiss, get_radar
from services.reconciliation import reconcile_star_payments
from services.scheduler_runs import record_scheduler_run
from services.trace import build_item_trace

from .ops_auth import require_ops_admin

logger = logging.getLogger("index_ops_finalize")

router = APIRouter()


def _admin_user(request: Request) -> str:
    return request.session.get("ops_admin", {}).get("user", "admin")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ===========================================================================
# NB-55: Quality Events — the monitoring-not-doing layer (Rule 2)
# ===========================================================================

# The revertible field set (Rule 2.2): anything an owner can correct. Any
# other field value → 400 "field not revertible".
_REVERTIBLE_FIELDS = {"title", "description", "price", "category", "subcategory", "specs"}
# Fields whose revert re-runs the alert pipeline (Rule 1.3 consistency).
_RETRIGGER_FIELDS = {"price", "specs", "category", "subcategory"}


def _console_admin_user(db: Session, request: Request) -> User:
    """NB-55: the reserved console-admin sentinel User row (telegram_id=-1).

    ItemEdit.edited_by is a NOT NULL FK to users.id — owner edits record the
    owner; admin reverts record the sentinel (username = the current admin).
    One row, resolve-or-create, reused across reverts. Documented in code as
    the console-admin sentinel."""
    admin_name = _admin_user(request)
    user = db.scalar(select(User).where(User.telegram_id == -1))
    if user is None:
        user = User(telegram_id=-1, username=admin_name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _coerce_restored_value(field: str, old_value: str | None):
    """NB-55 revert coercion: price → float (parse failure → 400), specs →
    canonical JSON (legacy python-repr dicts parsed leniently, then 400),
    all other revertible fields → verbatim string; None stays NULL."""
    if old_value is None:
        return None
    if field == "price":
        try:
            return float(old_value)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid stored price value")
    if field == "specs":
        try:
            return json.dumps(json.loads(old_value), sort_keys=True)
        except (json.JSONDecodeError, TypeError):
            try:
                return json.dumps(json.loads(old_value.replace("'", '"')), sort_keys=True)
            except (json.JSONDecodeError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid stored specs JSON")
    return old_value


def _value_to_edit_str(item, field: str, value) -> str | None:
    """Mirror item_status._log_edit's storage convention for ItemEdit rows."""
    if value is None:
        return None
    if field == "specs":
        try:
            if isinstance(value, str):
                return json.dumps(json.loads(value), sort_keys=True)
            return json.dumps(value, sort_keys=True)
        except (json.JSONDecodeError, TypeError):
            return str(value)
    return str(value)


@router.get("/quality/events")
def list_quality_events(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    _: None = Depends(require_ops_admin),
):
    """NB-55 (Rule 2.1/2.3): the Quality Events stream — every owner
    correction surfaced from the existing ItemEdit history (one row per
    changed field), joined to the item title and the editor's username,
    newest first."""
    rows = db.execute(
        select(ItemEdit, Item.title, User.username)
        .join(Item, ItemEdit.item_id == Item.id)
        .join(User, ItemEdit.edited_by == User.id)
        .order_by(ItemEdit.timestamp.desc(), ItemEdit.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    events = []
    for edit, title, username in rows:
        base = ItemEditResponse.model_validate(edit).model_dump()
        base["title"] = title
        base["edited_by_username"] = username
        events.append(base)
    return events


@router.post("/quality/events/{event_id}/revert")
def revert_item_edit(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """NB-55 (Rule 2.2): restore the prior value of an owner correction.

    Revert is itself an edit event (a NEW ItemEdit row — Rule 2.1
    visibility), authored by the console-admin sentinel. Reverts of
    price/specs/category/subcategory re-run the alert pipeline (Rule 1.3)."""
    event = db.get(ItemEdit, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Item edit not found")
    if event.field not in _REVERTIBLE_FIELDS:
        raise HTTPException(status_code=400, detail="field not revertible")

    item = db.get(Item, event.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Capture the current value BEFORE restoring (the new event's old_value).
    current = getattr(item, event.field)
    current_str = _value_to_edit_str(item, event.field, current)

    restored = _coerce_restored_value(event.field, event.old_value)
    setattr(item, event.field, restored)
    db.commit()

    new_value_str = (
        restored if restored is None or isinstance(restored, str) else str(restored)
    )
    editor = _console_admin_user(db, request)
    db.add(ItemEdit(
        item_id=item.id,
        field=event.field,
        old_value=current_str,
        new_value=new_value_str,
        edited_by=editor.id,
    ))
    db.commit()

    # Rule 1.3: the re-triggered fields re-evaluate matching (the same call
    # the owner edit path uses — item_status.update_item).
    if event.field in _RETRIGGER_FIELDS:
        try:
            process_new_item(db, item.id)
        except Exception as e:
            logger.warning(f"Revert re-processing failed for item {item.id}: {e}")

    record_audit(
        db,
        admin_user=_admin_user(request),
        action="revert_item_edit",
        section="quality",
        entity_type="item_edit",
        entity_id=str(event.id),
        before={"item_id": item.id, "field": event.field, "value": current_str},
        after={"item_id": item.id, "field": event.field, "value": new_value_str},
    )
    return {"status": "reverted", "item_id": item.id, "field": event.field}


# ===========================================================================
# NB-56: Users — the ban lever (Rule 3) + footprint counts (Rule 7.1)
# ===========================================================================

# NB-60 §6.1: the two explicit view events (server view_item, client
# view_item_card) — mirrors services/stats.py L24-25 (VIEW_INTERACTION_TYPES).
_VIEW_TYPES = ("view_item", "view_item_card")

# NB-60 §6.2: price-distribution bucket edges over active priced items
# (half-open: lo <= price < hi; the last bucket is open-ended).
_PRICE_BUCKETS = [
    ("0-1000", 0, 1000),
    ("1000-5000", 1000, 5000),
    ("5000-20000", 5000, 20000),
    ("20000-100000", 20000, 100000),
    ("100000+", 100000, None),
]


def _day_str(day) -> str:
    """Normalize a DB/date value to the 'YYYY-MM-DD' string used by the
    analytics day axis."""
    if hasattr(day, "isoformat"):
        return day.isoformat()
    return str(day)[:10]

def _user_footprint_counts(db: Session, user_id: int) -> dict:
    """Counts across the user's footprint tables (Rule 7.1)."""
    from models import Boost, Review, SoldReport, Subscription

    reviews = db.scalar(select(func.count(Review.id)).where(Review.user_id == user_id)) or 0
    alerts_total = db.scalar(select(func.count(Alert.id)).where(Alert.user_id == user_id)) or 0
    alerts_active = db.scalar(
        select(func.count(Alert.id)).where(Alert.user_id == user_id, Alert.is_active == True)
    ) or 0
    subs_active = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.user_id == user_id, Subscription.status == "active"
        )
    ) or 0
    boosts = db.scalar(select(func.count(Boost.id)).where(Boost.user_id == user_id)) or 0
    sold_reports = db.scalar(
        select(func.count(SoldReport.id)).where(SoldReport.user_id == user_id)
    ) or 0
    return {
        "reviews": reviews,
        "alerts_active": alerts_active,
        "alerts_total": alerts_total,
        "subscriptions_active": subs_active,
        "boosts": boosts,
        "sold_reports": sold_reports,
    }


def _resolve_user_by_telegram_id(db: Session, telegram_id: int) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{telegram_id}/status")
def user_status(
    telegram_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """NB-56 §2.4: one screen per user — banned flag + footprint counts."""
    user = _resolve_user_by_telegram_id(db, telegram_id)
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "banned": user.banned,
        "footprint": _user_footprint_counts(db, user.id),
    }


@router.post("/users/{telegram_id}/ban")
def ban_user_route(
    telegram_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """NB-56 §2.4: the ban lever — one flag; unban restores instantly
    (Rule 3.5, no side jobs)."""
    user = _resolve_user_by_telegram_id(db, telegram_id)
    ban_user(db, user.id)
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="ban_user",
        section="users",
        entity_type="user",
        entity_id=str(user.id),
        before={"banned": False, "telegram_id": telegram_id},
        after={"banned": True, "telegram_id": telegram_id},
    )
    return {"telegram_id": user.telegram_id, "banned": True}


@router.post("/users/{telegram_id}/unban")
def unban_user_route(
    telegram_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """NB-56 §2.4: the unban lever — instant restoration (Rule 3.5)."""
    user = _resolve_user_by_telegram_id(db, telegram_id)
    unban_user(db, user.id)
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="unban_user",
        section="users",
        entity_type="user",
        entity_id=str(user.id),
        before={"banned": True, "telegram_id": telegram_id},
        after={"banned": False, "telegram_id": telegram_id},
    )
    return {"telegram_id": user.telegram_id, "banned": False}


# ===========================================================================
# NB-58: Engine diagnostics — per-item decision traces (Rule 5)
# ===========================================================================

@router.get("/diagnostics/items/{item_id}/trace")
def item_trace_route(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """NB-58 §4.2: the side-effect-free replay of the alert pipeline for one
    item — every per-alert stage as data (expiry, price gate, match, judge,
    dispatch decision, throttle, dedup). No dispatch, no counters, no
    best_opportunity_score writes, no commit. The LLM judge call is the only
    external side effect."""
    trace = build_item_trace(db, item_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return trace


@router.get("/users/{telegram_id}/footprint")
def user_footprint(
    telegram_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """NB-60 §6.1: the deep user footprint — reviews (total + rating
    distribution 1..5 + recent 5), alerts (active/total), subscriptions
    (active + product), boosts (total/active), interactions (counts by
    type + recent 50). All joins resolve through users.id."""
    user = _resolve_user_by_telegram_id(db, telegram_id)

    # --- reviews ---
    reviews_total = db.scalar(
        select(func.count(Review.id)).where(Review.user_id == user.id)
    ) or 0
    rating_rows = db.execute(
        select(Review.rating, func.count(Review.id))
        .where(Review.user_id == user.id)
        .group_by(Review.rating)
    ).all()
    rating_distribution = {str(r): 0 for r in range(1, 6)}
    for rating, count in rating_rows:
        if 1 <= rating <= 5:
            rating_distribution[str(rating)] = count
    recent_review_rows = db.execute(
        select(Review, Channel.username)
        .join(Channel, Review.channel_id == Channel.id)
        .where(Review.user_id == user.id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(5)
    ).all()
    recent_reviews = [
        {
            "channel_id": review.channel_id,
            "channel_username": username,
            "rating": review.rating,
            "comment": review.comment,
            "created_at": (
                review.created_at.isoformat() if review.created_at else None
            ),
        }
        for review, username in recent_review_rows
    ]

    # --- alerts ---
    alerts_total = db.scalar(
        select(func.count(Alert.id)).where(Alert.user_id == user.id)
    ) or 0
    alerts_active = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.user_id == user.id, Alert.is_active == True
        )
    ) or 0

    # --- subscriptions (one active row per user in v1) ---
    subs_active = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.user_id == user.id, Subscription.status == "active"
        )
    ) or 0
    active_sub = db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.id.desc())
        .limit(1)
    )

    # --- boosts (active = placement window still open) ---
    now_utc = _now_utc()
    boosts_total = db.scalar(
        select(func.count(Boost.id)).where(Boost.user_id == user.id)
    ) or 0
    boosts_active = db.scalar(
        select(func.count(Boost.id)).where(
            Boost.user_id == user.id, Boost.ends_at > now_utc
        )
    ) or 0

    # --- interactions ---
    count_rows = db.execute(
        select(UserInteraction.interaction_type, func.count(UserInteraction.id))
        .where(UserInteraction.user_id == user.id)
        .group_by(UserInteraction.interaction_type)
    ).all()
    recent_interaction_rows = db.scalars(
        select(UserInteraction)
        .where(UserInteraction.user_id == user.id)
        .order_by(UserInteraction.created_at.desc(), UserInteraction.id.desc())
        .limit(50)
    ).all()

    return {
        "user": {
            "telegram_id": user.telegram_id,
            "username": user.username,
            "banned": user.banned,
        },
        "reviews": {
            "total": reviews_total,
            "rating_distribution": rating_distribution,
            "recent": recent_reviews,
        },
        "alerts": {"active": alerts_active, "total": alerts_total},
        "subscriptions": {
            "active": subs_active,
            "product": active_sub.product if active_sub else None,
        },
        "boosts": {"total": boosts_total, "active": boosts_active},
        "interactions": {
            "counts_by_type": {t: n for t, n in count_rows},
            "recent_50": [
                {
                    "id": row.id,
                    "item_id": row.item_id,
                    "interaction_type": row.interaction_type,
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                }
                for row in recent_interaction_rows
            ],
        },
    }


# ===========================================================================
# NB-60: Items analytics (blueprint §6.2)
# ===========================================================================

@router.get("/items/analytics")
def items_analytics(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Three blocks over live rows:
    - views_over_time: last 14 calendar days — aggregate daily views plus
      per-item daily series for the top-20 items by total views;
    - price_distribution: per category, histogram buckets over ACTIVE priced
      items (edges: 0-1k / 1k-5k / 5k-20k / 20k-100k / 100k+);
    - per_channel: per ACTIVE channel — item count, view count, sold-report
      count."""
    now_utc = _now_utc()
    today = now_utc.date()
    start_date = today - timedelta(days=13)  # 14 days inclusive
    window_start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    days = [(start_date + timedelta(days=i)).isoformat() for i in range(14)]

    # --- views over time (view_item + view_item_card, windowed) ---
    view_rows = db.execute(
        select(
            UserInteraction.item_id,
            func.date(UserInteraction.created_at).label("day"),
            func.count(UserInteraction.id),
        )
        .where(
            UserInteraction.interaction_type.in_(_VIEW_TYPES),
            UserInteraction.created_at >= window_start,
        )
        .group_by(UserInteraction.item_id, func.date(UserInteraction.created_at))
    ).all()
    per_day_total = {d: 0 for d in days}
    per_item: dict[int, dict[str, int]] = {}
    for item_id, day, count in view_rows:
        d = _day_str(day)
        per_day_total[d] = per_day_total.get(d, 0) + count
        if item_id is not None:
            per_item.setdefault(item_id, {})
            per_item[item_id][d] = per_item[item_id].get(d, 0) + count

    # the per-item series surfaces LIVE inventory only (the aggregate keeps
    # every view event in the window)
    active_item_ids = set(db.scalars(
        select(Item.id).where(Item.status == "active")
    ).all())
    per_item = {
        iid: day_map for iid, day_map in per_item.items()
        if iid in active_item_ids
    }

    ranked = sorted(
        per_item.items(), key=lambda kv: sum(kv[1].values()), reverse=True
    )[:20]
    top_items = []
    for item_id, day_map in ranked:
        item = db.get(Item, item_id)
        top_items.append({
            "item_id": item_id,
            "title": item.title if item else None,
            "total": sum(day_map.values()),
            "daily": [day_map.get(d, 0) for d in days],
        })

    # --- price distribution per category (active priced items) ---
    priced_rows = db.execute(
        select(Item.category, Item.price).where(
            Item.status == "active", Item.price.isnot(None)
        )
    ).all()
    by_category: dict[str, dict[str, int]] = {}
    for category, price in priced_rows:
        cat = by_category.setdefault(category or "Uncategorized", {
            name: 0 for name, _, _ in _PRICE_BUCKETS
        })
        for name, lo, hi in _PRICE_BUCKETS:
            if hi is None:
                if price >= lo:
                    cat[name] += 1
                    break
            elif lo <= price < hi:
                cat[name] += 1
                break
    price_distribution = [
        {"category": category, "buckets": buckets}
        for category, buckets in sorted(by_category.items())
    ]

    # --- per active channel aggregation ---
    per_channel = []
    for channel in db.scalars(
        select(Channel).where(Channel.is_active == True).order_by(Channel.id)
    ).all():
        items_count = db.scalar(
            select(func.count(Item.id)).where(
                Item.channel_id == channel.id, Item.status == "active"
            )
        ) or 0
        views_count = db.scalar(
            select(func.count(UserInteraction.id))
            .join(Item, UserInteraction.item_id == Item.id)
            .where(
                Item.channel_id == channel.id,
                UserInteraction.interaction_type.in_(_VIEW_TYPES),
            )
        ) or 0
        sold_count = db.scalar(
            select(func.count(SoldReport.id))
            .join(Item, SoldReport.item_id == Item.id)
            .where(Item.channel_id == channel.id)
        ) or 0
        per_channel.append({
            "channel_id": channel.id,
            "username": channel.username,
            "title": channel.title,
            "items": items_count,
            "views": views_count,
            "sold_reports": sold_count,
        })

    return {
        "views_over_time": {
            "days": days,
            "total": [per_day_total.get(d, 0) for d in days],
            "top_items": top_items,
        },
        "price_distribution": price_distribution,
        "per_channel": per_channel,
    }


# ===========================================================================
# NB-57: Anomaly Radar — computed problems with action chaining (Rule 4)
# ===========================================================================

@router.get("/radar")
def radar_route(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Rule 4.3: the admin's daily driver — refresh on load, see what's
    wrong, act. Every anomaly carries at least one one-click verb (4.2)."""
    return get_radar(db)


@router.post("/radar/resolve")
def radar_resolve(
    body: RadarResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Dismiss an anomaly identity — the state write is radar_dismissals
    (UNIQUE type+entity_id); the action itself is audited."""
    dismiss(db, body.type, body.entity_id, dismissed_by=_admin_user(request))
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="dismiss_anomaly",
        section="trust",
        entity_type="radar_dismissal",
        entity_id=f"{body.type}:{body.entity_id}",
        after={"type": body.type, "entity_id": body.entity_id},
    )
    return {"status": "dismissed"}


@router.post("/radar/items/{item_id}/clear-reports")
def radar_clear_reports(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Enforcement verb: directly deletes the item's SoldReport rows. The
    owner-gated service (item_status.clear_reports) is the OWNER flow; the
    admin verb is an enforcement action and bypasses it — documented drift."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    deleted = db.execute(delete(SoldReport).where(SoldReport.item_id == item_id))
    db.commit()
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="clear_reports_admin",
        section="trust",
        entity_type="item",
        entity_id=str(item_id),
        after={"deleted": deleted.rowcount or 0},
    )
    return {"status": "cleared", "deleted": deleted.rowcount or 0}


@router.post("/radar/channels/{channel_id}/pause")
def radar_pause_channel(
    channel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Enforcement verb: sets indexing_paused directly (the worker gate
    honors it); the channels route's toggle is owner-authorized — the admin
    action sets the flag directly (documented drift)."""
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel.indexing_paused = True
    db.commit()
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="pause_channel_indexing",
        section="trust",
        entity_type="channel",
        entity_id=str(channel_id),
        after={"indexing_paused": True},
    )
    return {"status": "paused", "channel_id": channel_id}


@router.post("/radar/items/{item_id}/hide")
def radar_hide_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Enforcement verb: status 'removed' + is_active False — search/feed
    filter on status, browse filters on both; the item stays as evidence."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status = "removed"
    item.is_active = False
    db.commit()
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="hide_item",
        section="trust",
        entity_type="item",
        entity_id=str(item_id),
        after={"status": "removed", "is_active": False},
    )
    return {"status": "hidden", "item_id": item_id}


# ===========================================================================
# NB-59: Engine actions — re-run, retry, trigger (blueprint §5.1)
# ===========================================================================

@router.post("/actions/items/{item_id}/reprocess")
def action_reprocess(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Re-run the alert pipeline for one item. Idempotent by design: the
    pipeline's duplicate suppression and throttle guard re-dispatch
    (blueprint §5.1). The verb itself runs the pipeline every time."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    process_new_item(db, item_id)
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="reprocess_item",
        section="alerts",
        entity_type="item",
        entity_id=str(item_id),
        after={"reprocess": True},
    )
    return {"status": "reprocessed", "item_id": item_id}


@router.post("/actions/notifications/{notification_id}/retry")
def action_retry_notification(
    notification_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """The shared retry verb (the radar's dead-chat action references this
    endpoint — one endpoint per verb, blueprint §5.2). FAILED → PENDING and
    the poller picks it up via /pending; PENDING → 409; terminal → 409."""
    notif = db.get(Notification, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notif.status == "PENDING":
        raise HTTPException(status_code=409, detail="Notification already pending")
    if notif.status != "FAILED":
        raise HTTPException(
            status_code=409,
            detail=f"Notification is in a terminal state ({notif.status})",
        )
    before = notif.status
    notif.status = "PENDING"
    db.commit()
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="retry_notification",
        section="alerts",
        entity_type="notification",
        entity_id=str(notification_id),
        before={"status": before},
        after={"status": "PENDING"},
    )
    return {"status": "pending", "notification_id": notification_id}


@router.post("/actions/reconcile")
def action_reconcile(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """Trigger the Star-payments reconciliation now — the exact
    ops_payments.py L84-113 run-now pattern, consolidated on the shared
    verb registry (blueprint §5.1)."""
    try:
        summary = asyncio.run(reconcile_star_payments(db))
        success = True
        error = None
    except Exception as e:
        logger.warning(f"ops/actions: run-now reconcile failed: {e}")
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
        action="reconcile_now",
        section="payments",
        entity_type="scheduler",
        entity_id="reconciliation",
        after={"summary": summary},
    )
    return {"status": "reconcile_done", "summary": summary}

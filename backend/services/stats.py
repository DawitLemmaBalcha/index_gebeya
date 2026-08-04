"""
Seller Intelligence aggregation (NB-47, blueprint §2.4).

Core block (free, every channel owner): views per item + 7-day sparkline,
alert matches, notifications dispatched (bullseye/ring split).
Pro block (gated by an active all_in_one subscription): price positioning vs
the same top-level category median, category pulse week-over-week, top
performers by views.

No fake numbers — every figure traces to user_interactions / notifications /
alerts / items (Rule 8.x "no estimates").
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Alert, Item, Notification, UserInteraction
from services.subscriptions import get_active_subscription

logger = logging.getLogger("index_stats")

# D9: the two explicit view events (server view_item, client view_item_card)
VIEW_INTERACTION_TYPES = ("view_item", "view_item_card")
SPARKLINE_DAYS = 7
TOP_PERFORMERS_LIMIT = 5


def get_channel_dashboard(db: Session, channel_id: int, user) -> dict:
    """
    Owner-only (route enforces). Returns:
    {"is_pro", "core": {...}, "pro": null | {...}}
    """
    now = datetime.now(timezone.utc)
    sub = get_active_subscription(db, user)
    is_pro = bool(sub and sub.product == "all_in_one")

    channel_items = db.scalars(
        select(Item).where(Item.channel_id == channel_id)
    ).all()
    channel_item_ids = [i.id for i in channel_items]

    core = _build_core(db, channel_id, channel_item_ids, channel_items, now)
    pro = _build_pro(db, channel_item_ids, channel_items, now) if is_pro else None

    return {"is_pro": is_pro, "core": core, "pro": pro}


def _build_core(db, channel_id, channel_item_ids, channel_items, now):
    items_out = []
    total_dispatched = {"bullseye": 0, "ring": 0}

    if not channel_item_ids:
        return {
            "items": [],
            "matching_buyers": 0,
            "total_dispatched": total_dispatched,
        }

    # --- Views per item (D9: only the two explicit view events) ---
    view_rows = db.execute(
        select(UserInteraction.item_id, func.count())
        .where(
            UserInteraction.item_id.in_(channel_item_ids),
            UserInteraction.interaction_type.in_(VIEW_INTERACTION_TYPES),
        )
        .group_by(UserInteraction.item_id)
    ).all()
    views_by_item = {item_id: cnt for item_id, cnt in view_rows}

    # --- 7-day sparkline buckets (calendar dates) ---
    spark_start = (now - timedelta(days=SPARKLINE_DAYS - 1)).date()
    spark_rows = db.execute(
        select(
            UserInteraction.item_id,
            func.date(UserInteraction.created_at),
            func.count(),
        )
        .where(
            UserInteraction.item_id.in_(channel_item_ids),
            UserInteraction.interaction_type.in_(VIEW_INTERACTION_TYPES),
            UserInteraction.created_at >= spark_start,
        )
        .group_by(UserInteraction.item_id, func.date(UserInteraction.created_at))
    ).all()
    spark_by_item = {}
    for item_id, day, cnt in spark_rows:
        spark_by_item.setdefault(item_id, {})[day.isoformat()] = cnt

    # --- Dispatched (SENT only), split by tier, per item and total ---
    sent_rows = db.execute(
        select(Notification.item_id, Notification.match_tier, func.count())
        .join(Item, Notification.item_id == Item.id)
        .where(Item.channel_id == channel_id, Notification.status == "SENT")
        .group_by(Notification.item_id, Notification.match_tier)
    ).all()
    dispatched_by_item = {}
    for item_id, tier, cnt in sent_rows:
        bucket = dispatched_by_item.setdefault(item_id, {"bullseye": 0, "ring": 0})
        if tier in bucket:
            bucket[tier] = cnt
        if tier in total_dispatched:
            total_dispatched[tier] += cnt

    # --- Alert matches: distinct alerts that fired for each item ---
    match_rows = db.execute(
        select(Notification.item_id, func.count(func.distinct(Notification.alert_id)))
        .join(Item, Notification.item_id == Item.id)
        .where(Item.channel_id == channel_id, Notification.alert_id.isnot(None))
        .group_by(Notification.item_id)
    ).all()
    matches_by_item = {item_id: cnt for item_id, cnt in match_rows}

    # --- Matching buyers: distinct ACTIVE alerts with >=1 notification ---
    matching_buyers = db.scalar(
        select(func.count(func.distinct(Alert.id)))
        .join(Notification, Notification.alert_id == Alert.id)
        .join(Item, Notification.item_id == Item.id)
        .where(Item.channel_id == channel_id, Alert.is_active == True)
    ) or 0

    for item in channel_items:
        day_counts = spark_by_item.get(item.id, {})
        sparkline = []
        for offset in range(SPARKLINE_DAYS - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            sparkline.append({"date": day, "count": day_counts.get(day, 0)})

        items_out.append({
            "item_id": item.id,
            "title": item.title,
            "image_path": item.image_path,
            "status": item.status,
            "views_total": views_by_item.get(item.id, 0),
            "views_daily": sparkline,
            "alert_matches": matches_by_item.get(item.id, 0),
            "dispatched": dispatched_by_item.get(
                item.id, {"bullseye": 0, "ring": 0}),
        })

    return {
        "items": items_out,
        "matching_buyers": matching_buyers,
        "total_dispatched": total_dispatched,
    }


def _build_pro(db, channel_item_ids, channel_items, now):
    # --- Price positioning: channel items vs same-category median ---
    categories = {i.category for i in channel_items if i.category}
    median_by_cat = {}
    for cat in categories:
        median_by_cat[cat] = db.scalar(
            select(func.percentile_cont(0.5).within_group(Item.price))
            .where(
                Item.category == cat,
                Item.status == "active",
                Item.price.isnot(None),
            )
        )

    price_positioning = []
    for item in channel_items:
        if item.price is None or item.category not in median_by_cat:
            continue
        median = median_by_cat[item.category]
        pct_diff = None
        if median:
            pct_diff = round((item.price - median) / median * 100, 2)
        price_positioning.append({
            "item_id": item.id,
            "median_price": median,
            "pct_diff": pct_diff,
        })

    # --- Category pulse: market-wide new items per week in the seller's categories ---
    week_start = now - timedelta(days=7)
    two_weeks_start = now - timedelta(days=14)
    category_pulse = []
    for cat in sorted(categories):
        this_week = db.scalar(
            select(func.count(Item.id)).where(
                Item.category == cat, Item.created_at >= week_start)
        ) or 0
        last_week = db.scalar(
            select(func.count(Item.id)).where(
                Item.category == cat,
                Item.created_at >= two_weeks_start,
                Item.created_at < week_start,
            )
        ) or 0
        category_pulse.append({
            "category": cat,
            "this_week": this_week,
            "last_week": last_week,
        })

    # --- Top performers: channel items by views, limit 5 ---
    view_rows = db.execute(
        select(UserInteraction.item_id, func.count())
        .where(
            UserInteraction.item_id.in_(channel_item_ids),
            UserInteraction.interaction_type.in_(VIEW_INTERACTION_TYPES),
        )
        .group_by(UserInteraction.item_id)
    ).all()
    views_by_item = {item_id: cnt for item_id, cnt in view_rows}
    ranked = sorted(
        channel_items, key=lambda i: views_by_item.get(i.id, 0), reverse=True
    )
    top_performers = [
        {
            "item_id": item.id,
            "title": item.title,
            "views": views_by_item.get(item.id, 0),
        }
        for item in ranked[:TOP_PERFORMERS_LIMIT]
    ]

    return {
        "price_positioning": price_positioning,
        "category_pulse": category_pulse,
        "top_performers": top_performers,
    }

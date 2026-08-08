"""
NB-51: ops console Section 6 — Monetization (blueprint §2.9).

Boost pricing + demand context, feature toggles, subscription settings,
revenue dashboard, boost moderation (end early). All ops-admin protected;
every mutation goes through record_audit (Rule 1.4).
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_engine.prompts import TAXONOMY_STRUCTURE
from constants import BOOST_PRICE_STARS
from database import get_db
from models import Boost, Channel, Item, Subscription
from schemas import (
    OpsPriceBulkRequest,
    OpsPriceUpdateRequest,
    OpsSettingUpdateRequest,
    OpsToggleUpdateRequest,
)
from services import settings_registry
from services.audit import record_audit
from services.boost import end_boost_for_item
from services.boost_pricing import (
    get_boost_price_by_key,
    invalidate_boost_price_cache,
    set_boost_price,
    set_boost_price_bulk,
)
from services.telegram_payments import star_payments

from .ops_auth import require_ops_admin

logger = logging.getLogger("index_ops_monetization")

router = APIRouter()

_TOGGLES = {
    "monetization_enabled",
    "boost_purchases_enabled",
    "subscription_purchases_enabled",
    "credit_boosts_enabled",
}

_SUBSCRIPTION_KEYS = {
    "alerts_only_price_stars",
    "all_in_one_price_stars",
    "alerts_subscription_extra_alerts",
    "all_in_one_monthly_boost_credit",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _admin_user(request: Request) -> str:
    return request.session.get("ops_admin", {}).get("user", "admin")


# ---------------------------------------------------------------------------
# Prices + demand context
# ---------------------------------------------------------------------------

def _constant_price(category: str) -> int:
    price = BOOST_PRICE_STARS.get(category)
    if not price:
        price = BOOST_PRICE_STARS.get("Other", 25)
    return max(1, int(price))


@router.get("/prices")
def get_prices(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    from models import BoostPrice as _BP

    now = _now_utc()
    week_ago = now - timedelta(days=7)

    # demand context: active + this-week boost counts per (category, subcategory)
    active_rows = db.execute(
        select(Item.category, Item.subcategory, func.count(Boost.id))
        .join(Boost, Boost.item_id == Item.id)
        .where(Boost.ends_at > now)
        .group_by(Item.category, Item.subcategory)
    ).all()
    week_rows = db.execute(
        select(Item.category, Item.subcategory, func.count(Boost.id))
        .join(Boost, Boost.item_id == Item.id)
        .where(Boost.created_at >= week_ago)
        .group_by(Item.category, Item.subcategory)
    ).all()
    active = {(c, s or ""): n for c, s, n in active_rows}
    this_week = {(c, s or ""): n for c, s, n in week_rows}

    # price rows: taxonomy ∪ DB rows; effective price + source per row
    stored = db.execute(
        select(_BP.category, _BP.subcategory, _BP.price_stars)
    ).all()
    stored_map = {(c, s): p for c, s, p in stored}

    categories: list[dict] = []
    seen_cats: set[str] = set()
    for category, subs in TAXONOMY_STRUCTURE.items():
        seen_cats.add(category)
        extra_subs = [
            s for (c, s) in stored_map
            if c == category and s != "" and s not in subs
        ]
        sub_names = [""] + list(subs) + extra_subs
        rows = []
        for s in sub_names:
            price = stored_map.get((category, s))
            rows.append({
                "subcategory": s,
                "price_stars": price if price is not None else _constant_price(category),
                "source": "db" if price is not None else "constant",
                "active_boosts": active.get((category, s), 0),
                "boosts_this_week": this_week.get((category, s), 0),
            })
        categories.append({"category": category, "rows": rows})

    # categories present in the DB but not the taxonomy
    for (c, s) in stored_map:
        if c not in seen_cats:
            seen_cats.add(c)
            categories.append({
                "category": c,
                "rows": [{
                    "subcategory": s,
                    "price_stars": stored_map[(c, s)],
                    "source": "db",
                    "active_boosts": active.get((c, s), 0),
                    "boosts_this_week": this_week.get((c, s), 0),
                }],
            })

    return {"generated_at": now.isoformat(), "categories": categories}


@router.put("/prices/{category}/{subcategory}")
def update_price(
    category: str,
    subcategory: str,
    body: OpsPriceUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if body.price_stars < 1 or body.price_stars > 10000:
        raise HTTPException(status_code=400, detail="price_stars must be between 1 and 10000")
    old = get_boost_price_by_key(db, category, subcategory)
    set_boost_price(
        db, category=category, subcategory=subcategory,
        price_stars=body.price_stars, updated_by=_admin_user(request),
    )
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="update_boost_price",
        section="monetization",
        entity_type="boost_price",
        entity_id=f"{category}/{subcategory}",
        before={"price_stars": old},
        after={"price_stars": body.price_stars},
    )
    return {"category": category, "subcategory": subcategory, "price_stars": body.price_stars}


@router.post("/prices/bulk")
def bulk_update_prices(
    body: OpsPriceBulkRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """set_category / percent / reset over a category (or a single
    subcategory when provided). One audit row per category."""
    from models import BoostPrice as _BP

    # target subcategories: taxonomy ∪ existing DB rows for the category
    subs = list(TAXONOMY_STRUCTURE.get(body.category, []))
    if body.subcategory is not None:
        targets = [body.subcategory]
    else:
        targets = [""] + subs
        extra = db.scalars(
            select(_BP.subcategory).where(
                _BP.category == body.category, _BP.subcategory != ""
            )
        ).all()
        targets += [s for s in extra if s not in targets]

    before_map: dict[str, int] = {}
    after_map: dict[str, int] = {}
    for sub in targets:
        old = get_boost_price_by_key(db, body.category, sub)
        if body.action == "set_category":
            new = int(body.price_stars) if body.price_stars is not None else old
        elif body.action == "percent":
            new = round(old * (100 + (body.percent or 0)) / 100)
        else:  # reset to floor
            new = _constant_price(body.category)
        new = max(1, new)
        set_boost_price_bulk(
            db, category=body.category, subcategory=sub,
            price_stars=new, updated_by=_admin_user(request),
        )
        before_map[sub] = old
        after_map[sub] = new
    invalidate_boost_price_cache()

    record_audit(
        db,
        admin_user=_admin_user(request),
        action="bulk_update_boost_prices",
        section="monetization",
        entity_type="boost_price",
        entity_id=body.category,
        before=before_map,
        after=after_map,
    )
    return {"category": body.category, "updated": len(targets)}


# ---------------------------------------------------------------------------
# Feature toggles
# ---------------------------------------------------------------------------

@router.get("/toggles")
def get_toggles(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    out = []
    for key in sorted(_TOGGLES):
        entry = settings_registry.REGISTRY.get(key, (None, "bool", None, ""))
        out.append({
            "key": key,
            "value": settings_registry.get_setting(db, key),
            "description": entry[3],
        })
    return out


@router.put("/toggles/{key}")
def update_toggle(
    key: str,
    body: OpsToggleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if key not in _TOGGLES:
        raise HTTPException(status_code=404, detail="Unknown toggle")
    old = settings_registry.get_setting(db, key)
    settings_registry.set_setting(db, key, str(body.value))
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="set_toggle",
        section="monetization",
        entity_type="admin_setting",
        entity_id=key,
        before={"value": old},
        after={"value": body.value},
    )
    return {"key": key, "value": body.value}


# ---------------------------------------------------------------------------
# Subscription settings
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_subscription_settings(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    out = []
    for key in sorted(_SUBSCRIPTION_KEYS):
        entry = settings_registry.REGISTRY.get(key, (None, "str", None, ""))
        source = "db" if db.get(settings_registry.AdminSetting, key) is not None else "env"
        out.append({
            "key": key,
            "value": settings_registry.get_setting(db, key),
            "source": source,
            "description": entry[3],
        })
    return out


@router.put("/settings/{key}")
def update_subscription_setting(
    key: str,
    body: OpsSettingUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    if key not in _SUBSCRIPTION_KEYS:
        raise HTTPException(status_code=404, detail="Unknown subscription setting")
    old = settings_registry.get_setting(db, key)
    try:
        settings_registry.set_setting(db, key, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="update_subscription_setting",
        section="monetization",
        entity_type="admin_setting",
        entity_id=key,
        before={"value": old},
        after={"value": body.value},
    )
    return {"key": key, "value": body.value}


# ---------------------------------------------------------------------------
# Revenue dashboard (all real data, §4.4)
# ---------------------------------------------------------------------------

@router.get("/revenue")
async def get_revenue(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    now = _now_utc()
    day = timedelta(days=30)

    try:
        transactions = await star_payments.get_star_transactions(limit=100)
    except Exception as e:
        logger.warning(f"ops/monetization: ledger failed: {e}")
        raise HTTPException(status_code=502, detail=f"Star ledger unavailable: {e}")
    if not isinstance(transactions, list):
        transactions = []

    stars_earned = 0
    tx_count = 0
    for tx in transactions:
        source = tx.get("source") or {}
        if source.get("transaction_type") == "invoice_payment":
            stars_earned += int(tx.get("amount") or 0)
            tx_count += 1

    active_subscriptions = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.status == "active",
            Subscription.current_period_end > now,
        )
    ) or 0
    active_boosts = db.scalar(
        select(func.count(Boost.id)).where(Boost.ends_at > now)
    ) or 0

    expiring_rows = db.execute(
        select(Boost.id, Item.id, Item.title, Boost.ends_at)
        .join(Item, Boost.item_id == Item.id)
        .where(Boost.ends_at > now, Boost.ends_at <= now + timedelta(hours=24))
        .order_by(Boost.ends_at.asc())
    ).all()
    expiring_soon = [
        {
            "boost_id": bid,
            "item_id": iid,
            "title": title,
            "ends_at": ends_at.isoformat(),
        }
        for bid, iid, title, ends_at in expiring_rows
    ]

    return {
        "stars_earned_last_30d": stars_earned,
        "active_subscriptions": active_subscriptions,
        "active_boosts": active_boosts,
        "expiring_soon": expiring_soon,
        "sources": {
            "stars_earned_last_30d": f"getStarTransactions (invoice_payment, {tx_count} txs)",
            "active_subscriptions": "subscriptions table (status=active, period not ended)",
            "active_boosts": "boosts table (ends_at > now)",
            "expiring_soon": "boosts table (ends_at within 24h, joined to items)",
        },
    }


# ---------------------------------------------------------------------------
# Boost moderation (Rule 4.5.1)
# ---------------------------------------------------------------------------

@router.get("/boosts")
def get_active_boosts(db: Session = Depends(get_db), _: None = Depends(require_ops_admin)):
    now = _now_utc()
    rows = db.execute(
        select(Boost, Item, Channel)
        .join(Item, Boost.item_id == Item.id)
        .join(Channel, Boost.channel_id == Channel.id)
        .where(Boost.ends_at > now)
        .order_by(Boost.ends_at.asc())
    ).all()
    return [
        {
            "id": boost.id,
            "item_id": boost.item_id,
            "title": item.title,
            "channel_username": channel.username,
            "source": boost.source,
            "price_paid_stars": boost.price_paid_stars,
            "starts_at": boost.starts_at.isoformat(),
            "ends_at": boost.ends_at.isoformat(),
            "created_at": boost.created_at.isoformat() if boost.created_at else None,
        }
        for boost, item, channel in rows
    ]


@router.post("/boosts/{boost_id}/end")
def end_boost_early(
    boost_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_ops_admin),
):
    """End an active boost immediately — no refunds (Rule 6.1)."""
    boost = db.get(Boost, boost_id)
    if not boost:
        raise HTTPException(status_code=404, detail="Boost not found")
    now = _now_utc()
    if boost.ends_at <= now:
        raise HTTPException(status_code=409, detail="Boost is not active")
    item = db.get(Item, boost.item_id)
    if not item or item.status != "active" or not item.is_active:
        raise HTTPException(status_code=409, detail="Item is not active")

    before_ends_at = boost.ends_at
    end_boost_for_item(db, boost.item_id)  # sets ends_at=now on the active rows
    record_audit(
        db,
        admin_user=_admin_user(request),
        action="end_boost_early",
        section="monetization",
        entity_type="boost",
        entity_id=str(boost_id),
        before={"ends_at": before_ends_at.isoformat()},
        after={"ends_at": now.isoformat()},
    )
    return {"status": "ended", "boost_id": boost_id}

"""
NB-49: the settings registry — the single "effective config" model
(ops-console.md Rule 1.5, blueprint §2.3).

Resolution per registered key: DB row (source='db') → env var
(source='env') → the constant default baked at import time. Reads are
FAIL-OPEN: if the admin_settings table is missing (migration failure),
the SQL error is swallowed and the env default is returned — the
marketplace never crashes on a console regression (blueprint §6).

No imports from other services — cycle-free by construction.
"""

import logging
import os
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AdminSetting
import constants as C

logger = logging.getLogger("index_settings")

# ---------------------------------------------------------------------------
# The registry table: key -> (env var | None, type, default, description)
# Env names and defaults verified against constants.py (blueprint D10).
# ---------------------------------------------------------------------------
REGISTRY: dict[str, tuple[str | None, str, object, str]] = {
    "monetization_enabled": (
        "MONETIZATION_ENABLED", "bool", bool(C.MONETIZATION_ENABLED),
        "Master kill switch for all monetization (503s + UI hide, exactly the env behavior)"),
    "boost_purchases_enabled": (
        None, "bool", True,
        "Allow paid boost purchases (quote + order)"),
    "subscription_purchases_enabled": (
        None, "bool", True,
        "Allow Star subscription purchases (order + status)"),
    "credit_boosts_enabled": (
        None, "bool", True,
        "Allow credit boost redemptions from all-in-one monthly credit"),
    "max_alerts_per_user": (
        "ALERT_MAX_PER_USER", "int", C.MAX_ALERTS_PER_USER,
        "Free-tier alert cap per user"),
    "alert_cap_banner_threshold": (
        "ALERT_CAP_BANNER_THRESHOLD", "int", C.ALERT_CAP_BANNER_THRESHOLD,
        "Cap-awareness banner display threshold (alerts left before the cap)"),
    "alert_max_matches": (
        "ALERT_MAX_MATCHES", "int", C.MAX_MATCHES_BEFORE_PAUSE,
        "Match count before an alert auto-pauses"),
    "alert_max_bullseye": (
        "ALERT_MAX_BULLSEYE", "int", C.MAX_BULLSEYE_BEFORE_PAUSE,
        "Bullseye match count before an alert auto-pauses"),
    "notification_throttle_seconds": (
        "ALERT_THROTTLE_SECONDS", "int", C.NOTIFICATION_THROTTLE_SECONDS,
        "Minimum seconds between alert notifications"),
    "alert_lifespan_days": (
        "ALERT_LIFESPAN_DAYS", "int", C.ALERT_LIFESPAN_DAYS,
        "Alert expiry after creation"),
    "boost_rotation_minutes": (
        "BOOST_ROTATION_MINUTES", "int", C.BOOST_ROTATION_MINUTES,
        "Pinned-boost rotation window"),
    "alert_retention_days": (
        "ALERT_RETENTION_DAYS", "int", C.ALERT_RETENTION_DAYS,
        "Purge age for dead alerts"),
    "notification_retention_days": (
        "NOTIFICATION_RETENTION_DAYS", "int", C.NOTIFICATION_RETENTION_DAYS,
        "Purge age for terminal notifications"),
    "soft_deleted_retention_days": (
        "SOFT_DELETED_RETENTION_DAYS", "int", C.SOFT_DELETED_RETENTION_DAYS,
        "Soft-deleted item retention"),
    "reported_sold_retention_days": (
        "REPORTED_SOLD_RETENTION_DAYS", "int", C.REPORTED_SOLD_RETENTION_DAYS,
        "Reported-sold item retention"),
    "stale_item_days": (
        "STALE_ITEM_DAYS", "int", C.STALE_ITEM_DAYS,
        "Zero-interaction staleness window"),
    "alerts_only_price_stars": (
        "ALERTS_ONLY_PRICE_STARS", "int", C.ALERTS_ONLY_PRICE_STARS,
        "Alerts-only subscription price (Stars)"),
    "all_in_one_price_stars": (
        "ALL_IN_ONE_PRICE_STARS", "int", C.ALL_IN_ONE_PRICE_STARS,
        "All-in-one subscription price (Stars)"),
    "alerts_subscription_extra_alerts": (
        "ALERTS_SUBSCRIPTION_EXTRA_ALERTS", "int", C.ALERTS_SUBSCRIPTION_EXTRA_ALERTS,
        "Extra alert allowance for subscribers"),
    "all_in_one_monthly_boost_credit": (
        "ALL_IN_ONE_MONTHLY_BOOST_CREDIT", "int", C.ALL_IN_ONE_MONTHLY_BOOST_CREDIT,
        "Monthly boost credit for all-in-one subscribers"),
}

_CASTERS = {
    "bool": lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
    "int": int,
    "float": float,
    "json": lambda v: json.loads(v) if isinstance(v, str) else v,
    "str": str,
}


def _cast_value(value, type_name: str):
    """Cast a raw string/primitive per the registry type. Raises
    ValueError/TypeError on malformed input (route translates to 400)."""
    caster = _CASTERS.get(type_name, _CASTERS["str"])
    return caster(value)


def get_setting(db: Session, key: str, *, env_default=None, cast=None):
    """Live value for a setting: DB row → env var → constant default.

    Registered keys resolve their env name/type/default from REGISTRY;
    `env_default`/`cast` are the escape hatch for ad-hoc keys. Reads are
    fail-open — a missing admin_settings table returns the env default.
    """
    entry = REGISTRY.get(key)
    if entry is not None:
        env_name, type_name, default, _desc = entry
        caster = cast or (lambda v: _cast_value(v, type_name))
    else:
        # Ad-hoc key: env lookup by the uppercase convention (escape hatch)
        env_name, type_name = key.upper(), "str"
        default = env_default
        caster = cast or _CASTERS["str"]

    # 1. DB row (fail-open on any SQL error)
    try:
        row = db.get(AdminSetting, key)
    except Exception as e:  # pragma: no cover - table missing
        logger.warning(f"settings_registry: read failed for {key!r}: {e}")
        row = None
    if row is not None:
        try:
            return caster(row.value)
        except (ValueError, TypeError):
            logger.warning(f"settings_registry: corrupt row value for {key!r} — falling through")

    # 2. env var
    raw = os.getenv(env_name) if env_name is not None else None
    if raw is not None:
        try:
            return caster(raw)
        except (ValueError, TypeError):
            logger.warning(f"settings_registry: unparseable env {env_name}={raw!r} — using default")

    # 3. constant default
    return default


def set_setting(db: Session, key: str, value, *, cast=None) -> AdminSetting:
    """Upsert a DB override (source='db'). The raw string is stored; the
    registered type validates BEFORE the write (ValueError → route 400).
    No audit here — routes audit."""
    entry = REGISTRY.get(key)
    if entry is None:
        raise ValueError(f"Unknown setting key: {key}")
    _env, type_name, _default, desc = entry
    caster = cast or (lambda v: _cast_value(v, type_name))
    caster(value)  # validate before write

    row = db.get(AdminSetting, key)
    if row is None:
        row = AdminSetting(key=key, value=str(value), type=type_name, source="db", description=desc)
        db.add(row)
    else:
        row.value = str(value)
    db.commit()
    db.refresh(row)
    return row


def list_settings(db: Session | None = None) -> list[dict]:
    """The effective-config view: [{key, type, value: live, source,
    description}] for every registered key. When called without a session
    (the route contract), a short-lived session is opened."""
    own_session = db is None
    if own_session:
        from database import SessionLocal
        db = SessionLocal()
    try:
        rows_out = []
        for key, (_env, type_name, _default, desc) in REGISTRY.items():
            try:
                source = "db" if db.get(AdminSetting, key) is not None else "env"
            except Exception:  # table missing — fail-open to env source
                source = "env"
            rows_out.append({
                "key": key,
                "type": type_name,
                "value": get_setting(db, key),
                "source": source,
                "description": desc,
            })
        return rows_out
    finally:
        if own_session:
            db.close()

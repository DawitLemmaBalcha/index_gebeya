"""
Shared configuration constants for the Alert Guardrails system (TECH-20).

All values are read from environment variables at module load time,
with sensible defaults. Zero means "disabled" (no limit/throttle/pause).

Consumed by:
  - backend/services/alerting.py
  - backend/api/routes/alerts.py
  - backend/ai_engine/matcher.py
  - backend/services/search.py
"""

import os
import logging
import json
from typing import Any, Union

logger = logging.getLogger("index_alerts")


def _get_config(key: str, default: Union[int, float], cast: type) -> Union[int, float]:
    """
    Read an environment variable, parse it, and apply guardrail rules:
    - None/missing → return default
    - Non-numeric string → warn and return default
    - Negative value → return 0 (disabled)
    - Otherwise → return the cast value
    """
    raw = os.getenv(key)
    if raw is None:
        return default

    try:
        if cast is int:
            val = int(raw)
        elif cast is float:
            val = float(raw)
        else:
            val = cast(raw)
    except (ValueError, TypeError):
        logger.warning(
            f"constants: Could not parse env var {key}={raw!r}, "
            f"falling back to default {default}"
        )
        return default

    if val < 0:
        logger.info(f"constants: {key}={val} → clamped to 0 (disabled)")
        return 0

    return val


def _get_json_config(key: str, default: dict) -> dict:
    """
    Read a JSON object from an environment variable (blueprint D4).

    The generic cast fallback of _get_config cannot parse dicts (its negative
    clamp is meaningless for them), so monetization JSON config (BOOST_PRICE_STARS)
    gets this dedicated helper: json.loads on success, warn-and-fallback to the
    default on ValueError/TypeError/None. No clamp.
    """
    raw = os.getenv(key)
    if raw is None:
        return default

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"{key} must decode to a JSON object")
        return parsed
    except (ValueError, TypeError):
        logger.warning(
            f"constants: Could not parse env var {key}={raw!r}, "
            f"falling back to default {default}"
        )
        return default


# --- Alert Rate Limits ---
MAX_ALERTS_PER_USER: int = _get_config("ALERT_MAX_PER_USER", 20, int)
MAX_MATCHES_BEFORE_PAUSE: int = _get_config("ALERT_MAX_MATCHES", 10, int)
MAX_BULLSEYE_BEFORE_PAUSE: int = _get_config("ALERT_MAX_BULLSEYE", 3, int)

# --- Throttle ---
NOTIFICATION_THROTTLE_SECONDS: int = _get_config("ALERT_THROTTLE_SECONDS", 3600, int)

# --- Expiry ---
ALERT_LIFESPAN_DAYS: int = _get_config("ALERT_LIFESPAN_DAYS", 14, int)

# --- Matching ---
RING_TOLERANCE: float = _get_config("ALERT_RING_TOLERANCE", 0.05, float)
TIER_1_THRESHOLD: float = _get_config("ALERT_BULLSEYE_THRESHOLD", 0.82, float)
TIER_2_THRESHOLD: float = _get_config("ALERT_RING_THRESHOLD", 0.55, float)

# --- Search ---
SEMANTIC_WEIGHT: float = _get_config("SEARCH_SEMANTIC_WEIGHT", 0.6, float)
LEXICAL_WEIGHT: float = _get_config("SEARCH_LEXICAL_WEIGHT", 0.4, float)
DEFAULT_RESULT_LIMIT: int = _get_config("SEARCH_RESULT_LIMIT", 20, int)

# --- Sold Reports & Cleanup (TECH-22) ---
CROWDSOURCE_SOLD_THRESHOLD: int = _get_config("CROWDSOURCE_SOLD_THRESHOLD", 3, int)
SOFT_DELETED_RETENTION_DAYS: int = _get_config("SOFT_DELETED_RETENTION_DAYS", 30, int)
REPORTED_SOLD_RETENTION_DAYS: int = _get_config("REPORTED_SOLD_RETENTION_DAYS", 7, int)
STALE_ITEM_DAYS: int = _get_config("STALE_ITEM_DAYS", 14, int)

# --- Anomaly Radar (NB-57) — plain env-overridable constants in v1 ---
# (documented: a settings-registry pass is a future package if the operator
# wants live radar tuning — blueprint §6.)
RADAR_SCAM_CHANNEL_MAX_TRUST: float = _get_config("RADAR_SCAM_CHANNEL_MAX_TRUST", 2.0, float)
RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X: float = _get_config("RADAR_SCAM_CHANNEL_PRICE_OUTLIER_X", 3.0, float)
RADAR_SCAM_CHANNEL_MIN_REPORTS: int = _get_config("RADAR_SCAM_CHANNEL_MIN_REPORTS", 2, int)
RADAR_PRICE_ANOMALY_MAX_X_MEDIAN: float = _get_config("RADAR_PRICE_ANOMALY_MAX_X_MEDIAN", 10.0, float)
RADAR_DEAD_CHAT_SEVERITY_MEDIUM: int = _get_config("RADAR_DEAD_CHAT_SEVERITY_MEDIUM", 1, int)
RADAR_DEAD_CHAT_SEVERITY_HIGH: int = _get_config("RADAR_DEAD_CHAT_SEVERITY_HIGH", 3, int)

# --- Retention (TECH-25) ---
ALERT_RETENTION_DAYS: int = _get_config("ALERT_RETENTION_DAYS", 30, int)
NOTIFICATION_RETENTION_DAYS: int = _get_config("NOTIFICATION_RETENTION_DAYS", 90, int)

# --- Monetization (NB-43..NB-47) ---
BOOST_DURATION_DAYS: int = _get_config("BOOST_DURATION_DAYS", 7, int)
BOOST_ROTATION_MINUTES: int = _get_config("BOOST_ROTATION_MINUTES", 30, int)
BOOST_PRICE_STARS: dict = _get_json_config("BOOST_PRICE_STARS", {
    "Mobile Phones": 150,
    "Laptops & Computers": 120,
    "Tablets": 100,
    "Electronics": 80,
    "Vehicles": 200,
    "Property": 250,
    "Home, Appliances & Furniture": 50,
    "Men's Fashion": 40,
    "Women's Fashion": 40,
    "Shoes": 40,
    "Health & Beauty": 40,
    "Commercial & Tools": 60,
    "Sports, Arts & Outdoors": 40,
    "Babies & Kids": 30,
    "Animals & Pets": 30,
    "Agriculture & Food": 40,
    "Services": 30,
    "Other": 25,
})
ALERTS_ONLY_PRICE_STARS: int = _get_config("ALERTS_ONLY_PRICE_STARS", 30, int)
ALL_IN_ONE_PRICE_STARS: int = _get_config("ALL_IN_ONE_PRICE_STARS", 100, int)
ALERTS_SUBSCRIPTION_EXTRA_ALERTS: int = _get_config("ALERTS_SUBSCRIPTION_EXTRA_ALERTS", 10, int)
ALL_IN_ONE_MONTHLY_BOOST_CREDIT: int = _get_config("ALL_IN_ONE_MONTHLY_BOOST_CREDIT", 2, int)
MONETIZATION_ENABLED: int = _get_config("MONETIZATION_ENABLED", 1, int)  # 0 = kill switch
# NB-48: cap-awareness banner shows when the seller is within this many
# active alerts of the effective cap (frontend display threshold).
ALERT_CAP_BANNER_THRESHOLD: int = _get_config("ALERT_CAP_BANNER_THRESHOLD", 2, int)
SUBSCRIPTION_PERIOD_SECONDS: int = 2592000  # HARD-LOCKED by Telegram (30d); NO env override

# NB-54: the Mini App origin for the support-toolkit deep-link generator
# (mirrors listener/config.py WEB_APP_URL; patterns verified: worker.py:110,
# App.jsx:51).
WEB_APP_URL: str = os.getenv("WEB_APP_URL", "https://indexgebeya.cfd")

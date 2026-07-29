"""
Shared configuration constants for the Alert Guardrails system (TECH-20).

All values are read from environment variables at module load time,
with sensible defaults. Zero means "disabled" (no limit/throttle/pause).

Consumed by:
  - backend/services/alerting.py
  - backend/api/routes/alerts.py
  - backend/ai_engine/matcher.py
"""

import os
import logging
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

# --- Sold Reports & Cleanup (TECH-22) ---
CROWDSOURCE_SOLD_THRESHOLD: int = _get_config("CROWDSOURCE_SOLD_THRESHOLD", 3, int)
SOFT_DELETED_RETENTION_DAYS: int = _get_config("SOFT_DELETED_RETENTION_DAYS", 30, int)
REPORTED_SOLD_RETENTION_DAYS: int = _get_config("REPORTED_SOLD_RETENTION_DAYS", 7, int)
STALE_ITEM_DAYS: int = _get_config("STALE_ITEM_DAYS", 14, int)

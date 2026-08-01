"""
TECH-25: Alert & Notification Retention Lifecycle tests.

Interface-level tests through run_daily_cleanup() (seeding via the db_session
fixture, assertions re-query via db_session — cleanup's own SessionLocal sees
the same suq_test_db). Retention constants are patched as module-level names
bound in services.cleanup (house monkeypatch pattern, test_auth/test_item_status).

Coverage:
  1. Active alerts survive the purge.
  2. Paused alerts survive the purge (THE regression guard — protection is
     structural: deleted_at NULL + future expires_at match neither branch).
  3. Deleted alerts purge after retention; their notifications cascade-delete
     at the database level (ON DELETE CASCADE).
  4. Expired alerts purge after retention (expiry remains absolute).
  5. ALERT_RETENTION_DAYS <= 0 disables the alert purge (safe-by-default).
  6. PENDING notifications are never purged; SENT/FAILED/REPLACED are.
  7. NOTIFICATION_RETENTION_DAYS <= 0 disables the notification purge.
  8. DELETE /alerts/{id} sets deleted_at (direct route-function call).
  9. Summary dict contains exactly the 5 documented keys.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, text
from fastapi import BackgroundTasks

from models import Alert, Notification, Item, User, Channel
from services.cleanup import run_daily_cleanup
from constants import ALERT_RETENTION_DAYS, NOTIFICATION_RETENTION_DAYS
from api.routes.alerts import delete_alert


# =========================================================================
# SCHEMA GUARD
# =========================================================================

@pytest.fixture(scope="session", autouse=True)
def _ensure_alert_fk_cascade(_test_db_schema):
    """
    The cascade assertion (test 3) depends on the test-DB
    notifications_alert_id_fkey being ON DELETE CASCADE. conftest's create_all
    builds it from the model on a fresh DB, but a pre-existing constraint
    (leftover from an earlier session) would still be RESTRICT. Mirror the
    idempotent TECH-25 migration from main.py: drop (guarded on pg_constraint)
    + re-add with CASCADE. No-op churn when the constraint already cascades.
    """
    from database import engine
    with engine.begin() as conn:
        conn.execute(text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname = 'notifications_alert_id_fkey' "
            "AND conrelid = 'notifications'::regclass) THEN "
            "ALTER TABLE notifications DROP CONSTRAINT notifications_alert_id_fkey; "
            "END IF; END $$;"
        ))
        conn.execute(text(
            "ALTER TABLE notifications ADD CONSTRAINT notifications_alert_id_fkey "
            "FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE"
        ))


# =========================================================================
# TEST HELPERS
# =========================================================================

def _make_user(db_session, tg_id):
    user = User(telegram_id=tg_id)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_alert(db_session, user, *, is_active=True, expires_at=None, deleted_at=None):
    alert = Alert(
        user_id=user.id,
        query_text="tech25 retention query",
        query_vector=None,
        preferences="{}",
        best_opportunity_score=0.0,
        expires_at=expires_at,
        is_active=is_active,
        deleted_at=deleted_at,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def _make_notification(db_session, user, alert_id=None, status="SENT", created_at=None):
    notif = Notification(
        user_id=user.id,
        alert_id=alert_id,
        match_tier="bullseye",
        match_score=0.9,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(notif)
    db_session.commit()
    db_session.refresh(notif)
    return notif


def _alert_count(db_session, alert_id):
    return db_session.scalar(
        select(func.count()).select_from(Alert).where(Alert.id == alert_id)
    )


def _notification_count(db_session, notif_id):
    return db_session.scalar(
        select(func.count()).select_from(Notification).where(Notification.id == notif_id)
    )


# =========================================================================
# PHASE 4 — ALERT PURGE
# =========================================================================

def test_purge_skips_active_alerts(db_session, monkeypatch):
    """Active alert with future expiry and NULL deleted_at survives the purge."""
    monkeypatch.setattr("services.cleanup.ALERT_RETENTION_DAYS", 1)
    user = _make_user(db_session, 40001)
    alert = _make_alert(
        db_session, user,
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )

    run_daily_cleanup()

    assert _alert_count(db_session, alert.id) == 1


def test_purge_protects_paused_alerts(db_session, monkeypatch):
    """THE regression guard: a paused alert (deleted_at NULL, future expiry)
    matches neither purge branch and must never be purged."""
    monkeypatch.setattr("services.cleanup.ALERT_RETENTION_DAYS", 1)
    user = _make_user(db_session, 40002)
    alert = _make_alert(
        db_session, user,
        is_active=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )

    run_daily_cleanup()

    assert _alert_count(db_session, alert.id) == 1


def test_purge_removes_deleted_alerts_after_retention(db_session, monkeypatch):
    """Deleted alert (deleted_at past retention) is purged, and its
    notifications are cascade-deleted at the DB level (ON DELETE CASCADE)."""
    monkeypatch.setattr("services.cleanup.ALERT_RETENTION_DAYS", 1)
    user = _make_user(db_session, 40003)
    alert = _make_alert(
        db_session, user,
        is_active=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        deleted_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    _make_notification(
        db_session, user,
        alert_id=alert.id,
        status="SENT",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    alert_id = alert.id  # capture before the purge — the row will be gone after

    run_daily_cleanup()

    assert _alert_count(db_session, alert_id) == 0
    assert db_session.scalar(
        select(func.count()).select_from(Notification).where(Notification.alert_id == alert_id)
    ) == 0


def test_purge_removes_expired_alerts_after_retention(db_session, monkeypatch):
    """Active alert whose expires_at passed retention is purged
    (expiry remains absolute — an alert that expired while paused is still dead)."""
    monkeypatch.setattr("services.cleanup.ALERT_RETENTION_DAYS", 1)
    user = _make_user(db_session, 40004)
    alert = _make_alert(
        db_session, user,
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=2),
    )

    run_daily_cleanup()

    assert _alert_count(db_session, alert.id) == 0


def test_retention_disabled_at_zero(db_session, monkeypatch):
    """ALERT_RETENTION_DAYS <= 0 disables the alert purge entirely
    (safe-by-default — no retention, no deletion)."""
    monkeypatch.setattr("services.cleanup.ALERT_RETENTION_DAYS", 0)
    user = _make_user(db_session, 40005)
    alert = _make_alert(
        db_session, user,
        is_active=False,
        deleted_at=datetime.now(timezone.utc) - timedelta(days=30),
    )

    run_daily_cleanup()

    assert _alert_count(db_session, alert.id) == 1


# =========================================================================
# PHASE 5 — NOTIFICATION RETENTION
# =========================================================================

def test_pending_notifications_never_purged(db_session, monkeypatch):
    """PENDING survives any age; only terminal SENT/FAILED/REPLACED older
    than the retention window are purged (explicit IN list — never != PENDING)."""
    monkeypatch.setattr("services.cleanup.NOTIFICATION_RETENTION_DAYS", 1)
    user = _make_user(db_session, 40006)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    pending = _make_notification(db_session, user, status="PENDING", created_at=old)
    sent = _make_notification(db_session, user, status="SENT", created_at=old)
    failed = _make_notification(db_session, user, status="FAILED", created_at=old)
    replaced = _make_notification(db_session, user, status="REPLACED", created_at=old)
    # Capture ids before the purge — purged rows must not be touched after.
    pending_id, sent_id, failed_id, replaced_id = pending.id, sent.id, failed.id, replaced.id

    run_daily_cleanup()

    assert _notification_count(db_session, pending_id) == 1
    assert _notification_count(db_session, sent_id) == 0
    assert _notification_count(db_session, failed_id) == 0
    assert _notification_count(db_session, replaced_id) == 0


def test_notification_retention_disabled_at_zero(db_session, monkeypatch):
    """NOTIFICATION_RETENTION_DAYS <= 0 disables the notification purge."""
    monkeypatch.setattr("services.cleanup.NOTIFICATION_RETENTION_DAYS", 0)
    user = _make_user(db_session, 40007)
    sent = _make_notification(
        db_session, user,
        status="SENT",
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
    )

    run_daily_cleanup()

    assert _notification_count(db_session, sent.id) == 1


# =========================================================================
# ROUTE SIDE-EFFECT — delete_alert sets deleted_at
# =========================================================================

class _FakeRequest:
    """Minimal Request stub exposing headers (used for the analytics call)."""

    def __init__(self):
        self.headers = {}


def test_delete_alert_sets_deleted_at(db_session):
    """Direct route-function call (internal-bypass auth): delete_alert sets
    deleted_at alongside is_active=False, persisted before the commit."""
    user = _make_user(db_session, 333)
    alert = _make_alert(
        db_session, user,
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    assert alert.deleted_at is None

    delete_alert(
        alert.id,
        "333",
        _FakeRequest(),
        BackgroundTasks(),
        db=db_session,
        x_internal_service="index-listener",
    )

    assert alert.deleted_at is not None
    assert alert.is_active is False
    # Persisted: re-query through SQL.
    reloaded = db_session.scalar(select(Alert).where(Alert.id == alert.id))
    assert reloaded is not None
    assert reloaded.deleted_at is not None


# =========================================================================
# SUMMARY DICT
# =========================================================================

def test_summary_dict_keys(db_session):
    """run_daily_cleanup() returns exactly the 5 documented summary keys."""
    summary = run_daily_cleanup()

    assert set(summary.keys()) == {
        "soft_deleted_removed",
        "reported_sold_removed",
        "stale_flagged",
        "alerts_purged",
        "notifications_purged",
    }

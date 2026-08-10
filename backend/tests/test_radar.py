"""
NB-57: the Anomaly Radar — computed problems with action chaining (Rule 4).

Covers: the five detections firing on seeded data (dead-chat buyers,
judge-error spikes, report spikes, scam-pattern channels, price anomalies),
every action verb (retry, clear-reports, pause, hide, ban owner), dismissal
persistence across get_radar calls, the notification FAILED endpoint
(PENDING→200 / terminal→409), and the listener poller's consecutive-
failure marking at NOTIFICATION_FAILURE_LIMIT.

NOTE: the retry verb (POST /ops/actions/notifications/{id}/retry) is defined
by NB-59 (P5) — the radar references the shared verb registry (blueprint
§5.2). This suite exercises it as part of the radar action chain.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from constants import CROWDSOURCE_SOLD_THRESHOLD
from database import get_db
from models import (
    AuditLog,
    Channel,
    Item,
    Notification,
    RadarDismissal,
    SoldReport,
    User,
)

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")


def _user(db, telegram_id=111, banned=False):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", banned=banned)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _channel(db, username, owner_tg=None, trust_score=0.0):
    channel = Channel(
        username=username, title=username, registered_by=owner_tg,
        trust_score=trust_score, indexing_paused=False, is_active=True,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _item(db, channel, *, title="iPhone 13", price=100.0, category="Mobile Phones",
          status="active", is_active=True):
    item = Item(
        channel_id=channel.id, title=title, price=price, category=category,
        subcategory="General", status=status, is_active=is_active,
        image_path="x.jpg", specs="{}",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _sold_reports(db, item, user, count):
    for i in range(count):
        reporter = _user(db, telegram_id=user.telegram_id + i + 1)
        db.add(SoldReport(user_id=reporter.id, item_id=item.id))
    db.commit()


def _failed_notifications(db, user, count):
    for i in range(count):
        db.add(Notification(
            user_id=user.id, item_id=None, alert_id=None,
            match_tier="bullseye", match_score=1.0, status="FAILED",
        ))
    db.commit()


def _ops_client(db_session):
    from api.routes import ops_auth, ops_finalize

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="t", session_cookie="ops_session")
    app.include_router(ops_auth.router, prefix="/ops/auth")
    app.include_router(ops_finalize.router, prefix="/ops")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    resp = client.post(
        "/ops/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    assert resp.status_code == 200
    return client


def _notifications_client(db_session):
    from api.routes import notifications as notif_route

    app = FastAPI()
    app.include_router(notif_route.router, prefix="/notifications")

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def _anomalies_of(db_session, type_):
    from services.radar import get_radar

    return [a for a in get_radar(db_session)["anomalies"] if a["type"] == type_]


# ---------------------------------------------------------------------------
# The FAILED-status instrumentation (honest dead-chat rows, blueprint §3.4)
# ---------------------------------------------------------------------------
class TestFailEndpoint:
    def test_pending_to_failed_and_terminal_409(self, db_session):
        user = _user(db_session)
        notif = Notification(
            user_id=user.id, item_id=None, alert_id=None,
            match_tier="bullseye", match_score=1.0, status="PENDING",
        )
        db_session.add(notif)
        db_session.commit()
        sent = Notification(
            user_id=user.id, item_id=None, alert_id=None,
            match_tier="bullseye", match_score=1.0, status="SENT",
        )
        db_session.add(sent)
        db_session.commit()
        client = _notifications_client(db_session)

        resp = client.post(f"/notifications/{notif.id}/fail")
        assert resp.status_code == 200
        assert resp.json() == {"status": "failed"}
        db_session.expire_all()
        assert db_session.get(Notification, notif.id).status == "FAILED"

        # terminal → 409 (already FAILED)
        resp = client.post(f"/notifications/{notif.id}/fail")
        assert resp.status_code == 409

        # SENT → 409
        resp = client.post(f"/notifications/{sent.id}/fail")
        assert resp.status_code == 409

        # unknown → 404
        resp = client.post("/notifications/99999/fail")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Detection 1: dead-chat buyers
# ---------------------------------------------------------------------------
class TestDetectDeadChatBuyers:
    def test_medium_severity_below_high_threshold(self, db_session):
        user = _user(db_session, telegram_id=201)
        _failed_notifications(db_session, user, 2)
        anomalies = _anomalies_of(db_session, "dead_chat_buyer")
        assert len(anomalies) == 1
        assert anomalies[0]["entity_id"] == "201"
        assert anomalies[0]["severity"] == "medium"
        assert any(a["verb"] == "Retry delivery" for a in anomalies[0]["actions"])

    def test_high_severity_at_threshold(self, db_session):
        user = _user(db_session, telegram_id=202)
        _failed_notifications(db_session, user, 3)
        anomalies = _anomalies_of(db_session, "dead_chat_buyer")
        assert anomalies[0]["severity"] == "high"

    def test_no_failed_rows_no_anomaly(self, db_session):
        user = _user(db_session, telegram_id=203)
        db_session.add(Notification(
            user_id=user.id, item_id=None, alert_id=None,
            match_tier="bullseye", match_score=1.0, status="PENDING",
        ))
        db_session.commit()
        assert _anomalies_of(db_session, "dead_chat_buyer") == []


# ---------------------------------------------------------------------------
# Detection 2: judge-error spikes (process-local counters)
# ---------------------------------------------------------------------------
class TestDetectJudgeErrors:
    def test_fires_when_counter_nonzero(self, db_session, monkeypatch):
        from services import alerting

        monkeypatch.setattr(alerting, "JUDGE_ERROR_COUNT", 4)
        monkeypatch.setattr(
            alerting, "JUDGE_ERROR_LAST_TS", datetime.now(timezone.utc)
        )
        anomalies = _anomalies_of(db_session, "judge_error_spike")
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "medium"
        assert "4" in anomalies[0]["summary"]
        # dismiss-only: no kill-switch action exists (v1 locked decision)
        verbs = [a["verb"] for a in anomalies[0]["actions"]]
        assert verbs == ["Dismiss"]

    def test_silent_when_counter_zero(self, db_session, monkeypatch):
        from services import alerting

        monkeypatch.setattr(alerting, "JUDGE_ERROR_COUNT", 0)
        assert _anomalies_of(db_session, "judge_error_spike") == []


# ---------------------------------------------------------------------------
# Detection 3: report spikes (at/near the take-down threshold)
# ---------------------------------------------------------------------------
class TestDetectReportSpikes:
    def test_near_threshold_medium(self, db_session):
        user = _user(db_session, telegram_id=301)
        ch = _channel(db_session, "ch_spike_near")
        item = _item(db_session, ch)
        _sold_reports(db_session, item, user, CROWDSOURCE_SOLD_THRESHOLD - 1)
        anomalies = _anomalies_of(db_session, "report_spike")
        assert len(anomalies) == 1
        assert anomalies[0]["entity_id"] == str(item.id)
        assert anomalies[0]["severity"] == "medium"
        verbs = [a["verb"] for a in anomalies[0]["actions"]]
        assert "Clear reports" in verbs
        assert "View item" in verbs

    def test_at_threshold_high(self, db_session):
        user = _user(db_session, telegram_id=302)
        ch = _channel(db_session, "ch_spike_at")
        item = _item(db_session, ch)
        _sold_reports(db_session, item, user, CROWDSOURCE_SOLD_THRESHOLD)
        anomalies = _anomalies_of(db_session, "report_spike")
        assert anomalies[0]["severity"] == "high"

    def test_inactive_item_not_flagged(self, db_session):
        user = _user(db_session, telegram_id=303)
        ch = _channel(db_session, "ch_spike_inactive")
        item = _item(db_session, ch, status="reported_sold")
        _sold_reports(db_session, item, user, CROWDSOURCE_SOLD_THRESHOLD)
        assert _anomalies_of(db_session, "report_spike") == []


# ---------------------------------------------------------------------------
# Detection 4: scam-pattern channels (low trust + price outlier + reports)
# ---------------------------------------------------------------------------
class TestDetectScamChannels:
    def test_fires_on_composite_watchlist(self, db_session):
        user = _user(db_session, telegram_id=401)
        # owner id must not collide with the reporter ids _sold_reports
        # derives from the reporter base id (base+1, base+2)
        owner = _user(db_session, telegram_id=901)
        ch = _channel(db_session, "ch_scam", owner_tg=901, trust_score=1.5)
        # category median = 100 (two priced peers)
        _item(db_session, ch, title="Peer A", price=100.0)
        _item(db_session, ch, title="Peer B", price=100.0)
        outlier = _item(db_session, ch, title="Outlier", price=1000.0)
        _sold_reports(db_session, outlier, user, 2)

        anomalies = _anomalies_of(db_session, "scam_pattern_channel")
        assert len(anomalies) == 1
        assert anomalies[0]["entity_id"] == str(ch.id)
        assert anomalies[0]["severity"] == "high"
        verbs = [a["verb"] for a in anomalies[0]["actions"]]
        assert "Pause indexing" in verbs
        assert "Ban owner" in verbs

    def test_high_trust_channel_not_flagged(self, db_session):
        user = _user(db_session, telegram_id=403)
        ch = _channel(db_session, "ch_clean_trust", trust_score=4.8)
        _item(db_session, ch, title="Peer A", price=100.0)
        _item(db_session, ch, title="Peer B", price=100.0)
        outlier = _item(db_session, ch, title="Outlier", price=1000.0)
        _sold_reports(db_session, outlier, user, 2)
        assert _anomalies_of(db_session, "scam_pattern_channel") == []

    def test_low_report_count_not_flagged(self, db_session):
        user = _user(db_session, telegram_id=404)
        ch = _channel(db_session, "ch_scam_lowreports", trust_score=1.5)
        _item(db_session, ch, title="Peer A", price=100.0)
        _item(db_session, ch, title="Peer B", price=100.0)
        outlier = _item(db_session, ch, title="Outlier", price=1000.0)
        _sold_reports(db_session, outlier, user, 1)
        assert _anomalies_of(db_session, "scam_pattern_channel") == []


# ---------------------------------------------------------------------------
# Detection 5: price anomalies (0 ETB and >= 10x category median)
# ---------------------------------------------------------------------------
class TestDetectPriceAnomalies:
    def test_zero_price_medium(self, db_session):
        ch = _channel(db_session, "ch_zero")
        item = _item(db_session, ch, price=0.0)
        anomalies = _anomalies_of(db_session, "price_anomaly")
        assert any(a["entity_id"] == str(item.id) and a["severity"] == "medium"
                   for a in anomalies)

    def test_outlier_vs_median_high(self, db_session):
        ch = _channel(db_session, "ch_outlier")
        _item(db_session, ch, title="Peer A", price=100.0)
        _item(db_session, ch, title="Peer B", price=100.0)
        item = _item(db_session, ch, title="10x", price=1500.0)
        anomalies = _anomalies_of(db_session, "price_anomaly")
        assert any(a["entity_id"] == str(item.id) and a["severity"] == "high"
                   for a in anomalies)

    def test_reasonable_price_not_flagged(self, db_session):
        ch = _channel(db_session, "ch_reasonable")
        _item(db_session, ch, title="Peer A", price=100.0)
        _item(db_session, ch, title="Peer B", price=100.0)
        _item(db_session, ch, title="In range", price=300.0)
        assert _anomalies_of(db_session, "price_anomaly") == []


# ---------------------------------------------------------------------------
# Dismissal persistence
# ---------------------------------------------------------------------------
class TestDismiss:
    def test_dismiss_persists_across_get_radar_calls(self, db_session):
        from services.radar import get_radar, dismiss

        user = _user(db_session, telegram_id=501)
        _failed_notifications(db_session, user, 3)

        before = get_radar(db_session)["anomalies"]
        assert len(before) == 1

        dismiss(db_session, "dead_chat_buyer", "501", dismissed_by="admin")
        after = get_radar(db_session)["anomalies"]
        assert after == []

        # the dismissal row persists
        row = db_session.scalar(select(RadarDismissal))
        assert row is not None
        assert row.type == "dead_chat_buyer"
        assert row.entity_id == "501"
        assert row.dismissed_by == "admin"

    def test_resolve_endpoint_and_audit(self, db_session):
        user = _user(db_session, telegram_id=502)
        _failed_notifications(db_session, user, 3)
        client = _ops_client(db_session)

        resp = client.post("/ops/radar/resolve", json={
            "type": "dead_chat_buyer", "entity_id": "502",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "dismissed"}

        from services.radar import get_radar

        assert get_radar(db_session)["anomalies"] == []
        audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "dismiss_anomaly"))
        assert audit is not None
        assert audit.section == "trust"


# ---------------------------------------------------------------------------
# Radar action verbs
# ---------------------------------------------------------------------------
class TestRadarActions:
    def test_clear_reports_deletes_directly_without_owner_gate(self, db_session):
        user = _user(db_session, telegram_id=601)
        ch = _channel(db_session, "ch_actions_clear")
        item = _item(db_session, ch)
        _sold_reports(db_session, item, user, 3)
        client = _ops_client(db_session)

        resp = client.post(f"/ops/radar/items/{item.id}/clear-reports")
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] == 3
        assert db_session.scalar(select(SoldReport.id)) is None
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == "clear_reports_admin")
        )
        assert audit is not None

    def test_pause_sets_indexing_paused(self, db_session):
        ch = _channel(db_session, "ch_actions_pause")
        client = _ops_client(db_session)
        resp = client.post(f"/ops/radar/channels/{ch.id}/pause")
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(Channel, ch.id).indexing_paused is True

    def test_hide_sets_removed_and_inactive(self, db_session):
        ch = _channel(db_session, "ch_actions_hide")
        item = _item(db_session, ch)
        client = _ops_client(db_session)
        resp = client.post(f"/ops/radar/items/{item.id}/hide")
        assert resp.status_code == 200
        db_session.expire_all()
        hidden = db_session.get(Item, item.id)
        assert hidden.status == "removed"
        assert hidden.is_active is False

    def test_retry_flips_failed_to_pending(self, db_session):
        """NB-59 §5.1 shared verb — referenced by the radar action chain."""
        user = _user(db_session, telegram_id=602)
        notif = Notification(
            user_id=user.id, item_id=None, alert_id=None,
            match_tier="bullseye", match_score=1.0, status="FAILED",
        )
        db_session.add(notif)
        db_session.commit()
        client = _ops_client(db_session)

        resp = client.post(f"/ops/actions/notifications/{notif.id}/retry")
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert db_session.get(Notification, notif.id).status == "PENDING"

        # already pending → 409
        resp = client.post(f"/ops/actions/notifications/{notif.id}/retry")
        assert resp.status_code == 409

    def test_ban_owner_verb_via_shared_users_endpoint(self, db_session):
        owner = _user(db_session, telegram_id=603)
        ch = _channel(db_session, "ch_actions_ban", owner_tg=603)
        item = _item(db_session, ch)
        client = _ops_client(db_session)
        resp = client.post(f"/ops/users/{owner.telegram_id}/ban")
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(User, owner.id).banned is True


# ---------------------------------------------------------------------------
# The listener poller: consecutive-failure marking (blueprint §3.4)
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LISTENER_DIR = os.path.join(_REPO_ROOT, "listener")
if _LISTENER_DIR not in sys.path:
    sys.path.insert(0, _LISTENER_DIR)

import types  # noqa: E402


class WebAppInfo:
    def __init__(self, url):
        self.url = url


class InlineKeyboardButton:
    def __init__(self, text, web_app=None, callback_data=None):
        self.text = text
        self.web_app = web_app
        self.callback_data = callback_data


class InlineKeyboardMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class TelegramError(Exception):
    pass


class Bot:
    pass


_telegram = types.ModuleType("telegram")
_telegram.Bot = Bot
_telegram.WebAppInfo = WebAppInfo
_telegram.InlineKeyboardButton = InlineKeyboardButton
_telegram.InlineKeyboardMarkup = InlineKeyboardMarkup
_error_mod = types.ModuleType("telegram.error")
_error_mod.TelegramError = TelegramError
_telegram.error = _error_mod
sys.modules.setdefault("telegram", _telegram)
sys.modules.setdefault("telegram.error", _error_mod)


class _FlakyBot:
    """fail_first=-1 → always fails; N ≥ 0 → fails the first N deliveries,
    then succeeds (the poller contract: transient failures below the limit
    keep retrying; a success clears the consecutive-failure counter)."""

    def __init__(self, fail_first=-1):
        self.failures_left = fail_first

    async def send_photo(self, *args, **kwargs):
        return await self.send_message(*args, **kwargs)

    async def send_message(self, *args, **kwargs):
        if self.failures_left != 0:
            if self.failures_left > 0:
                self.failures_left -= 1
            raise TelegramError("chat not found")
        return True


_PENDING_PAYLOAD = [{
    "id": 5,
    "message_text": None,
    "alert_id": None,
    "user_telegram_id": 111,
    "match_tier": "bullseye",
    "item": {
        "id": 1, "title": "iPhone 13", "price": 100, "specs": "{}",
        "description": "d", "image_path": None, "images": [],
    },
}]


def _run_poller(monkeypatch, *, limit, fail_first=-1):
    import notifications as notif_mod  # listener/notifications.py

    # Faithful mock of the backend: a notification leaves the /pending poll
    # once it flips to SENT (ack) or FAILED (mark) — otherwise the poller
    # would re-deliver the same row forever and mark it 42 times.
    state = {"pending": True}
    calls = {"ack": 0, "fail": 0}
    notif_id = _PENDING_PAYLOAD[0]["id"]

    async def _pending():
        return _PENDING_PAYLOAD if state["pending"] else []

    async def _ack(nid):
        calls["ack"] += 1
        state["pending"] = False

    async def _fail(nid):
        calls["fail"] += 1
        state["pending"] = False

    monkeypatch.setattr(notif_mod, "get_pending_notifications", _pending)
    monkeypatch.setattr(notif_mod, "ack_notification", _ack)
    monkeypatch.setattr(notif_mod, "mark_notification_failed", _fail)
    monkeypatch.setattr(notif_mod, "NOTIFICATION_FAILURE_LIMIT", limit)

    import asyncio

    real_sleep = asyncio.sleep

    # NOTE: the fake sleep must YIELD like the real sleep(0) — a bare
    # immediately-completing coroutine keeps the poller's ready queue
    # non-empty forever, so the loop never sleeps on the selector and the
    # harness's real timers starve (verified empirically on 3.14: the
    # harness never breaks and the test hangs). real_sleep(0) contains the
    # bare-yield `__sleep0` path, so the loop gets its timer slots back.
    monkeypatch.setattr(asyncio, "sleep", lambda delay: real_sleep(0))

    async def _harness():
        task = asyncio.create_task(
            notif_mod.notification_poller(_FlakyBot(fail_first=fail_first))
        )
        for _ in range(200):
            if calls["fail"] or calls["ack"]:
                break
            await real_sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_harness())
    return calls


class TestPollerFailureMarking:
    def test_marks_failed_after_limit_consecutive_failures(self, monkeypatch):
        calls = _run_poller(monkeypatch, limit=2)
        assert calls["ack"] == 0
        assert calls["fail"] == 1

    def test_retries_below_the_limit(self, monkeypatch):
        # two transient failures (below limit 3), then a successful delivery:
        # the counter clears on success and the poller acks instead of marking.
        calls = _run_poller(monkeypatch, limit=3, fail_first=2)
        assert calls["ack"] == 1
        assert calls["fail"] == 0

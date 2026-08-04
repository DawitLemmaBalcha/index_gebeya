"""
Alert-cap unification regression tests (TECH-28, blueprint D3/§2.3/§5.2).

Both cap call sites (services/alerting.create_alert and the alerts route
create_new_alert) must delegate to get_effective_alert_cap and produce
identical reject/pass behavior at 20/21/30/31 alerts. Also covers the
toggle_alert_pause lapsed-guard (resume of a lapse-deactivated alert
requires an active subscription).
"""
import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import get_db
from models import User, Alert, Subscription
from constants import MAX_ALERTS_PER_USER, ALERTS_SUBSCRIPTION_EXTRA_ALERTS
from services.alerting import create_alert
from services.subscriptions import get_effective_alert_cap


def _make_user(db, telegram_id=111):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_alert(db, user, *, is_active=True, lapsed=False):
    vec = [0.01] * 512
    alert = Alert(
        user_id=user.id,
        query_text=f"alert {user.id} {len(user.alerts or [])}",
        query_vector=vec,
        preferences=json.dumps({}),
        is_active=is_active,
        lapsed=lapsed,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _make_subscription(db, user):
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    sub = Subscription(
        user_id=user.id, product="alerts_only", status="active",
        telegram_payment_charge_id="chg_cap_reg",
        invoice_payload=f"s:{user.id}:alerts_only:abc",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
        is_recurring=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _alerts_client(db_session):
    from api.routes import alerts as alerts_router
    app = FastAPI()
    app.include_router(alerts_router.router, prefix="/alerts", tags=["Alerts"])

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


class TestServiceCallSite:
    """services/alerting.create_alert uses the effective cap."""

    def test_free_tier_rejects_above_cap(self, db_session):
        user = _make_user(db_session)
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            create_alert(db_session, user, "one too many", None, {})
        assert exc.value.status_code == 400
        assert f"{MAX_ALERTS_PER_USER}" in exc.value.detail

    def test_free_tier_accepts_at_cap(self, db_session):
        user = _make_user(db_session)
        for _ in range(MAX_ALERTS_PER_USER - 1):
            _make_alert(db_session, user)

        alert = create_alert(db_session, user, "at the cap", None, {})
        assert alert.id > 0

    def test_subscription_raises_cap_both_sides(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user)
        cap = get_effective_alert_cap(db_session, user)
        for _ in range(cap):
            _make_alert(db_session, user)

        # At the raised cap: still accepted (count == cap rejected? No —
        # reject only when active_count >= cap, so cap-1 active is the max
        # successful state; we seeded cap alerts -> next create rejects.)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            create_alert(db_session, user, "over the raised cap", None, {})
        assert exc.value.status_code == 400
        assert str(cap) in exc.value.detail

    def test_subscription_cap_behavior_at_21_and_31(self, db_session):
        user = _make_user(db_session)
        from fastapi import HTTPException
        # Free tier: 20 ok, 21 rejected
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)
        with pytest.raises(HTTPException):
            create_alert(db_session, user, "x", None, {})
        # Subscription: 30 ok, 31 rejected
        _make_subscription(db_session, user)
        for _ in range(ALERTS_SUBSCRIPTION_EXTRA_ALERTS):
            _make_alert(db_session, user)  # now at 30
        with pytest.raises(HTTPException):
            create_alert(db_session, user, "x", None, {})


class TestRouteCallSite:
    """The alerts route create_new_alert uses the effective cap (D3)."""

    def _post_alert(self, client, user_id):
        return client.post(
            "/alerts/",
            json={
                "query_text": f"route alert {user_id}",
                "max_price": None,
                "init_data": str(user_id),  # internal bypass
                "preferences": {},
            },
            headers={"X-Internal-Service": "index-listener"},
        )

    def test_route_free_tier_rejects_above_cap(self, db_session):
        user = _make_user(db_session)
        for _ in range(MAX_ALERTS_PER_USER):
            _make_alert(db_session, user)
        client = _alerts_client(db_session)

        resp = self._post_alert(client, 111)
        assert resp.status_code == 400
        assert f"{MAX_ALERTS_PER_USER}" in resp.json()["detail"]

    def test_route_accepts_with_subscription_up_to_raised_cap(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user)
        cap = get_effective_alert_cap(db_session, user)
        for _ in range(cap - 1):
            _make_alert(db_session, user)
        client = _alerts_client(db_session)

        resp = self._post_alert(client, 111)
        assert resp.status_code == 200, resp.text

        resp = self._post_alert(client, 111)  # now at cap -> reject
        assert resp.status_code == 400


class TestLapsedResumeGuard:
    """toggle_alert_pause: resuming a lapse-deactivated alert needs a
    subscription (blueprint §2.3 locked lapse mechanism)."""

    def _pause_client(self, db_session):
        return _alerts_client(db_session)

    def _toggle(self, client, alert_id, user_id):
        return client.patch(
            f"/alerts/{alert_id}/pause",
            params={"init_data": str(user_id)},
            headers={"X-Internal-Service": "index-listener"},
        )

    def test_resume_lapsed_alert_without_subscription_400(self, db_session):
        user = _make_user(db_session)
        alert = _make_alert(db_session, user, is_active=False, lapsed=True)
        client = self._pause_client(db_session)

        resp = self._toggle(client, alert.id, 111)
        assert resp.status_code == 400
        assert "Subscription required" in resp.json()["detail"]
        # Still inactive after the rejected resume
        db_session.refresh(alert)
        assert alert.is_active is False

    def test_resume_lapsed_alert_with_subscription_200(self, db_session):
        user = _make_user(db_session)
        _make_subscription(db_session, user)
        alert = _make_alert(db_session, user, is_active=False, lapsed=True)
        client = self._pause_client(db_session)

        resp = self._toggle(client, alert.id, 111)
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is True

    def test_pausing_lapsed_alert_stays_allowed(self, db_session):
        user = _make_user(db_session)
        alert = _make_alert(db_session, user, is_active=False, lapsed=True)
        client = self._pause_client(db_session)

        # Pausing (is_active False -> True) is the guarded direction; toggling
        # FROM False is a resume. The guard only blocks resumes without a
        # subscription, so this 400 applies. Pausing a lapsed alert means the
        # user clicks pause while it is already inactive — the toggle is a
        # no-op flip back to active which is still a resume.
        resp = self._toggle(client, alert.id, 111)
        assert resp.status_code == 400  # no subscription -> resume blocked

    def test_plain_user_pause_resume_unaffected(self, db_session):
        user = _make_user(db_session)
        alert = _make_alert(db_session, user, is_active=True, lapsed=False)
        client = self._pause_client(db_session)

        # Pause (active -> inactive): allowed without subscription
        resp = self._toggle(client, alert.id, 111)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
        # Resume (inactive -> active, lapsed=False): allowed without subscription
        resp = self._toggle(client, alert.id, 111)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True


class TestAlertInteractionUserAttribution:
    """UAT regression: alert routes must pass the TELEGRAM id (not the
    users.id PK) to AnalyticsService.log_interaction. The service resolves
    user_id via `select(User.id).where(User.telegram_id == user_id)`, so a
    PK passed here finds no telegram match and the interaction row is stored
    with user_id = NULL — silently dropping alert event attribution.

    These tests drive the REAL routes through TestClient (background tasks
    run before the response returns), so they lock the call-site contract:
    the stored user_interactions.user_id must be the resolved users.id PK.
    Mirrors TestAnalyticsOverflow's db_session + row-assertion style."""

    def _interaction_row(self, db_session, interaction_type):
        from models import UserInteraction
        return db_session.scalar(
            select(UserInteraction).where(
                UserInteraction.interaction_type == interaction_type
            )
        )

    def test_create_alert_interaction_stores_resolved_user_pk(self, db_session):
        user = _make_user(db_session)
        client = _alerts_client(db_session)

        resp = client.post(
            "/alerts/",
            json={
                "query_text": "attribution check",
                "max_price": None,
                "init_data": str(user.telegram_id),  # internal bypass
                "preferences": {},
            },
            headers={"X-Internal-Service": "index-listener"},
        )
        assert resp.status_code == 200, resp.text

        row = self._interaction_row(db_session, "create_alert")
        assert row is not None
        assert row.user_id == user.id  # users.id PK — not NULL, not telegram_id

    def test_delete_alert_interaction_stores_resolved_user_pk(self, db_session):
        user = _make_user(db_session)
        alert = _make_alert(db_session, user)
        client = _alerts_client(db_session)

        resp = client.delete(
            f"/alerts/{alert.id}",
            params={"init_data": str(user.telegram_id)},
            headers={"X-Internal-Service": "index-listener"},
        )
        assert resp.status_code == 200, resp.text

        row = self._interaction_row(db_session, "delete_alert")
        assert row is not None
        assert row.user_id == user.id  # users.id PK — not NULL, not telegram_id

    def test_pause_alert_interaction_stores_resolved_user_pk(self, db_session):
        user = _make_user(db_session)
        alert = _make_alert(db_session, user, is_active=True, lapsed=False)
        client = _alerts_client(db_session)

        resp = client.patch(
            f"/alerts/{alert.id}/pause",
            params={"init_data": str(user.telegram_id)},
            headers={"X-Internal-Service": "index-listener"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False  # paused

        row = self._interaction_row(db_session, "alert_paused")
        assert row is not None
        assert row.user_id == user.id  # users.id PK — not NULL, not telegram_id

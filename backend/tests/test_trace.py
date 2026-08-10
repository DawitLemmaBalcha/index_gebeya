"""
NB-58: engine diagnostics — per-item decision traces (blueprint §4, §5.4).

The trace replays the per-alert pipeline stages as PURE logic — no dispatch,
no counters, no best_opportunity_score writes, no commit. The LLM judge call
is the only external side effect (identical to the real pipeline's call).

Covers: every stage outcome on seeded data (price_gate, expired,
threshold_miss, judge_rejected / judge_errored / unknown_verdict with a
monkeypatched verify_match_with_llm, high_water_suppressed, throttled,
dedup_suppressed, dispatched, speed_pass); side-effect-free assertions (zero
Notification rows, JUDGE_ERROR_COUNT unchanged, best_opportunity_score
unchanged, no alert rows mutated); 404 for an unknown item.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from ai_engine.llm_client import JudgeVerdict
from database import get_db
from models import Alert, Channel, Item, Notification, User
from services import alerting, trace as trace_mod

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "indexgebeya")

# Vector fixtures: pgvector requires the full 512-dimension space.
V_ITEM = [1.0] + [0.0] * 511            # cosine 1.0 vs V_BULLSEYE, 0.8 vs V_RING
V_BULLSEYE = [1.0] + [0.0] * 511
V_RING = [0.8] + [0.6] + [0.0] * 510    # cosine 0.8 vs V_ITEM
V_ORTHOGONAL = [0.0, 1.0] + [0.0] * 510  # cosine 0.0 vs V_ITEM

# Hybrid scores (final = 0.5*semantic + 0.5*lexical):
#  - RING: title "abzzz" vs query "abqqq" → lexical 0.4; semantic 0.8 →
#    final 0.60 (>= TIER_2 0.55, < TIER_1 0.82; no speed pass: "abqqq"
#    is not contained in "abzzz").
#  - BULLSEYE: title "abcde" vs query "xabcde" → lexical 10/11 ≈ 0.909;
#    semantic 1.0 → final ≈ 0.9545 (>= 0.82; no speed pass: the >3-char
#    query "xabcde" is not contained in "abcde").
RING_TITLE, RING_QUERY = "abzzz", "abqqq"
BULL_TITLE, BULL_QUERY = "abcde", "xabcde"


def _user(db, telegram_id=111):
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", banned=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _channel(db, username="ch_trace"):
    channel = Channel(
        username=username, title=username, registered_by=None,
        trust_score=0.0, indexing_paused=False, is_active=True,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _item(db, channel, *, title=RING_TITLE, price=100.0, vector=None):
    item = Item(
        channel_id=channel.id, title=title, price=price,
        category="Mobile Phones", subcategory="General", status="active",
        is_active=True, image_path="x.jpg", specs="{}",
        image_vector=vector if vector is not None else V_ITEM,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _alert(db, user, *, query=RING_QUERY, vector=None, max_price=None,
           preferences="{}", expires_at=None, best=0.0,
           last_triggered_at=None):
    alert = Alert(
        user_id=user.id, query_text=query,
        query_vector=vector if vector is not None else V_RING,
        max_price=max_price, preferences=preferences,
        best_opportunity_score=best, expires_at=expires_at,
        last_triggered_at=last_triggered_at, is_active=True,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _trace(db_session, item_id):
    return trace_mod.build_item_trace(db_session, item_id)


def _stage_of(result, alert_id):
    return next(s for s in result["stages"] if s["alert_id"] == alert_id)


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


def _judge_mock(title, query, preferences):
    """Per-alert verdicts keyed off the alert's preferences payload — the
    judge's third argument — so the query text can stay on the RING lexical
    fixture ("abqqq" vs title "abzzz")."""
    verdicts = {
        "rejectme": JudgeVerdict.REJECTED,
        "erroeme": JudgeVerdict.ERRORED,
        "unknownme": None,  # a non-enum return → the defensive fail-closed branch
    }
    return verdicts.get((preferences or {}).get("verdict"), JudgeVerdict.APPROVED)


# ---------------------------------------------------------------------------
# The stage outcomes
# ---------------------------------------------------------------------------
class TestStageOutcomes:
    def test_price_gate(self, db_session):
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user, max_price=50.0)  # item price 100
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "price_gate"

    def test_expired(self, db_session):
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(
            db_session, user,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "expired"

    def test_threshold_miss(self, db_session):
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user, vector=V_ORTHOGONAL, query="qqqq")
        result = _trace(db_session, item.id)
        stage = _stage_of(result, alert.id)
        assert stage["outcome"] == "threshold_miss"
        assert stage["tier"] == "miss"

    def test_speed_pass(self, db_session):
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch, title="iPhone 13")
        alert = _alert(db_session, user, query="iphone13")
        result = _trace(db_session, item.id)
        stage = _stage_of(result, alert.id)
        assert stage["outcome"] == "speed_pass"
        assert stage["score"] == 1.0
        assert stage["tier"] == "bullseye"
        assert "skip" in stage["reason"].lower()

    def test_judge_rejected(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user, preferences='{"verdict": "rejectme"}')
        result = _trace(db_session, item.id)
        stage = _stage_of(result, alert.id)
        assert stage["outcome"] == "judge_rejected"
        assert stage["tier"] == "ring"

    def test_judge_errored(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user, preferences='{"verdict": "erroeme"}')
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "judge_errored"

    def test_unknown_verdict(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user, preferences='{"verdict": "unknownme"}')
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "unknown_verdict"

    def test_high_water_suppressed(self, db_session):
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        # score 0.60 must clear best 0.90 - RING_TOLERANCE (0.05) → suppressed
        alert = _alert(db_session, user, best=0.90)
        result = _trace(db_session, item.id)
        stage = _stage_of(result, alert.id)
        assert stage["outcome"] == "high_water_suppressed"
        assert stage["score"] == 0.60

    def test_throttled(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "NOTIFICATION_THROTTLE_SECONDS", 3600)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(
            db_session, user,
            last_triggered_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        )
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "throttled"

    def test_dedup_suppressed(self, db_session):
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user)
        db_session.add(Notification(
            user_id=user.id, item_id=item.id, alert_id=alert.id,
            match_tier="ring", match_score=0.6, status="PENDING",
        ))
        db_session.commit()
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "dedup_suppressed"

    def test_dispatched(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch, title=BULL_TITLE)
        alert = _alert(db_session, user, query=BULL_QUERY, vector=V_BULLSEYE)
        result = _trace(db_session, item.id)
        stage = _stage_of(result, alert.id)
        assert stage["outcome"] == "dispatched"
        assert stage["tier"] == "bullseye"
        assert stage["score"] > 0.82


# ---------------------------------------------------------------------------
# The side-effect-free contract (blueprint §4.1)
# ---------------------------------------------------------------------------
class TestSideEffectFree:
    def test_no_rows_written_no_counters_no_mutations(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        monkeypatch.setattr(alerting, "JUDGE_ERROR_COUNT", 7)
        user = _user(db_session)
        ch = _channel(db_session)
        # a BULLSEYE that WOULD raise the high water mark and dispatch
        item = _item(db_session, ch, title=BULL_TITLE)
        alert = _alert(db_session, user, query=BULL_QUERY, vector=V_BULLSEYE)

        result = _trace(db_session, item.id)
        assert result["alerts_evaluated"] == 1
        assert _stage_of(result, alert.id)["outcome"] == "dispatched"

        # zero Notification rows created
        assert db_session.scalar(select(func.count(Notification.id))) == 0
        # the judge counter the real pipeline would increment is untouched
        assert alerting.JUDGE_ERROR_COUNT == 7
        db_session.expire_all()
        # best_opportunity_score untouched (real pipeline raises it to 0.95)
        assert db_session.get(Alert, alert.id).best_opportunity_score == 0.0
        # no alert row mutated (last_triggered_at stays NULL, still active)
        row = db_session.get(Alert, alert.id)
        assert row.last_triggered_at is None
        assert row.is_active is True
        assert row.total_matches == 0

    def test_judge_errored_does_not_increment_counter(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        monkeypatch.setattr(alerting, "JUDGE_ERROR_COUNT", 3)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch)
        alert = _alert(db_session, user, preferences='{"verdict": "erroeme"}')
        result = _trace(db_session, item.id)
        assert _stage_of(result, alert.id)["outcome"] == "judge_errored"
        assert alerting.JUDGE_ERROR_COUNT == 3  # fail-open counter NOT bumped


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
class TestTraceEndpoint:
    def test_endpoint_shape(self, db_session, monkeypatch):
        monkeypatch.setattr(trace_mod, "verify_match_with_llm", _judge_mock)
        user = _user(db_session)
        ch = _channel(db_session)
        item = _item(db_session, ch, title=BULL_TITLE)
        alert = _alert(db_session, user, query=BULL_QUERY, vector=V_BULLSEYE)
        client = _ops_client(db_session)

        resp = client.get(f"/ops/diagnostics/items/{item.id}/trace")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["item_id"] == item.id
        assert body["generated_at"]
        assert body["alerts_evaluated"] == 1
        stage = body["stages"][0]
        assert set(stage) == {"alert_id", "query_text", "outcome", "score", "tier", "reason"}
        assert stage["outcome"] == "dispatched"

    def test_404_unknown_item(self, db_session):
        client = _ops_client(db_session)
        resp = client.get("/ops/diagnostics/items/99999/trace")
        assert resp.status_code == 404

    def test_build_item_trace_returns_none_for_unknown_item(self, db_session):
        assert _trace(db_session, 99999) is None

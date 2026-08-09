"""
NB-20: LLM judge tri-state (JudgeVerdict) + orchestrator verdict behaviors.

Judge unit tests (mock httpx.Client at ai_engine.llm_client):
  - 200 + {"match": true}                       -> APPROVED
  - 200 + {"match": false}                      -> REJECTED
  - 200 + {} (missing match key)                -> REJECTED (fail-closed preserved)
  - 200 + unparseable inner JSON                -> ERRORED
  - 200 + non-dict payload                      -> ERRORED
  - non-200 (500)                               -> ERRORED
  - no API key                                  -> ERRORED
  - transport exception / timeout               -> ERRORED

Orchestrator behaviors (patch services.alerting.verify_match_with_llm):
  - REJECTED -> no Notification; counters unchanged.
  - ERRORED  -> Notification created (fail-open) AND JUDGE_ERROR_COUNT
                incremented AND JUDGE_ERROR_LAST_TS set.
  - APPROVED -> Notification created; counters unchanged.

House patterns: db_session fixture from conftest; alert/item fixture wired
like test_alert_pipeline.py; the no-key case monkeypatches the MODULE
attribute (GROQ_API_KEY is captured at import time, not read from env).
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select, func

from models import Alert, Item, User, Channel, Notification
from ai_engine.llm_client import verify_match_with_llm, JudgeVerdict
from ai_engine.matcher import MatchTier, MatchResult
from ai_engine.vector_client import vectorize_text
from services.alerting import process_new_item


# ---------------------------------------------------------------------------
# Judge unit tests
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_on_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raise_on_json = raise_on_json
        self.text = "mock body"

    def json(self):
        if self._raise_on_json:
            raise ValueError("invalid json body")
        return self._payload


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *args, **kwargs):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _judge(content, **kw):
    """Run verify_match_with_llm with a fake Groq response whose inner
    message content is `content` (a JSON string)."""
    payload = {"choices": [{"message": {"content": content}}]}
    fake = _FakeClient(_FakeResponse(payload=payload, **kw))
    with patch("ai_engine.llm_client.httpx.Client", return_value=fake):
        return verify_match_with_llm("iPhone 13 Pro", "iPhone 13", {"strict_brand": True})


class TestJudgeVerdictStates:
    def test_match_true_approved(self):
        assert _judge('{"match": true}') is JudgeVerdict.APPROVED

    def test_match_false_rejected(self):
        assert _judge('{"match": false}') is JudgeVerdict.REJECTED

    def test_missing_match_key_rejected_fail_closed(self):
        # NB-20: the legacy read was result.get("match", False) — a 200 with
        # no `match` key fail-CLOSED. Tri-state maps it to REJECTED so the
        # match outcome is preserved exactly.
        assert _judge('{}') is JudgeVerdict.REJECTED

    def test_unparseable_inner_json_errored(self):
        assert _judge("this is not json") is JudgeVerdict.ERRORED

    def test_non_dict_payload_errored(self):
        assert _judge("[1, 2, 3]") is JudgeVerdict.ERRORED

    def test_non_200_errored(self):
        fake = _FakeClient(_FakeResponse(status_code=500, payload={}))
        with patch("ai_engine.llm_client.httpx.Client", return_value=fake):
            assert (
                verify_match_with_llm("t", "q", {}) is JudgeVerdict.ERRORED
            )

    def test_no_api_key_errored(self, monkeypatch):
        # GROQ_API_KEY is captured at module import — patch the module
        # attribute, not the env var.
        monkeypatch.setattr("ai_engine.llm_client.GROQ_API_KEY", None)
        assert (
            verify_match_with_llm("t", "q", {}) is JudgeVerdict.ERRORED
        )

    def test_transport_exception_errored(self):
        fake = _FakeClient(ConnectionError("timeout"))
        with patch("ai_engine.llm_client.httpx.Client", return_value=fake):
            assert (
                verify_match_with_llm("t", "q", {}) is JudgeVerdict.ERRORED
            )


# ---------------------------------------------------------------------------
# Orchestrator verdict behaviors
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_judge_counters():
    """The counters are process-global module attributes — snapshot and
    restore around every test in this file."""
    from services import alerting

    snapshot = (alerting.JUDGE_ERROR_COUNT, alerting.JUDGE_ERROR_LAST_TS)
    yield
    alerting.JUDGE_ERROR_COUNT, alerting.JUDGE_ERROR_LAST_TS = snapshot


def _make_alert_and_item(db, query_text="random gadget", item_title="unrelated product listing"):
    """User + Channel + Alert + Item wired like test_alert_pipeline.py."""
    user = User(telegram_id=abs(hash(query_text + item_title)) % 900000 + 100000)
    db.add(user)
    db.flush()

    channel = Channel(username=f"lj_{abs(hash(query_text)) % 999999}", title="NB-20 Channel")
    db.add(channel)
    db.flush()

    alert = Alert(
        user_id=user.id,
        query_text=query_text,
        query_vector=vectorize_text(query_text),
        max_price=None,
        preferences="{}",
        best_opportunity_score=0.0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        is_active=True,
    )
    db.add(alert)
    db.flush()

    item = Item(
        channel_id=channel.id,
        telegram_message_id=abs(hash(item_title + query_text)) % 9000000 + 5000000,
        title=item_title,
        price=None,
        image_vector=None,
    )
    db.add(item)
    db.commit()
    db.refresh(alert)
    db.refresh(item)
    return alert, item


def _run_pipeline(db, verdict):
    alert, item = _make_alert_and_item(db)
    with patch(
        "services.alerting.evaluate_match",
        return_value=MatchResult(MatchTier.RING, 0.65, "mock", speed_pass=False),
    ), patch("services.alerting.verify_match_with_llm", return_value=verdict):
        process_new_item(db, item.id)
    total = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.alert_id == alert.id)
    )
    return alert, item, total


class TestOrchestratorVerdictBehaviors:
    def test_rejected_verdict_skips_and_keeps_counters(self, db_session):
        from services import alerting

        before_count, before_ts = alerting.JUDGE_ERROR_COUNT, alerting.JUDGE_ERROR_LAST_TS
        _, _, total = _run_pipeline(db_session, JudgeVerdict.REJECTED)
        assert total == 0
        assert alerting.JUDGE_ERROR_COUNT == before_count
        assert alerting.JUDGE_ERROR_LAST_TS == before_ts

    def test_errored_verdict_fail_opens_and_counts(self, db_session):
        from services import alerting

        before_count, _ = alerting.JUDGE_ERROR_COUNT, alerting.JUDGE_ERROR_LAST_TS
        _, _, total = _run_pipeline(db_session, JudgeVerdict.ERRORED)
        assert total == 1, "ERRORED must fail open (dispatch) — legacy True-path outcome"
        assert alerting.JUDGE_ERROR_COUNT == before_count + 1
        assert alerting.JUDGE_ERROR_LAST_TS is not None

    def test_approved_verdict_dispatches_and_keeps_counters(self, db_session):
        from services import alerting

        before_count, before_ts = alerting.JUDGE_ERROR_COUNT, alerting.JUDGE_ERROR_LAST_TS
        _, _, total = _run_pipeline(db_session, JudgeVerdict.APPROVED)
        assert total == 1
        assert alerting.JUDGE_ERROR_COUNT == before_count
        assert alerting.JUDGE_ERROR_LAST_TS == before_ts

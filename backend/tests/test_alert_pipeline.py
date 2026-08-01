"""
TECH-24: Alert pipeline deepening tests.

Coverage:
  - Interface tests through process_new_item(db, item_id) (the test surface):
    a. Containment speed pass skips the LLM judge entirely.
    b. Hybrid (non-speed-pass) match still invokes the LLM judge.
  - Unit tests through evaluate_match (empty vectors, None prices):
    c. Containment -> speed pass (BULLSEYE, 1.0).
    d. Exact normalized equality -> speed pass.
    e. Short query protection ("usb" vs "business") -> no speed pass, MISS.
    f. Unrelated pair -> MISS, no speed pass.
  - Backward compatibility:
    g. MatchResult constructed positionally defaults speed_pass to False.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import select, func
from models import Alert, Item, User, Channel, Notification
from services.alerting import process_new_item
from ai_engine.matcher import MatchTier, MatchResult
from ai_engine.vector_client import vectorize_text


# =========================================================================
# Interface tests (through process_new_item with the db_session fixture)
# =========================================================================

def _make_alert_and_item(db, query_text, item_title, max_price=None, item_price=None):
    """Create a User + Channel + Alert + Item wired the same way as test_tech20."""
    user = User(telegram_id=abs(hash(query_text + item_title)) % 900000 + 100000)
    db.add(user)
    db.flush()

    channel = Channel(username=f"tap_{abs(hash(query_text)) % 999999}", title="TECH-24 Channel")
    db.add(channel)
    db.flush()

    alert = Alert(
        user_id=user.id,
        query_text=query_text,
        query_vector=vectorize_text(query_text),
        max_price=max_price,
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
        price=item_price,
        image_vector=None,  # vectorless item is fine — containment path never needs it
    )
    db.add(item)
    db.commit()
    db.refresh(alert)
    db.refresh(item)
    return alert, item


def test_containment_speed_pass_skips_judge(db_session):
    """(a) 'iPhone 13' contained in 'iPhone 13 Pro Max 256GB Black' -> bullseye,
    and the LLM judge must NEVER be invoked (behavior-doc Rule 3.1 consequence)."""
    alert, item = _make_alert_and_item(
        db_session,
        query_text="iPhone 13",
        item_title="iPhone 13 Pro Max 256GB Black",
        max_price=100000,
        item_price=80000,
    )

    def _judge_must_not_run(*args, **kwargs):
        raise AssertionError("LLM judge must not be called on speed pass")

    with patch("services.alerting.verify_match_with_llm", side_effect=_judge_must_not_run):
        process_new_item(db_session, item.id)

    notif = db_session.scalar(
        select(Notification).where(
            Notification.alert_id == alert.id,
            Notification.item_id == item.id,
        )
    )
    total = db_session.scalar(
        select(func.count()).select_from(Notification).where(Notification.alert_id == alert.id)
    )
    assert total == 1, f"Expected exactly 1 Notification, got {total}"
    assert notif.match_tier == "bullseye", f"Expected bullseye tier, got {notif.match_tier}"


def test_hybrid_ring_without_speed_pass_invokes_judge(db_session):
    """(b) A probabilistic RING match (speed_pass=False) must invoke the judge,
    and dispatch when the judge approves."""
    alert, item = _make_alert_and_item(
        db_session,
        query_text="random gadget",
        item_title="unrelated product listing",
    )

    judge_calls = []

    def judge_spy(item_title, alert_query, preferences):
        judge_calls.append((item_title, alert_query, preferences))
        return True

    with patch(
        "services.alerting.evaluate_match",
        return_value=MatchResult(MatchTier.RING, 0.65, "mock", speed_pass=False),
    ), patch("services.alerting.verify_match_with_llm", judge_spy):
        process_new_item(db_session, item.id)

    assert len(judge_calls) == 1, (
        f"LLM judge must be called exactly once for a non-speed-pass match, "
        f"called {len(judge_calls)} times"
    )
    total = db_session.scalar(
        select(func.count()).select_from(Notification).where(Notification.alert_id == alert.id)
    )
    assert total == 1, f"Expected exactly 1 Notification, got {total}"


# =========================================================================
# Unit tests (through evaluate_match with empty vectors / None prices)
# =========================================================================

def test_containment_is_speed_pass():
    """(c) Containment (Rule 3.1) -> deterministic BULLSEYE 1.0 speed pass."""
    from ai_engine.matcher import evaluate_match

    result = evaluate_match(
        item_vector=[],
        alert_vector=[],
        item_price=None,
        alert_max_price=None,
        item_title="iPhone 13 Pro Max 256GB Black",
        alert_query_text="iPhone 13",
    )
    assert result.speed_pass is True
    assert result.tier == MatchTier.BULLSEYE
    assert result.score == 1.0


def test_exact_normalized_equality_is_speed_pass():
    """(d) Exact normalized equality -> speed pass."""
    from ai_engine.matcher import evaluate_match

    result = evaluate_match(
        item_vector=[], alert_vector=[], item_price=None, alert_max_price=None,
        item_title="iPhone 13", alert_query_text="iPhone 13",
    )
    assert result.speed_pass is True


def test_short_query_protection_blocks_speed_pass():
    """(e) 3-char-or-less query must NOT speed pass even when contained (Rule 3.2);
    with empty vectors the hybrid score lands below TIER_2 -> MISS."""
    from ai_engine.matcher import evaluate_match

    result = evaluate_match(
        item_vector=[], alert_vector=[], item_price=None, alert_max_price=None,
        item_title="business", alert_query_text="usb",
    )
    assert result.speed_pass is False
    assert result.tier == MatchTier.MISS


def test_unrelated_pair_is_miss():
    """(f) Unrelated query/title -> MISS with no speed pass."""
    from ai_engine.matcher import evaluate_match

    result = evaluate_match(
        item_vector=[], alert_vector=[], item_price=None, alert_max_price=None,
        item_title="Samsung Galaxy S24", alert_query_text="iPhone 13",
    )
    assert result.tier == MatchTier.MISS
    assert result.speed_pass is False


def test_match_result_positional_construction_is_backward_compatible():
    """(g) Existing positional construction keeps speed_pass=False."""
    result = MatchResult(MatchTier.RING, 0.65, "x")
    assert result.speed_pass is False

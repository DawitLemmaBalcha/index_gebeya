"""
User-deletion FK policy tests (side mission, TECH-25 class).

sqladmin hard-delete of a `users` row used to fail with ForeignKeyViolation
because 8 FKs referenced users.id with no ON DELETE action (RESTRICT
default). The locked policy:

  - user_interactions.user_id        → ON DELETE SET NULL
  - alerts.user_id                   → ON DELETE CASCADE
  - notifications.user_id            → ON DELETE CASCADE
  - reviews.user_id                  → ON DELETE CASCADE
  - sold_reports.user_id             → ON DELETE CASCADE
  - item_edits.edited_by             → ON DELETE CASCADE
  - boosts.user_id                   → ON DELETE CASCADE
  - subscriptions.user_id            → ON DELETE CASCADE

`channels.registered_by` is a plain BigInteger, NOT an FK — intentionally
untouched: channels survive user deletion with registered_by intact.

The cascade/nullification happens at the DATABASE level (the ORM has no
cascade configured on these relationships — except the legacy
delete-orphan on User.alerts, which is harmless). Tests seed children,
delete the user via db.delete + db.commit, and assert observable outcomes
with fresh count queries (never ORM refresh of dead objects).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, func, text

from models import (
    Alert,
    Boost,
    Channel,
    Item,
    ItemEdit,
    Notification,
    Review,
    SoldReport,
    Subscription,
    User,
    UserInteraction,
)


# =========================================================================
# SCHEMA GUARD
# =========================================================================

@pytest.fixture(scope="session", autouse=True)
def _ensure_user_fk_actions(_test_db_schema):
    """
    The cascade/SET NULL assertions depend on the test-DB user FKs carrying
    the policy actions. conftest's create_all builds them from the model on
    a fresh DB, but a pre-existing constraint (leftover from an earlier
    session) would still be RESTRICT. Mirror the idempotent user-deletion
    migration from main.py: for each of the 8 user FKs, drop (guarded on
    pg_constraint) + re-add with the policy action. No-op churn when the
    constraint already carries the action.
    """
    from database import engine
    with engine.begin() as conn:
        for table, column, constraint, action in [
            ("user_interactions", "user_id", "user_interactions_user_id_fkey", "SET NULL"),
            ("alerts", "user_id", "alerts_user_id_fkey", "CASCADE"),
            ("notifications", "user_id", "notifications_user_id_fkey", "CASCADE"),
            ("reviews", "user_id", "reviews_user_id_fkey", "CASCADE"),
            ("sold_reports", "user_id", "sold_reports_user_id_fkey", "CASCADE"),
            ("item_edits", "edited_by", "item_edits_edited_by_fkey", "CASCADE"),
            ("boosts", "user_id", "boosts_user_id_fkey", "CASCADE"),
            ("subscriptions", "user_id", "subscriptions_user_id_fkey", "CASCADE"),
        ]:
            conn.execute(text(
                f"DO $$ BEGIN "
                f"IF EXISTS (SELECT 1 FROM pg_constraint "
                f"WHERE conname = '{constraint}' "
                f"AND conrelid = '{table}'::regclass) THEN "
                f"ALTER TABLE {table} DROP CONSTRAINT {constraint}; "
                f"END IF; END $$;"
            ))
            conn.execute(text(
                f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                f"FOREIGN KEY ({column}) REFERENCES users(id) ON DELETE {action}"
            ))


# =========================================================================
# TEST HELPERS
# =========================================================================

def _make_user(db, tg_id):
    user = User(telegram_id=tg_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_channel(db, username, registered_by=None):
    channel = Channel(username=username, registered_by=registered_by)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _make_item(db, channel):
    item = Item(
        channel_id=channel.id,
        title="user-delete policy item",
        category="Other",
        price=50.0,
        status="active",
        is_active=True,
        image_path="test.jpg",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _make_alert(db, user):
    alert = Alert(
        user_id=user.id,
        query_text="user-delete policy alert",
        query_vector=None,
        preferences="{}",
        best_opportunity_score=0.0,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _make_notification(db, user):
    notif = Notification(
        user_id=user.id,
        match_tier="bullseye",
        match_score=0.9,
        status="SENT",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def _make_review(db, user, channel):
    review = Review(
        channel_id=channel.id,
        user_id=user.id,
        rating=5,
        comment="user-delete policy review",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def _make_sold_report(db, user, item):
    report = SoldReport(user_id=user.id, item_id=item.id)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _make_item_edit(db, user, item):
    edit = ItemEdit(
        item_id=item.id,
        field="price",
        old_value="50.0",
        new_value="60.0",
        edited_by=user.id,
    )
    db.add(edit)
    db.commit()
    db.refresh(edit)
    return edit


def _make_boost(db, user, item, channel):
    boost = Boost(
        item_id=item.id,
        channel_id=channel.id,
        user_id=user.id,
        source="paid",
        price_paid_stars=25,
        telegram_payment_charge_id=None,  # unique column — NULLs distinct
        starts_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(boost)
    db.commit()
    db.refresh(boost)
    return boost


def _make_subscription(db, user):
    sub = Subscription(
        user_id=user.id,
        product="alerts_only",
        status="active",
        telegram_payment_charge_id=None,  # unique column — NULLs distinct
        invoice_payload="user-delete-policy-test",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _count(db, model, *criteria):
    """Fresh count query — never ORM refresh of possibly-dead rows."""
    return db.scalar(select(func.count()).select_from(model).where(*criteria))


# =========================================================================
# CASCADE — deleting a user removes all ownership-bound children
# =========================================================================

def test_delete_user_cascades_all_children(db_session):
    """One child of each ownership type (alerts, notifications, reviews,
    sold_reports, item_edits, boosts, subscriptions) bound to the user.
    After db.delete(user) + commit, every child table has zero rows for
    that user — the DB-level ON DELETE CASCADE does the work."""
    user = _make_user(db_session, 60001)
    channel = _make_channel(db_session, "ch_delete_cascade", registered_by=60001)
    item = _make_item(db_session, channel)
    _make_alert(db_session, user)
    _make_notification(db_session, user)
    _make_review(db_session, user, channel)
    _make_sold_report(db_session, user, item)
    _make_item_edit(db_session, user, item)
    _make_boost(db_session, user, item, channel)
    _make_subscription(db_session, user)
    uid = user.id

    db_session.delete(user)
    db_session.commit()

    assert _count(db_session, User, User.id == uid) == 0
    assert _count(db_session, Alert, Alert.user_id == uid) == 0
    assert _count(db_session, Notification, Notification.user_id == uid) == 0
    assert _count(db_session, Review, Review.user_id == uid) == 0
    assert _count(db_session, SoldReport, SoldReport.user_id == uid) == 0
    assert _count(db_session, ItemEdit, ItemEdit.edited_by == uid) == 0
    assert _count(db_session, Boost, Boost.user_id == uid) == 0
    assert _count(db_session, Subscription, Subscription.user_id == uid) == 0


# =========================================================================
# SET NULL — user_interactions survives with a NULL user_id
# =========================================================================

def test_delete_user_set_nulls_interactions(db_session):
    """user_interactions.user_id is ON DELETE SET NULL: deleting the user
    must NOT delete the interaction rows — they survive with user_id NULL
    (verified via fresh query, not ORM refresh)."""
    user = _make_user(db_session, 60002)
    for _ in range(2):
        db_session.add(UserInteraction(user_id=user.id))
    db_session.commit()
    uid = user.id

    db_session.delete(user)
    db_session.commit()

    # Rows survive ...
    assert _count(db_session, UserInteraction) == 2
    # ... but are no longer attributed to the deleted user ...
    assert _count(db_session, UserInteraction, UserInteraction.user_id == uid) == 0
    # ... their user_id is NULL at the DB level.
    assert _count(db_session, UserInteraction, UserInteraction.user_id.is_(None)) == 2


# =========================================================================
# CLEAN DELETE — no children, no problem
# =========================================================================

def test_delete_user_with_no_children(db_session):
    """A bare user row deletes cleanly — the sqladmin hard-delete path."""
    user = _make_user(db_session, 60003)
    uid = user.id

    db_session.delete(user)
    db_session.commit()

    assert _count(db_session, User, User.id == uid) == 0


# =========================================================================
# CHANNELS SURVIVE — registered_by is a BigInteger, not an FK
# =========================================================================

def test_user_with_channels_deletes_and_channels_survive(db_session):
    """channels.registered_by is intentionally a plain BigInteger (NOT an
    FK). Deleting the user succeeds and the channel survives with
    registered_by intact — proving the non-FK design."""
    user = _make_user(db_session, 60004)
    channel = _make_channel(db_session, "ch_delete_survive", registered_by=user.telegram_id)
    ch_id = channel.id
    registered_by = user.telegram_id

    db_session.delete(user)
    db_session.commit()

    assert _count(db_session, User, User.id == user.id) == 0
    surviving = db_session.scalar(select(Channel).where(Channel.id == ch_id))
    assert surviving is not None
    assert surviving.registered_by == registered_by

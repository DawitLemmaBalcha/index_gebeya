"""
Channel-deletion FK policy tests (final sweep of the FK-action bug class).

sqladmin hard-delete of a `channels` row used to fail because 3 FKs
referenced channels.id with no ON DELETE action (RESTRICT default). The
locked policy (ADR-0001 pattern, mirror of a97d1e2's user-deletion fix):

  - items.channel_id    → ON DELETE CASCADE (listings die with the channel)
  - reviews.channel_id  → ON DELETE CASCADE (ratings die with the channel)
  - boosts.channel_id   → ON DELETE CASCADE (boosts die with the channel)

The product's SOFT remove flow (Stores "Remove" → is_active=False → products
stay in catalog) is a flag, NOT a delete — untouched by this policy.

The cascade happens at the DATABASE level. Channel.items and Channel.reviews
carry passive_deletes=True: without it the ORM pre-nullifies these child FKs
on channel delete, violating their NOT NULL columns before the DB cascade
fires (the proven a97d1e2 trap). Boosts have NO Channel-side relationship —
the mapper is blind, so the DB does the work there. Tests seed children,
delete the channel via db.delete + db.commit, and assert observable outcomes
with fresh count queries (never ORM refresh of dead objects).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, func, text

from models import (
    Boost,
    Channel,
    Item,
    ItemImage,
    Review,
    SoldReport,
    User,
)


# =========================================================================
# SCHEMA GUARD
# =========================================================================

@pytest.fixture(scope="session", autouse=True)
def _ensure_channel_fk_actions(_test_db_schema):
    """
    The cascade assertions depend on the test-DB channel FKs carrying the
    policy actions. conftest's create_all builds them from the model on a
    fresh DB, but a pre-existing constraint (leftover from an earlier
    session) would still be RESTRICT. Mirror the idempotent channel-deletion
    migration from main.py: for each of the 3 channel FKs, drop (guarded on
    pg_constraint) + re-add with ON DELETE CASCADE. No-op churn when the
    constraint already carries the action.
    """
    from database import engine
    with engine.begin() as conn:
        for table, column, constraint, action in [
            ("items", "channel_id", "items_channel_id_fkey", "CASCADE"),
            ("reviews", "channel_id", "reviews_channel_id_fkey", "CASCADE"),
            ("boosts", "channel_id", "boosts_channel_id_fkey", "CASCADE"),
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
                f"FOREIGN KEY ({column}) REFERENCES channels(id) ON DELETE {action}"
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


def _make_channel(db, username):
    channel = Channel(username=username)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _make_item(db, channel):
    item = Item(
        channel_id=channel.id,
        title="channel-delete policy item",
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


def _make_review(db, user, channel):
    review = Review(
        channel_id=channel.id,
        user_id=user.id,
        rating=5,
        comment="channel-delete policy review",
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


def _count(db, model, *criteria):
    """Fresh count query — never ORM refresh of possibly-dead rows."""
    return db.scalar(select(func.count()).select_from(model).where(*criteria))


# =========================================================================
# CASCADE — deleting a channel removes its listings, ratings, and boosts
# =========================================================================

def test_delete_channel_cascades_items_reviews_boosts(db_session):
    """One child of each channel-bound type (item, review, boost) bound to
    the channel. After db.delete(channel) + commit, every child table has
    zero rows for that channel — the DB-level ON DELETE CASCADE does the
    work."""
    user = _make_user(db_session, 70001)
    channel = _make_channel(db_session, "ch_delete_cascade")
    item = _make_item(db_session, channel)
    _make_review(db_session, user, channel)
    _make_boost(db_session, user, item, channel)
    ch_id = channel.id

    db_session.delete(channel)
    db_session.commit()

    assert _count(db_session, Channel, Channel.id == ch_id) == 0
    assert _count(db_session, Item, Item.channel_id == ch_id) == 0
    assert _count(db_session, Review, Review.channel_id == ch_id) == 0
    assert _count(db_session, Boost, Boost.channel_id == ch_id) == 0


# =========================================================================
# CLEAN DELETE — no children, no problem
# =========================================================================

def test_delete_channel_with_no_children(db_session):
    """A bare channel row deletes cleanly — the sqladmin hard-delete path."""
    channel = _make_channel(db_session, "ch_delete_bare")
    ch_id = channel.id

    db_session.delete(channel)
    db_session.commit()

    assert _count(db_session, Channel, Channel.id == ch_id) == 0


# =========================================================================
# TRANSITIVE CASCADE — items' children die with the cascaded items
# =========================================================================

def test_delete_channel_transitively_removes_item_children(db_session):
    """Multi-path cascade: deleting the channel cascades its items at the DB
    level, and each cascaded item's own children (item_images, sold_reports)
    cascade in turn via their item_id ON DELETE CASCADE actions. Seed
    item + item_image + sold_report, delete the channel, assert all gone."""
    user = _make_user(db_session, 70002)
    channel = _make_channel(db_session, "ch_delete_transitive")
    item = _make_item(db_session, channel)
    item_image = ItemImage(item_id=item.id, image_path="gallery.jpg")
    db_session.add(item_image)
    db_session.commit()
    _make_sold_report(db_session, user, item)
    iid = item.id
    img_id = item_image.id

    db_session.delete(channel)
    db_session.commit()

    assert _count(db_session, Item, Item.id == iid) == 0
    assert _count(db_session, ItemImage, ItemImage.id == img_id) == 0
    assert _count(db_session, SoldReport, SoldReport.item_id == iid) == 0


# =========================================================================
# SOFT REMOVE UNTOUCHED — is_active flag, not a delete
# =========================================================================

def test_soft_remove_keeps_items(db_session):
    """The Stores "Remove" flow flips channel.is_active to False — a flag,
    NOT a delete. Items must survive it (they stay in the catalog)."""
    channel = _make_channel(db_session, "ch_soft_remove")
    item = _make_item(db_session, channel)
    iid = item.id

    channel.is_active = False
    db_session.commit()

    assert _count(db_session, Channel, Channel.id == channel.id) == 1
    assert _count(db_session, Item, Item.id == iid) == 1
    surviving = db_session.scalar(select(Channel).where(Channel.id == channel.id))
    assert surviving.is_active is False

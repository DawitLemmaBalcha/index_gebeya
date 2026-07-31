"""
Unit tests for services/item_status.py — item status-transition business rules.

These rules previously lived inside the items.py route handlers and could not
be tested without spinning up FastAPI. Observable outcomes asserted here:
  - report threshold flip (CROWDSOURCE_SOLD_THRESHOLD)
  - one-report-per-user-per-item
  - owner cannot report their own item
  - relist clears reports and resets status; no-op on never-reported items
  - non-owner 403 on every owner-only operation
  - mark_sold / clear_reports behavior
  - ItemEdit history: exactly one record per changed field
  - alert re-trigger (process_new_item) on price/specs change only
"""

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from constants import CROWDSOURCE_SOLD_THRESHOLD
from models import Channel, Item, ItemEdit, SoldReport, User
from schemas import ItemUpdateRequest
import services.item_status as item_status


# =========================================================================
# TEST HELPERS
# =========================================================================

def _make_user(db_session, tg_id, username="tester"):
    user = User(telegram_id=tg_id, username=username)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_channel(db_session, registered_by):
    channel = Channel(username=f"chan_{uuid4().hex[:8]}", registered_by=registered_by)
    db_session.add(channel)
    db_session.commit()
    db_session.refresh(channel)
    return channel


def _make_item(db_session, channel, status="active", price=100.0, title="Test item"):
    item = Item(channel_id=channel.id, title=title, price=price, status=status, is_active=True)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _report_count(db_session, item_id):
    return db_session.scalar(
        select(func.count()).select_from(SoldReport).where(SoldReport.item_id == item_id)
    )


def _edit_count(db_session, item_id):
    return db_session.scalar(
        select(func.count()).select_from(ItemEdit).where(ItemEdit.item_id == item_id)
    )


# =========================================================================
# REPORT SOLD — crowdsourced sold-reporting
# =========================================================================

@pytest.mark.asyncio
async def test_report_sold_creates_report_no_status_flip(db_session):
    """Single report: record created, count returned, status still active."""
    channel = _make_channel(db_session, registered_by=None)
    item = _make_item(db_session, channel)
    user = _make_user(db_session, 10001)

    result = await item_status.report_sold(db_session, item.id, user)

    assert result == {"status": "reported", "report_count": 1}
    assert _report_count(db_session, item.id) == 1
    assert db_session.get(Item, item.id).status == "active"


@pytest.mark.asyncio
async def test_report_sold_threshold_flips_status_and_notifies(db_session, monkeypatch):
    """At CROWDSOURCE_SOLD_THRESHOLD the status flips to 'reported_sold' and the owner is notified."""
    channel = _make_channel(db_session, registered_by=None)
    item = _make_item(db_session, channel)

    dm_calls = []

    async def fake_send_owner_dm(db, channel_id, message):
        dm_calls.append((channel_id, message))

    monkeypatch.setattr(item_status, "send_owner_dm", fake_send_owner_dm)

    for i in range(CROWDSOURCE_SOLD_THRESHOLD):
        user = _make_user(db_session, 20000 + i)
        result = await item_status.report_sold(db_session, item.id, user)

    assert result["status"] == "reported"
    assert result["report_count"] == CROWDSOURCE_SOLD_THRESHOLD
    assert db_session.get(Item, item.id).status == "reported_sold"
    assert _report_count(db_session, item.id) == CROWDSOURCE_SOLD_THRESHOLD
    # Owner DM attempted with the item's channel (best-effort adapter is patched here).
    assert [cid for cid, _ in dm_calls] == [channel.id]


@pytest.mark.asyncio
async def test_report_sold_one_report_per_user(db_session):
    """Second report by the same user is rejected with 409."""
    channel = _make_channel(db_session, registered_by=None)
    item = _make_item(db_session, channel)
    user = _make_user(db_session, 30001)

    await item_status.report_sold(db_session, item.id, user)

    with pytest.raises(HTTPException) as exc_info:
        await item_status.report_sold(db_session, item.id, user)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "You already reported this as sold."
    assert _report_count(db_session, item.id) == 1


@pytest.mark.asyncio
async def test_report_sold_owner_cannot_report_own_item(db_session):
    """The channel owner reporting their own item gets 403."""
    channel = _make_channel(db_session, registered_by=40001)
    item = _make_item(db_session, channel)
    owner = _make_user(db_session, 40001)

    with pytest.raises(HTTPException) as exc_info:
        await item_status.report_sold(db_session, item.id, owner)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You cannot report your own product"
    assert _report_count(db_session, item.id) == 0


@pytest.mark.asyncio
async def test_report_sold_missing_item_404(db_session):
    user = _make_user(db_session, 50001)

    with pytest.raises(HTTPException) as exc_info:
        await item_status.report_sold(db_session, 999999, user)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Item not found"


# =========================================================================
# RELIST — owner clears reports and resets status
# =========================================================================

def test_relist_clears_reports_and_resets_status(db_session):
    """Relisting a reported item: status -> active, all SoldReports deleted."""
    channel = _make_channel(db_session, registered_by=60001)
    item = _make_item(db_session, channel, status="reported_sold")
    owner = _make_user(db_session, 60001)
    for i in range(3):
        reporter = _make_user(db_session, 61000 + i)
        db_session.add(SoldReport(user_id=reporter.id, item_id=item.id))
    db_session.commit()
    assert _report_count(db_session, item.id) == 3

    result = item_status.relist_item(db_session, item.id, owner)

    assert result == {"status": "active", "message": "Item re-listed successfully"}
    assert db_session.get(Item, item.id).status == "active"
    assert _report_count(db_session, item.id) == 0


def test_relist_never_reported_is_noop(db_session):
    """Relisting an active, never-reported item returns already_active."""
    channel = _make_channel(db_session, registered_by=70001)
    item = _make_item(db_session, channel, status="active")
    owner = _make_user(db_session, 70001)

    result = item_status.relist_item(db_session, item.id, owner)

    assert result == {"status": "already_active", "message": "Item was never reported"}
    assert db_session.get(Item, item.id).status == "active"


def test_relist_non_owner_forbidden(db_session):
    """Non-owner relisting -> 403."""
    channel = _make_channel(db_session, registered_by=80001)
    item = _make_item(db_session, channel, status="reported_sold")
    stranger = _make_user(db_session, 89999)

    with pytest.raises(HTTPException) as exc_info:
        item_status.relist_item(db_session, item.id, stranger)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Only the channel owner can re-list this item"


def test_relist_missing_item_404(db_session):
    owner = _make_user(db_session, 80002)

    with pytest.raises(HTTPException) as exc_info:
        item_status.relist_item(db_session, 999999, owner)

    assert exc_info.value.status_code == 404


# =========================================================================
# MARK SOLD / CLEAR REPORTS — owner-authoritative actions
# =========================================================================

def test_mark_sold_sets_status(db_session):
    channel = _make_channel(db_session, registered_by=90001)
    item = _make_item(db_session, channel, status="active")
    owner = _make_user(db_session, 90001)

    result = item_status.mark_sold(db_session, item.id, owner)

    assert result == {"status": "sold", "message": "Item marked as sold"}
    assert db_session.get(Item, item.id).status == "sold"


def test_mark_sold_non_owner_forbidden(db_session):
    channel = _make_channel(db_session, registered_by=91001)
    item = _make_item(db_session, channel)
    stranger = _make_user(db_session, 91999)

    with pytest.raises(HTTPException) as exc_info:
        item_status.mark_sold(db_session, item.id, stranger)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Only the channel owner can mark items as sold"


def test_clear_reports_keeps_status(db_session):
    """Clearing reports deletes SoldReports WITHOUT changing status."""
    channel = _make_channel(db_session, registered_by=92001)
    item = _make_item(db_session, channel, status="reported_sold")
    owner = _make_user(db_session, 92001)
    for i in range(2):
        reporter = _make_user(db_session, 93000 + i)
        db_session.add(SoldReport(user_id=reporter.id, item_id=item.id))
    db_session.commit()

    result = item_status.clear_reports(db_session, item.id, owner)

    assert result == {"status": "reported_sold", "message": "2 report(s) cleared"}
    assert db_session.get(Item, item.id).status == "reported_sold"
    assert _report_count(db_session, item.id) == 0


def test_clear_reports_non_owner_forbidden(db_session):
    channel = _make_channel(db_session, registered_by=94001)
    item = _make_item(db_session, channel)
    stranger = _make_user(db_session, 94999)

    with pytest.raises(HTTPException) as exc_info:
        item_status.clear_reports(db_session, item.id, stranger)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Only the channel owner can clear reports"


# =========================================================================
# UPDATE ITEM — edit history + alert re-trigger
# =========================================================================

def _patch_process_new_item(monkeypatch):
    calls = []
    monkeypatch.setattr(item_status, "process_new_item", lambda db, item_id: calls.append(item_id))
    return calls


def test_update_item_applies_fields_and_logs_edits(db_session, monkeypatch):
    """Changing title + price -> both applied, exactly 2 ItemEdit records."""
    channel = _make_channel(db_session, registered_by=95001)
    item = _make_item(db_session, channel, price=100.0, title="Old title")
    owner = _make_user(db_session, 95001)
    _patch_process_new_item(monkeypatch)

    updated = item_status.update_item(
        db_session, item.id, owner,
        ItemUpdateRequest(title="New title", price=250.0),
    )

    assert updated.title == "New title"
    assert updated.price == 250.0
    assert _edit_count(db_session, item.id) == 2
    fields = db_session.scalars(
        select(ItemEdit.field).where(ItemEdit.item_id == item.id)
    ).all()
    assert set(fields) == {"title", "price"}


def test_update_item_noop_creates_no_edit_records(db_session, monkeypatch):
    """Sending the same values back -> no ItemEdit records."""
    channel = _make_channel(db_session, registered_by=96001)
    item = _make_item(db_session, channel, price=100.0, title="Same title")
    owner = _make_user(db_session, 96001)
    _patch_process_new_item(monkeypatch)

    item_status.update_item(
        db_session, item.id, owner,
        ItemUpdateRequest(title="Same title", price=100.0),
    )

    assert _edit_count(db_session, item.id) == 0


def test_update_item_non_owner_forbidden(db_session, monkeypatch):
    channel = _make_channel(db_session, registered_by=97001)
    item = _make_item(db_session, channel)
    stranger = _make_user(db_session, 97999)
    _patch_process_new_item(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        item_status.update_item(db_session, item.id, stranger, ItemUpdateRequest(title="Hack"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You can only edit items in your own channels"


def test_update_item_price_change_retriggers_alerting(db_session, monkeypatch):
    """Price change -> process_new_item re-triggered exactly once."""
    channel = _make_channel(db_session, registered_by=98001)
    item = _make_item(db_session, channel, price=100.0)
    owner = _make_user(db_session, 98001)
    calls = _patch_process_new_item(monkeypatch)

    item_status.update_item(db_session, item.id, owner, ItemUpdateRequest(price=150.0))

    assert calls == [item.id]


def test_update_item_title_only_does_not_retrigger_alerting(db_session, monkeypatch):
    """Title-only change -> NO process_new_item call."""
    channel = _make_channel(db_session, registered_by=99001)
    item = _make_item(db_session, channel, title="Old")
    owner = _make_user(db_session, 99001)
    calls = _patch_process_new_item(monkeypatch)

    item_status.update_item(db_session, item.id, owner, ItemUpdateRequest(title="New"))

    assert calls == []


def test_update_item_specs_change_logged_and_retriggers(db_session, monkeypatch):
    """Specs change -> one ItemEdit, specs persisted as JSON, alerting re-triggered."""
    channel = _make_channel(db_session, registered_by=100001)
    item = _make_item(db_session, channel)
    owner = _make_user(db_session, 100001)
    calls = _patch_process_new_item(monkeypatch)

    item_status.update_item(
        db_session, item.id, owner,
        ItemUpdateRequest(specs={"brand": "X", "model": "Y"}),
    )

    assert _edit_count(db_session, item.id) == 1
    assert json.loads(db_session.get(Item, item.id).specs) == {"brand": "X", "model": "Y"}
    assert calls == [item.id]

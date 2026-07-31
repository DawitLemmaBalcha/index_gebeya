"""
Unit tests for services/owner_dm.py — Telegram owner-DM delivery.

The module has two adapters over the same domain concept:
  - send_owner_dm      (async, for route handlers)
  - send_owner_dm_sync (sync, for the cleanup background thread)

Both are best-effort: they log warnings on failure and NEVER raise.
Behavioral invariants preserved from the original implementations:
  - channel lookup, early return when no owner (registered_by is None)
  - missing BOT_TOKEN -> warning, no HTTP call
  - non-200 response  -> warning, no raise
"""

import json

import httpx
import pytest

import services.owner_dm as owner_dm
from models import Channel


def _make_channel(db_session, registered_by):
    channel = Channel(
        username=f"chan_{registered_by if registered_by is not None else 'no_owner'}",
        registered_by=registered_by,
    )
    db_session.add(channel)
    db_session.commit()
    return channel


def _patch_async_client(monkeypatch, handler):
    """Route send_owner_dm's httpx.AsyncClient through a MockTransport."""
    original_client = httpx.AsyncClient  # capture BEFORE patching (avoid recursion)
    calls = []

    def record(request):
        calls.append(request)
        return handler(request)

    def factory(**kwargs):
        return original_client(transport=httpx.MockTransport(record), **kwargs)

    monkeypatch.setattr(owner_dm.httpx, "AsyncClient", factory)
    return calls


# =========================================================================
# ASYNC ADAPTER (route handlers)
# =========================================================================

@pytest.mark.asyncio
async def test_send_owner_dm_owner_exists_and_sends(db_session, monkeypatch):
    """Owner present + BOT_TOKEN set -> exactly one POST with chat_id/text."""
    channel = _make_channel(db_session, registered_by=12345)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = _patch_async_client(monkeypatch, lambda req: httpx.Response(200, json={"ok": True}))

    await owner_dm.send_owner_dm(db_session, channel.id, "Hello owner")

    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert calls[0].url.path == f"/bot123:TESTTOKEN/sendMessage"
    assert body["chat_id"] == 12345
    assert body["text"] == "Hello owner"


@pytest.mark.asyncio
async def test_send_owner_dm_no_registered_by_no_call(db_session, monkeypatch):
    """Channel without an owner -> no HTTP call."""
    channel = _make_channel(db_session, registered_by=None)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = _patch_async_client(monkeypatch, lambda req: httpx.Response(200, json={"ok": True}))

    await owner_dm.send_owner_dm(db_session, channel.id, "Hello")

    assert calls == []


@pytest.mark.asyncio
async def test_send_owner_dm_missing_channel_no_call(db_session, monkeypatch):
    """Nonexistent channel -> no HTTP call."""
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = _patch_async_client(monkeypatch, lambda req: httpx.Response(200, json={"ok": True}))

    await owner_dm.send_owner_dm(db_session, 999999, "Hello")

    assert calls == []


@pytest.mark.asyncio
async def test_send_owner_dm_missing_token_no_call(db_session, monkeypatch, caplog):
    """BOT_TOKEN not set -> warning logged, no HTTP call, no raise."""
    channel = _make_channel(db_session, registered_by=12345)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", None)

    calls = _patch_async_client(monkeypatch, lambda req: httpx.Response(200, json={"ok": True}))

    await owner_dm.send_owner_dm(db_session, channel.id, "Hello")

    assert calls == []
    assert any("BOT_TOKEN not set" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_send_owner_dm_http_error_warns_but_never_raises(db_session, monkeypatch, caplog):
    """Non-200 response -> warning logged, no exception raised."""
    channel = _make_channel(db_session, registered_by=12345)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = _patch_async_client(monkeypatch, lambda req: httpx.Response(500, text="bot exploded"))

    await owner_dm.send_owner_dm(db_session, channel.id, "Hello")

    assert len(calls) == 1
    assert any("DM send failed" in r.message for r in caplog.records)


# =========================================================================
# SYNC ADAPTER (cleanup background thread)
# =========================================================================

def test_send_owner_dm_sync_owner_exists_and_sends(db_session, monkeypatch):
    """Sync adapter opens its own session; owner present -> one POST."""
    channel = _make_channel(db_session, registered_by=54321)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = []

    def fake_post(url, json=None, timeout=10.0):
        calls.append((url, json))
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(owner_dm.httpx, "post", fake_post)

    owner_dm.send_owner_dm_sync(channel.id, "Cleanup message")

    assert len(calls) == 1
    url, body = calls[0]
    assert url == f"https://api.telegram.org/bot123:TESTTOKEN/sendMessage"
    assert body["chat_id"] == 54321
    assert body["text"] == "Cleanup message"


def test_send_owner_dm_sync_no_owner_no_call(db_session, monkeypatch):
    """Sync adapter: channel without owner -> no HTTP call."""
    channel = _make_channel(db_session, registered_by=None)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = []
    monkeypatch.setattr(
        owner_dm.httpx, "post", lambda url, json=None, timeout=10.0: calls.append(url)
    )

    owner_dm.send_owner_dm_sync(channel.id, "Cleanup message")

    assert calls == []


def test_send_owner_dm_sync_missing_token_no_call(db_session, monkeypatch, caplog):
    """Sync adapter: BOT_TOKEN not set -> warning logged, no HTTP call."""
    channel = _make_channel(db_session, registered_by=54321)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", None)

    calls = []
    monkeypatch.setattr(
        owner_dm.httpx, "post", lambda url, json=None, timeout=10.0: calls.append(url)
    )

    owner_dm.send_owner_dm_sync(channel.id, "Cleanup message")

    assert calls == []
    assert any("BOT_TOKEN not set" in r.message for r in caplog.records)


def test_send_owner_dm_sync_http_error_warns_but_never_raises(db_session, monkeypatch, caplog):
    """Sync adapter: non-200 -> warning logged, no raise."""
    channel = _make_channel(db_session, registered_by=54321)
    monkeypatch.setattr(owner_dm, "BOT_TOKEN", "123:TESTTOKEN")

    calls = []

    def fake_post(url, json=None, timeout=10.0):
        calls.append(url)
        return httpx.Response(500, text="bot exploded")

    monkeypatch.setattr(owner_dm.httpx, "post", fake_post)

    owner_dm.send_owner_dm_sync(channel.id, "Cleanup message")

    assert len(calls) == 1
    assert any("DM send failed" in r.message for r in caplog.records)

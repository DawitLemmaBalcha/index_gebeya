"""
Unit tests for TECH-07: Channel Photo Refresher Logic
Tests the listener/photo_refresher.py module using mocks.
Run with: pytest tests/test_photo_refresher.py -v

Coverage:
  T9:  Daily refresher updates photo when it changes
  T10: Daily refresher skips channels with unchanged photos
  T11: Daily refresher nullifies photo when channel removes it
  T12: Daily refresher handles API failure gracefully
  T13: Daily refresher handles Telegram errors per-channel
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# Mock external dependencies BEFORE importing photo_refresher.
# The host environment may not have python-telegram-bot installed,
# and /app/media may not exist.
# ===========================================================================
from types import ModuleType

# --- Mock 'telegram' and 'telegram.error' ---
_mock_telegram = ModuleType("telegram")
_mock_telegram_error = ModuleType("telegram.error")


class _MockBot:
    """Mock for telegram.Bot that can be configured per-test via AsyncMock."""


class TelegramError(Exception):
    """Mock for telegram.error.TelegramError."""


_mock_telegram.Bot = _MockBot
_mock_telegram_error.TelegramError = TelegramError
_mock_telegram.error = _mock_telegram_error

sys.modules["telegram"] = _mock_telegram
sys.modules["telegram.error"] = _mock_telegram_error

# --- Mock 'config' module to provide constants and avoid /app/media creation ---
_mock_config = ModuleType("config")
_mock_config.logger = MagicMock()
_mock_config.API_BASE = "http://mock-api:8000"
_mock_config.CHANNEL_PHOTO_REFRESH_INTERVAL = 0.1
_mock_config.MEDIA_DIR = "/tmp/mock_media_test"
sys.modules["config"] = _mock_config

os.makedirs("/tmp/mock_media_test", exist_ok=True)

# Ensure the listener package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "listener"))

# Reset the mock logger between tests
def _reset_logger():
    _mock_config.logger.reset_mock()

# ===========================================================================
# Helper classes
# ===========================================================================

class MockChatPhoto:
    """Mock for telegram.ChatPhoto."""
    def __init__(self, big_file_id):
        self.big_file_id = big_file_id


class MockChat:
    """Mock for telegram.Chat."""
    def __init__(self, username, photo_big_file_id=None):
        self.username = username
        self.photo = MockChatPhoto(photo_big_file_id) if photo_big_file_id else None


class _StopLoop(Exception):
    """Raised to break the infinite loop in the refresher after one cycle."""


def _make_mock_client(get_json_response, patch_call_log):
    """
    Factory that returns a MockClient class that returns the given JSON
    on GET and records PATCH calls into patch_call_log.
    """
    _response = get_json_response  # capture for closure
    _log = patch_call_log

    class _MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            obj = type('_R', (), {})()
            obj.status_code = 200
            obj.json = lambda: _response
            return obj

        async def patch(self, url, **kwargs):
            _log.append({
                "url": url,
                "json": kwargs.get("json", {}),
            })
            obj = type('_R', (), {})()
            obj.status_code = 200
            obj.json = lambda: {}
            return obj

    return _MockClient


def _make_failing_mock_client(status_code=500):
    """Factory that returns a MockClient whose GET always fails."""
    _status = status_code  # capture for closure

    class _FailingMockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            obj = type('_R', (), {})()
            obj.status_code = _status
            return obj

        async def patch(self, url, **kwargs):
            obj = type('_R', (), {})()
            obj.status_code = 200
            obj.json = lambda: {}
            return obj

    return _FailingMockClient


# =========================================================================
# T9: Daily refresher updates photo when it changes
# =========================================================================

@pytest.mark.asyncio
async def test_refresher_updates_photo_when_changed():
    """
    T9: Set a channel's photo_file_id to a known old value.
    Run the refresher for one loop iteration.
    Verify PATCH /channels/{channel_id} is called with the new photo_file_id.
    """
    _reset_logger()
    from photo_refresher import channel_photo_refresher

    old_photo_id = "old_big_file_id_123"
    new_photo_id = "new_big_file_id_456"

    channels_response = [
        {"id": 1, "username": "testchannel", "photo_file_id": old_photo_id,
         "title": "Test", "review_count": 5, "trust_score": 3.5, "is_verified": False}
    ]

    patch_call_log = []
    MockClient = _make_mock_client(channels_response, patch_call_log)

    mock_bot = AsyncMock()
    mock_chat = MockChat("testchannel", photo_big_file_id=new_photo_id)
    mock_bot.get_chat = AsyncMock(return_value=mock_chat)

    loop_count = [0]

    async def mock_sleep(seconds):
        loop_count[0] += 1
        if loop_count[0] >= 2:
            raise _StopLoop()

    with patch("httpx.AsyncClient", MockClient), \
         patch("asyncio.sleep", mock_sleep):

        try:
            await channel_photo_refresher(mock_bot)
        except _StopLoop:
            pass

    mock_bot.get_chat.assert_called_with("@testchannel")
    patch_for_ch1 = [c for c in patch_call_log if "/channels/1" in c["url"]]
    assert len(patch_for_ch1) >= 1, f"Expected PATCH for channel 1, got {patch_call_log}"
    assert patch_for_ch1[0]["json"]["photo_file_id"] == new_photo_id, (
        f"Expected {new_photo_id}, got {patch_for_ch1[0]['json']}"
    )


# =========================================================================
# T10: Daily refresher skips channels with unchanged photos
# =========================================================================

@pytest.mark.asyncio
async def test_refresher_skips_unchanged_photos():
    """
    T10: Set a channel's photo_file_id to the correct current value.
    Run the refresher. Verify PATCH is NOT called for this channel.
    """
    _reset_logger()
    from photo_refresher import channel_photo_refresher

    current_photo_id = "same_photo_id_789"

    channels_response = [
        {"id": 2, "username": "unchangedchannel", "photo_file_id": current_photo_id,
         "title": "Unchanged", "review_count": 3, "trust_score": 4.0, "is_verified": True}
    ]

    patch_call_log = []
    MockClient = _make_mock_client(channels_response, patch_call_log)

    mock_bot = AsyncMock()
    mock_chat = MockChat("unchangedchannel", photo_big_file_id=current_photo_id)
    mock_bot.get_chat = AsyncMock(return_value=mock_chat)

    loop_count = [0]

    async def mock_sleep(seconds):
        loop_count[0] += 1
        if loop_count[0] >= 2:
            raise _StopLoop()

    with patch("httpx.AsyncClient", MockClient), \
         patch("asyncio.sleep", mock_sleep):

        try:
            await channel_photo_refresher(mock_bot)
        except _StopLoop:
            pass

    patch_for_ch2 = [c for c in patch_call_log if "/channels/2" in c["url"]]
    assert len(patch_for_ch2) == 0, (
        f"Expected NO PATCH for channel 2 (photo unchanged), got: {patch_call_log}"
    )


# =========================================================================
# T11: Daily refresher nullifies photo when channel removes it
# =========================================================================

@pytest.mark.asyncio
async def test_refresher_nullifies_photo_when_removed():
    """
    T11: Set a channel's photo_file_id to a value, but the channel
    no longer has a photo in Telegram. Verify PATCH is called with
    {"photo_file_id": null}.
    """
    _reset_logger()
    from photo_refresher import channel_photo_refresher

    old_photo_id = "old_photo_that_was_removed"

    channels_response = [
        {"id": 3, "username": "removedphotochannel", "photo_file_id": old_photo_id,
         "title": "Photo Removed", "review_count": 1, "trust_score": 2.0, "is_verified": False}
    ]

    patch_call_log = []
    MockClient = _make_mock_client(channels_response, patch_call_log)

    mock_bot = AsyncMock()
    mock_chat = MockChat("removedphotochannel", photo_big_file_id=None)
    mock_bot.get_chat = AsyncMock(return_value=mock_chat)

    loop_count = [0]

    async def mock_sleep(seconds):
        loop_count[0] += 1
        if loop_count[0] >= 2:
            raise _StopLoop()

    with patch("httpx.AsyncClient", MockClient), \
         patch("asyncio.sleep", mock_sleep):

        try:
            await channel_photo_refresher(mock_bot)
        except _StopLoop:
            pass

    patch_for_ch3 = [c for c in patch_call_log if "/channels/3" in c["url"]]
    assert len(patch_for_ch3) >= 1, f"Expected PATCH for channel 3, got: {patch_call_log}"

    nullify_calls = [c for c in patch_for_ch3 if c["json"].get("photo_file_id") is None]
    assert len(nullify_calls) >= 1, (
        f"Expected nullify PATCH, got: {patch_for_ch3}"
    )


# =========================================================================
# T12: Daily refresher handles API failure gracefully
# =========================================================================

@pytest.mark.asyncio
async def test_refresher_handles_api_failure_gracefully():
    """
    T12: Simulate the backend /channels/ endpoint returning an error (500).
    Verify the refresher logs an error and sleeps before retrying.
    Verify the refresher does not crash.
    """
    _reset_logger()
    from photo_refresher import channel_photo_refresher

    FailingClient = _make_failing_mock_client(status_code=500)
    mock_bot = AsyncMock()

    loop_count = [0]

    async def mock_sleep(seconds):
        loop_count[0] += 1
        if loop_count[0] >= 3:
            raise _StopLoop()

    with patch("httpx.AsyncClient", FailingClient), \
         patch("asyncio.sleep", mock_sleep):

        try:
            await channel_photo_refresher(mock_bot)
        except _StopLoop:
            pass

    # Should have retried at least twice
    assert loop_count[0] >= 2, f"Expected refresher to retry, loop count: {loop_count[0]}"

    # Verify error logged — check directly via the refreshed import's logger
    import photo_refresher as pr
    error_logger = pr.logger
    error_calls = [
        c for c in error_logger.error.call_args_list
        if "Failed to fetch channels" in str(c)
    ]
    if len(error_calls) < 1:
        # Fallback: check _mock_config.logger too
        error_calls = [
            c for c in _mock_config.logger.error.call_args_list
            if "Failed to fetch channels" in str(c)
        ]
    assert len(error_calls) >= 1, f"Expected error log for failed channel fetch. error calls: {error_logger.error.call_args_list}, all calls: {error_logger.mock_calls}"


# =========================================================================
# T13: Daily refresher handles Telegram errors per-channel
# =========================================================================

@pytest.mark.asyncio
async def test_refresher_handles_telegram_errors_per_channel():
    """
    T13: Simulate getChat raising a TelegramError for one channel
    but succeeding for another. Verify the errored channel is skipped
    and the refresher continues to the next channel.
    """
    _reset_logger()
    from photo_refresher import channel_photo_refresher

    channels_response = [
        {"id": 10, "username": "goodchannel", "photo_file_id": "old_10",
         "title": "Good", "review_count": 5, "trust_score": 4.0, "is_verified": True},
        {"id": 11, "username": "bannedchannel", "photo_file_id": "old_11",
         "title": "Banned", "review_count": 0, "trust_score": 0.0, "is_verified": False},
        {"id": 12, "username": "anothergood", "photo_file_id": "old_12",
         "title": "Another", "review_count": 2, "trust_score": 3.0, "is_verified": False},
    ]

    patch_call_log = []
    MockClient = _make_mock_client(channels_response, patch_call_log)

    mock_bot = AsyncMock()

    async def mock_get_chat(chat_id):
        if chat_id == "@bannedchannel":
            raise TelegramError("Bot was kicked from the channel")
        elif chat_id == "@goodchannel":
            return MockChat("goodchannel", photo_big_file_id="new_10")
        elif chat_id == "@anothergood":
            return MockChat("anothergood", photo_big_file_id="new_12")
        raise ValueError(f"Unexpected chat_id: {chat_id}")

    mock_bot.get_chat = mock_get_chat

    loop_count = [0]

    async def mock_sleep(seconds):
        loop_count[0] += 1
        if loop_count[0] >= 3:
            raise _StopLoop()

    with patch("httpx.AsyncClient", MockClient), \
         patch("asyncio.sleep", mock_sleep):

        try:
            await channel_photo_refresher(mock_bot)
        except _StopLoop:
            pass

    # Verify PATCH was called for good channels
    good_patches = [c for c in patch_call_log
                    if "/channels/10" in c["url"] or "/channels/12" in c["url"]]
    assert len(good_patches) >= 2, (
        f"Expected PATCH for channels 10 and 12, got {patch_call_log}"
    )

    # Verify PATCH was NOT called for banned channel
    banned_patches = [c for c in patch_call_log if "/channels/11" in c["url"]]
    assert len(banned_patches) == 0, (
        f"Expected NO PATCH for banned channel 11, got: {banned_patches}"
    )

    # Verify warning logged for Telegram error
    warning_calls = [
        c for c in _mock_config.logger.warning.call_args_list
        if "Telegram error" in str(c) or "bannedchannel" in str(c)
    ]
    assert len(warning_calls) >= 1, "Expected warning log for banned channel"


# =========================================================================
# Edge case: channel with no username is skipped
# =========================================================================

@pytest.mark.asyncio
async def test_refresher_skips_channel_without_username():
    """
    Verify that channels with no username are skipped without error.
    """
    _reset_logger()
    from photo_refresher import channel_photo_refresher

    channels_response = [
        {"id": 99, "username": None, "photo_file_id": "some_photo",
         "title": "No Username", "review_count": 0, "trust_score": 0.0, "is_verified": False},
        {"id": 100, "username": "", "photo_file_id": "some_photo_2",
         "title": "Empty Username", "review_count": 0, "trust_score": 0.0, "is_verified": False},
    ]

    patch_call_log = []
    MockClient = _make_mock_client(channels_response, patch_call_log)

    mock_bot = AsyncMock()
    mock_bot.get_chat = AsyncMock()

    loop_count = [0]

    async def mock_sleep(seconds):
        loop_count[0] += 1
        if loop_count[0] >= 2:
            raise _StopLoop()

    with patch("httpx.AsyncClient", MockClient), \
         patch("asyncio.sleep", mock_sleep):

        try:
            await channel_photo_refresher(mock_bot)
        except _StopLoop:
            pass

    # get_chat should NOT have been called (no valid username)
    mock_bot.get_chat.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

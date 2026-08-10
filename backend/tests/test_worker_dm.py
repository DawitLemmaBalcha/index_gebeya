"""
NB-55: the Indexed/Updated owner DM (listener/worker.py success branch).

Stubs the `telegram` module (minimal InlineKeyboardButton /
InlineKeyboardMarkup / WebAppInfo classes) BEFORE importing worker,
monkeypatches worker.get_item_api / send_to_api / get_channel_info and
drives the worker with a FakeBot. Asserts:

  - both is_replaced variants render the right headline text;
  - the rich body carries the description and the spec summary
    (skip-set keys location/condition never surface);
  - one buttons row with "✏️ Edit product" + "🚀 Boost this product",
    both WebAppInfo deep-links to {WEB_APP_URL}/stores/{channelId}/{itemId};
  - the photo-message path when media exists (send_photo with the caption,
    processing DM deleted best-effort);
  - fetch failure falls back to today's text DM + the boost button.
"""
import asyncio
import json
import os
import sys
import types

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LISTENER_DIR = os.path.join(_REPO_ROOT, "listener")
if _LISTENER_DIR not in sys.path:
    sys.path.insert(0, _LISTENER_DIR)


# ---------------------------------------------------------------------------
# telegram module stub (installed before `import worker`)
# ---------------------------------------------------------------------------
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

import worker  # noqa: E402  (must follow the stub install)

WEB_APP_URL = worker.WEB_APP_URL


class FakeMessage:
    def __init__(self):
        self.edited = None
        self.deleted = False

    async def edit_text(self, text, reply_markup=None):
        self.edited = {"text": text, "reply_markup": reply_markup}

    async def delete(self):
        self.deleted = True


class FakeBot:
    def __init__(self):
        self.dm = FakeMessage()
        self.photo = FakeMessage()
        self.send_photo_calls = []

    async def send_message(self, chat_id, text):
        return self.dm

    async def send_photo(self, chat_id, photo, caption, reply_markup=None, parse_mode=None):
        self.send_photo_calls.append({
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "reply_markup": reply_markup,
        })
        return self.photo


def _item_details(**overrides):
    details = {
        "id": 42,
        "title": "iPhone 13 128GB",
        "price": 250.0,
        "currency": "ETB",
        "description": "Brand new sealed iPhone 13.",
        "specs": '{"brand": "Samsung", "model": "Galaxy S21", "condition": "New", "location": "AA"}',
        "category": "Mobile Phones",
        "subcategory": "Android Phones",
        "image_path": None,
        "images": [],
    }
    details.update(overrides)
    return details


async def _process_one(bot, *, replaced, item_details):
    """Run background_worker for exactly one queue job; return the bot."""
    queue = asyncio.Queue()
    await queue.put({"message_id": 11, "channel_name": "testchannel"})

    async def _send_to_api(payload):
        return {
            "success": True,
            "item_id": 42,
            "title": "iPhone 13 128GB",
            "price": 250.0,
            "replaced": replaced,
        }

    async def _get_channel_info(channel_name):
        return {"id": 7, "registered_by": 111, "indexing_paused": False, "is_active": True}

    async def _get_item_api(item_id):
        return item_details

    worker.send_to_api = _send_to_api
    worker.get_channel_info = _get_channel_info
    worker.get_item_api = _get_item_api
    worker.HEARTBEAT_INTERVAL = 0.01

    task = asyncio.create_task(worker.background_worker(queue, bot))
    try:
        await asyncio.wait_for(queue.join(), timeout=10)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return bot


def _button_labels(markup):
    return [b.text for row in markup.inline_keyboard for b in row]


class TestWorkerRichDM:
    def test_text_path_has_edit_and_boost_buttons_and_rich_body(self):
        bot = asyncio.run(_process_one(FakeBot(), replaced=False, item_details=_item_details()))
        assert bot.dm.edited is not None
        text = bot.dm.edited["text"]
        assert "✅ Indexed: iPhone 13 128GB — 250 ETB" in text
        assert "Brand new sealed iPhone 13." in text  # description
        assert "Samsung" in text                      # spec summary values
        assert "Galaxy S21" in text
        assert "New" not in text                      # condition skipped
        assert "AA" not in text                       # location skipped

        row = bot.dm.edited["reply_markup"].inline_keyboard[0]
        assert [b.text for b in row] == ["✏️ Edit product", "🚀 Boost this product"]
        for b in row:
            assert b.web_app.url == f"{WEB_APP_URL}/stores/7/42"

    def test_replaced_variant_uses_updated_headline(self):
        bot = asyncio.run(_process_one(FakeBot(), replaced=True, item_details=_item_details()))
        text = bot.dm.edited["text"]
        assert "✅ Updated: iPhone 13 128GB — 250 ETB" in text
        assert "Replaced previous listing" in text

    def test_description_suppressed_when_no_description(self):
        details = _item_details(description="No description")
        bot = asyncio.run(_process_one(FakeBot(), replaced=False, item_details=details))
        text = bot.dm.edited["text"]
        assert "No description" not in text
        assert "Samsung" in text

    def test_photo_path_sends_photo_and_deletes_processing_dm(self):
        details = _item_details(images=["album1.jpg", "album2.jpg"])
        bot = asyncio.run(_process_one(FakeBot(), replaced=False, item_details=details))
        assert len(bot.send_photo_calls) == 1
        call = bot.send_photo_calls[0]
        assert call["chat_id"] == 111
        assert call["photo"] == f"{WEB_APP_URL}/media/album1.jpg"
        assert "Brand new sealed iPhone 13." in call["caption"]
        assert "Samsung" in call["caption"]
        assert bot.dm.deleted is True
        assert [b.text for b in call["reply_markup"].inline_keyboard[0]] == [
            "✏️ Edit product",
            "🚀 Boost this product",
        ]

    def test_photo_path_falls_back_to_image_path_when_no_gallery(self):
        details = _item_details(images=[], image_path="thumb.jpg")
        bot = asyncio.run(_process_one(FakeBot(), replaced=False, item_details=details))
        assert bot.send_photo_calls[0]["photo"] == f"{WEB_APP_URL}/media/thumb.jpg"

    def test_fetch_failure_falls_back_to_text_dm_with_boost_button(self):
        bot = asyncio.run(_process_one(FakeBot(), replaced=False, item_details=None))
        assert bot.dm.edited is not None
        text = bot.dm.edited["text"]
        assert "✅ Indexed: iPhone 13 128GB — 250 ETB" in text
        assert "Samsung" not in text
        assert "Brand new sealed iPhone 13." not in text
        row = bot.dm.edited["reply_markup"].inline_keyboard[0]
        assert [b.text for b in row] == ["🚀 Boost this product"]
        assert row[0].web_app.url == f"{WEB_APP_URL}/stores/7/42"

    def test_specs_parsed_from_json_string(self):
        details = _item_details(specs=json.dumps({"brand": "Nokia", "condition": "Used"}))
        bot = asyncio.run(_process_one(FakeBot(), replaced=False, item_details=details))
        text = bot.dm.edited["text"]
        assert "Nokia" in text
        assert "Used" not in text

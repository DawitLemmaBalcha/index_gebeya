import asyncio
import json
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from client import send_to_api, get_channel_info, get_item_api
from config import logger, HEARTBEAT_INTERVAL, MAX_RETRIES_LIMIT, WEB_APP_URL
from stats import stats


async def background_worker(queue: asyncio.Queue, bot):
    """
    Serial Worker with Fixed Heartbeat + Processing DM Lifecycle (TECH-19).
    - Processes 1 item at a time.
    - Waits FIXED_INTERVAL seconds between every attempt.
    - Retries same item up to MAX_RETRIES before dropping.
    - Checks channel metadata before ingesting:
      - If channel is paused (indexing_paused=True), skip ingestion.
      - If channel is removed (is_active=False), skip ingestion.
      - If channel has a registered_by user, send/edit processing DMs.
    """
    logger.info(f"🔧 Worker Started (Heartbeat: {HEARTBEAT_INTERVAL}s | Max Retries: {MAX_RETRIES_LIMIT})")
    
    while True:
        # 1. Pull Job (Waits here if queue is empty)
        payload = await queue.get()
        message_id = payload.get('message_id', 'unknown')
        channel_name = payload.get('channel_name')

        # --- TECH-19: Check channel metadata before processing ---
        dm_message = None  # telegram.Message object if DM was sent
        channel_info = None

        if channel_name:
            channel_info = await get_channel_info(channel_name)

        if channel_info is not None:
            # Channel exists in DB — check pause/remove gates
            if channel_info.get('indexing_paused'):
                logger.info(f"⏸️ Skipping msg #{message_id}: @{channel_name} is paused")
                queue.task_done()
                continue

            if not channel_info.get('is_active'):
                logger.info(f"🗑️ Skipping msg #{message_id}: @{channel_name} was removed")
                queue.task_done()
                continue

        # --- Send initial processing DM if owner is registered ---
        if channel_info is not None and channel_info.get('registered_by'):
            registered_by = channel_info['registered_by']
            try:
                dm_message = await bot.send_message(
                    chat_id=registered_by,
                    text=f"⏳ Processing your post from @{channel_name}..."
                )
                logger.info(f"📨 Sent initial DM to {registered_by} for msg #{message_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to send initial DM to {registered_by}: {e}")
                dm_message = None  # Don't try to edit if initial send failed

        # --- 2. Processing Loop (The "Jammed Gun" logic) ---
        retry_count = 0
        result = None

        while True:
            # Try to send
            result = await send_to_api(payload)

            if result and result.get('success'):
                break

            # Failed? Check if we should retry.
            retry_count += 1
            if retry_count >= MAX_RETRIES_LIMIT:
                logger.error(f"💀 DEAD LETTER: Dropping msg #{message_id} after {retry_count} failures.")
                break

            # Log Retry
            logger.warning(f"♻️ Retry {retry_count}/{MAX_RETRIES_LIMIT} for msg #{message_id} in {HEARTBEAT_INTERVAL}s...")

            # WAIT before retrying (The Heartbeat)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

        # --- NB-50: record ingest stats for the heartbeat payload ---
        if result and result.get('success'):
            stats["items_processed_total"] += 1
            stats["last_update_at"] = time.time()

        # --- TECH-19: Edit DM with result ---
        if dm_message is not None and result is not None:
            try:
                if result.get('success'):
                    title = result.get('title')
                    price = result.get('price')
                    is_replaced = result.get('replaced', False)

                    if price:
                        formatted_price = f"{price:.0f} ETB"
                    else:
                        formatted_price = "Ask for Price"

                    if is_replaced:
                        edit_text = f"✅ Updated: {title} — {formatted_price}\n⚠️ Replaced previous listing. Use different images for different products."
                    else:
                        edit_text = f"✅ Indexed: {title} — {formatted_price}"

                    # NB-45 (Rule 5.1/5.2): every item-result DM carries the
                    # boost deep-link button — path params matching the
                    # App.jsx route /stores/:channelId/:itemId (§2.7/§2.8).
                    # NB-55 (Rule 1.1/1.2): the Edit door sits beside Boost —
                    # both are WebAppInfo doors into the web app, never a
                    # Telegram DM editing flow.
                    channel_id = channel_info.get('id') if channel_info else None
                    reply_markup = None
                    reply_markup_boost = None
                    if channel_id and result.get('item_id'):
                        stores_url = f"{WEB_APP_URL}/stores/{channel_id}/{result['item_id']}"
                        reply_markup = InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                "✏️ Edit product",
                                web_app=WebAppInfo(url=stores_url),
                            ),
                            InlineKeyboardButton(
                                "🚀 Boost this product",
                                web_app=WebAppInfo(url=stores_url),
                            ),
                        ]])
                        # NB-55: the fetch-failure fallback keeps the legacy
                        # single boost button (the DM never breaks).
                        reply_markup_boost = InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                "🚀 Boost this product",
                                web_app=WebAppInfo(url=stores_url),
                            ),
                        ]])

                    # NB-55 (Rule 1.1): the rich Indexed/Updated DM — the
                    # full picture (description + spec summary + photo), not
                    # just the title line. Telegram cannot edit text into a
                    # photo, so media goes out as a NEW photo message and the
                    # processing DM is deleted best-effort. Any fetch or send
                    # failure falls back to today's text DM + the boost button.
                    item_details = None
                    if result.get('item_id'):
                        item_details = await get_item_api(result['item_id'])

                    if item_details is not None:
                        body = edit_text
                        description = item_details.get('description')
                        if description and description != 'No description':
                            body += f"\n\n📝 {description}"
                        specs_text = _build_spec_summary(item_details.get('specs'))
                        if specs_text:
                            body += f"\n\n_{specs_text}_"

                        media_path = None
                        images = item_details.get('images') or []
                        if images:
                            media_path = images[0]
                        elif item_details.get('image_path'):
                            media_path = item_details['image_path']

                        if media_path:
                            try:
                                await bot.send_photo(
                                    chat_id=registered_by,
                                    photo=f"{WEB_APP_URL}/media/{media_path}",
                                    caption=body,
                                    reply_markup=reply_markup,
                                )
                                try:
                                    await dm_message.delete()
                                except Exception as e:
                                    logger.warning(f"⚠️ Failed to delete processing DM for msg #{message_id}: {e}")
                            except Exception as e:
                                logger.warning(f"⚠️ Photo DM failed for msg #{message_id}, falling back to text: {e}")
                                await dm_message.edit_text(edit_text, reply_markup=reply_markup_boost)
                        else:
                            await dm_message.edit_text(body, reply_markup=reply_markup)
                    else:
                        await dm_message.edit_text(edit_text, reply_markup=reply_markup_boost)

                    logger.info(f"📝 Edited DM with success for msg #{message_id} (replaced={is_replaced})")
                else:
                    await dm_message.edit_text(
                        f"❌ Could not process your post from @{channel_name}. "
                        f"The post may not contain a product or an image."
                    )
                    logger.info(f"📝 Edited DM with failure for msg #{message_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to edit DM for msg #{message_id}: {e}")

        # 3. Cleanup & Pace
        queue.task_done()
        
        # Even on success, we wait the heartbeat interval to ensure steady pacing
        success = result and result.get('success') if result else False
        if success:
            logger.info(f"💤 Resting for {HEARTBEAT_INTERVAL}s...")
            await asyncio.sleep(HEARTBEAT_INTERVAL)


def _build_spec_summary(specs) -> str:
    """NB-55: the top 3-4 relevant spec values for the rich owner DM — the
    exact skip-set pattern from listener/notifications.py (location,
    condition, contact_phone, phone_number never surface in DMs)."""
    if not specs:
        return ""
    if isinstance(specs, str):
        try:
            specs = json.loads(specs.replace("'", '"'))
        except Exception:
            return ""
    if not isinstance(specs, dict):
        return ""
    skip_keys = {'location', 'condition', 'contact_phone', 'phone_number'}
    relevant = {k: v for k, v in specs.items() if k.lower() not in skip_keys}
    if not relevant:
        return ""
    return ' | '.join(str(v) for v in list(relevant.values())[:4])
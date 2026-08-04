import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from client import send_to_api, get_channel_info
from config import logger, HEARTBEAT_INTERVAL, MAX_RETRIES_LIMIT, WEB_APP_URL


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
                    # Generic button text; the price never appears in the DM.
                    channel_id = channel_info.get('id') if channel_info else None
                    reply_markup = None
                    if channel_id and result.get('item_id'):
                        reply_markup = InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                "🚀 Boost this product",
                                web_app=WebAppInfo(
                                    url=f"{WEB_APP_URL}/stores/{channel_id}/{result['item_id']}"
                                ),
                            )
                        ]])

                    await dm_message.edit_text(edit_text, reply_markup=reply_markup)
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
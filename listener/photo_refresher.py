import asyncio
import httpx
from telegram import Bot
from telegram.error import TelegramError
from config import logger, API_BASE, CHANNEL_PHOTO_REFRESH_INTERVAL


async def channel_photo_refresher(bot: Bot):
    """
    Daily background task that fetches current channel profile photos from Telegram
    and updates the backend when photos change. Runs in an infinite loop with a
    configurable sleep interval between cycles.
    """
    logger.info(f"📸 Channel Photo Refresher started (interval: {CHANNEL_PHOTO_REFRESH_INTERVAL}s)")

    while True:
        try:
            # 1. Fetch all channels from the backend
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{API_BASE}/channels/")
                if resp.status_code != 200:
                    logger.error(f"📸 Failed to fetch channels: {resp.status_code}")
                    await asyncio.sleep(CHANNEL_PHOTO_REFRESH_INTERVAL)
                    continue
                channels = resp.json()

            logger.info(f"📸 Refreshing photos for {len(channels)} channels")

            # 2. Determine per-channel delay to avoid rate limits
            if len(channels) > 500:
                per_channel_delay = 0.3
            elif len(channels) > 100:
                per_channel_delay = 0.5
            else:
                per_channel_delay = 1.0

            # 3. Iterate over each channel
            for ch in channels:
                channel_id = ch.get("id")
                username = ch.get("username")
                current_photo_file_id = ch.get("photo_file_id")

                if not username:
                    continue

                chat_identifier = f"@{username}"

                try:
                    chat = await bot.get_chat(chat_identifier)

                    if chat.photo:
                        new_photo_id = chat.photo.big_file_id
                        if new_photo_id != current_photo_file_id:
                            async with httpx.AsyncClient(timeout=30.0) as client:
                                patch_resp = await client.patch(
                                    f"{API_BASE}/channels/{channel_id}",
                                    json={"photo_file_id": new_photo_id},
                                )
                                if patch_resp.status_code == 200:
                                    logger.info(f"📸 Updated photo for @{username}")
                                else:
                                    logger.warning(
                                        f"📸 Failed to update photo for @{username}: {patch_resp.status_code}"
                                    )
                    else:
                        # Channel no longer has a photo — nullify if previously set
                        if current_photo_file_id is not None:
                            async with httpx.AsyncClient(timeout=30.0) as client:
                                patch_resp = await client.patch(
                                    f"{API_BASE}/channels/{channel_id}",
                                    json={"photo_file_id": None},
                                )
                                if patch_resp.status_code == 200:
                                    logger.info(f"📸 Channel @{username} no longer has a photo")
                                else:
                                    logger.warning(
                                        f"📸 Failed to nullify photo for @{username}: {patch_resp.status_code}"
                                    )

                except TelegramError as e:
                    logger.warning(f"📸 Telegram error for @{username}: {e}")
                    continue

                # Per-channel delay to avoid rate limits
                await asyncio.sleep(per_channel_delay)

            logger.info(f"📸 Channel photo refresh cycle completed. Sleeping for {CHANNEL_PHOTO_REFRESH_INTERVAL}s")

        except Exception as e:
            logger.error(f"📸 Photo refresher encountered an error: {e}")

        await asyncio.sleep(CHANNEL_PHOTO_REFRESH_INTERVAL)

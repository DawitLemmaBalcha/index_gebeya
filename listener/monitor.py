import os
import uuid
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import MEDIA_DIR, ALBUM_BUFFER_DELAY, logger

# ------------------------------------------------------------------
# MONITOR: CHANNEL INGESTION & MEDIA BUFFERS
# ------------------------------------------------------------------

# MEMORY STATE
# { media_group_id: { "text": str, "images": [paths], "task": asyncio.Task } }
ALBUM_BUFFERS = {}

async def process_album_flush(media_group_id: str, channel_username: str, message_id: int, queue: asyncio.Queue):
    """
    Called after the buffer delay. Pushes the aggregated album to the Worker Queue.
    """
    await asyncio.sleep(ALBUM_BUFFER_DELAY)
    
    if media_group_id not in ALBUM_BUFFERS:
        return

    data = ALBUM_BUFFERS.pop(media_group_id)
    images = data["images"]
    text = data["text"]
    
    logger.info(f"📦 Flushing Album {media_group_id}: {len(images)} images -> Queue")

    payload = {
        "channel_name": channel_username,
        "message_id": message_id,
        "text": text,
        "image_path": images[0] if images else None, # Thumbnail
        "album_paths": images # Full Album
    }

    # NON-BLOCKING PUSH
    await queue.put(payload)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receives Telegram Posts -> Downloads Media -> Buffers -> Pushes to Queue
    """
    post = update.channel_post or update.message
    if not post: return

    post_text = post.text or post.caption or ""
    media_group_id = post.media_group_id
    
    # Filter empty posts
    if not post_text and not post.photo: return

    # Extract Metadata
    message_id = post.message_id
    channel_username = post.chat.username or post.chat.title.replace(" ", "_") or "unknown"
    
    # Access the Global Queue passed via bot_data
    queue = context.bot_data["job_queue"]

    # --- 1. DOWNLOAD IMAGE ---
    image_rel_path = None
    if post.photo:
        try:
            photo_obj = post.photo[-1] # Largest size
            new_file = await context.bot.get_file(photo_obj.file_id)
            ext = new_file.file_path.split('.')[-1] if new_file.file_path else "jpg"
            
            filename = f"{channel_username}_{message_id}_{uuid.uuid4().hex[:6]}.{ext}"
            save_path = os.path.join(MEDIA_DIR, filename)
            
            await new_file.download_to_drive(custom_path=save_path)
            image_rel_path = filename
        except Exception as e:
            logger.error(f"⚠️ Image download failed: {e}")

    # --- 2. BUFFERING LOGIC ---
    if media_group_id:
        if media_group_id not in ALBUM_BUFFERS:
            ALBUM_BUFFERS[media_group_id] = {"text": "", "images": [], "task": None}
        
        # Aggregate
        if post_text:
            current = ALBUM_BUFFERS[media_group_id]["text"]
            ALBUM_BUFFERS[media_group_id]["text"] = (current + "\n" + post_text).strip()
            
        if image_rel_path:
            ALBUM_BUFFERS[media_group_id]["images"].append(image_rel_path)

        # Debounce Timer
        if ALBUM_BUFFERS[media_group_id]["task"]:
            ALBUM_BUFFERS[media_group_id]["task"].cancel()

        ALBUM_BUFFERS[media_group_id]["task"] = asyncio.create_task(
            process_album_flush(media_group_id, channel_username, message_id, queue)
        )
        
    else:
        # --- SINGLE POST ---
        logger.info(f"📩 Single Post #{message_id} -> Queue")
        payload = {
            "channel_name": channel_username,
            "message_id": message_id,
            "text": post_text,
            "image_path": image_rel_path,
            "album_paths": [image_rel_path] if image_rel_path else []
        }
        await queue.put(payload)
import asyncio
import sys
import logging
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from config import TELEGRAM_TOKEN, logger

# NEW IMPORTS
from monitor import handle_channel_post
from bot_ui import handle_start
from alert_conversation import alert_conv_handler
from bot_commands import handle_my_alerts, handle_alert_callback # 👈 NEW IMPORTS
from worker import background_worker
from notifications import notification_poller
from photo_refresher import channel_photo_refresher

# --- SILENCE HTTPX LOGS (POLLING NOISE) ---
logging.getLogger("httpx").setLevel(logging.WARNING)
# ------------------------------------------

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        logger.critical("❌ ERROR: TELEGRAM_BOT_TOKEN missing in .env")
        sys.exit(1)

    logger.info("--- Index Gebeya Listener (Hybrid: Ingestion + MiniApp) Online ---")

    # 1. Initialize Application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # 2. Initialize the Job Queue
    job_queue = asyncio.Queue()
    application.bot_data["job_queue"] = job_queue

    # 3. Register Handlers
    
    # A. User Commands
    application.add_handler(CommandHandler('start', handle_start))
    application.add_handler(CommandHandler('myalerts', handle_my_alerts)) # 👈 NEW COMMAND
    
    # B. Conversation (Alert Creation)
    application.add_handler(alert_conv_handler)
    
    # C. Global Callbacks (Stop Alert Buttons)
    application.add_handler(CallbackQueryHandler(handle_alert_callback, pattern="^stop_")) # 👈 NEW HANDLER

    # D. Channel Ingestion
    channel_handler = MessageHandler(filters.ChatType.CHANNEL, handle_channel_post)
    application.add_handler(channel_handler)

    # 4. Start Background Workers
    async def post_init(app):
        # A. Ingestion Worker
        asyncio.create_task(background_worker(job_queue))
        logger.info("✅ Ingestion Worker Injected")
        
        # B. Notification Poller (The Mailman)
        asyncio.create_task(notification_poller(app.bot))
        logger.info("✅ Notification Poller Injected")

        # C. Channel Photo Refresher
        asyncio.create_task(channel_photo_refresher(app.bot))
        logger.info("✅ Channel Photo Refresher Injected")

    application.post_init = post_init

    # 5. Run
    application.run_polling()
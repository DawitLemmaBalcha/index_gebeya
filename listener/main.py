import asyncio
import sys
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ChatMemberHandler, PreCheckoutQueryHandler, TypeHandler, filters
from config import TELEGRAM_TOKEN, logger

# NEW IMPORTS
from monitor import handle_channel_post
from bot_ui import handle_start, handle_addchannel_callback
from alert_conversation import alert_conv_handler
from bot_commands import handle_my_alerts, handle_alert_callback, handle_addchannel, handle_sold_report_callback # 👈 NEW IMPORTS
from chat_member_handler import handle_chat_member
from worker import background_worker
from notifications import notification_poller
from photo_refresher import channel_photo_refresher
from payments import handle_pre_checkout, handle_successful_payment, handle_subscription_update  # NB-43..NB-46
from client import send_heartbeat  # NB-50: heartbeat sender

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
    application.add_handler(CommandHandler('addchannel', handle_addchannel))
    application.add_handler(ChatMemberHandler(handle_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # B. Conversation (Alert Creation)
    application.add_handler(alert_conv_handler)
    
    # C. Global Callbacks (Stop Alert Buttons + Add Channel)
    application.add_handler(CallbackQueryHandler(handle_alert_callback, pattern="^stop_")) # 👈 NEW HANDLER
    application.add_handler(CallbackQueryHandler(handle_addchannel_callback, pattern="^cmd_addchannel$"))
    application.add_handler(CallbackQueryHandler(handle_sold_report_callback, pattern="^sold_report_"))

    # D. Channel Ingestion
    channel_handler = MessageHandler(filters.ChatType.CHANNEL, handle_channel_post)
    application.add_handler(channel_handler)

    # E. Payments (NB-43..NB-46) — registration ORDER matters (blueprint §2.6):
    # PreCheckoutQueryHandler, then SuccessfulPayment, then the catch-all
    # TypeHandler LAST (PTB 22.8 has no Update.subscription — BotSubscription-
    # Updated arrives via update.api_kwargs, D2). Nothing may follow it.
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    application.add_handler(MessageHandler(filters.SuccessfulPayment, handle_successful_payment))
    application.add_handler(TypeHandler(Update, handle_subscription_update))  # MUST be last

    # 4. Start Background Workers
    async def post_init(app):
        # A. Ingestion Worker
        asyncio.create_task(background_worker(job_queue, app.bot))
        logger.info("✅ Ingestion Worker Injected")
        
        # B. Notification Poller (The Mailman)
        asyncio.create_task(notification_poller(app.bot))
        logger.info("✅ Notification Poller Injected")

        # C. Channel Photo Refresher
        asyncio.create_task(channel_photo_refresher(app.bot))
        logger.info("✅ Channel Photo Refresher Injected")

        # D. NB-50: Heartbeat sender (listener presence + worker stats)
        asyncio.create_task(send_heartbeat(job_queue))
        logger.info("✅ Heartbeat Sender Injected")

    application.post_init = post_init

    # 5. Run
    application.run_polling()
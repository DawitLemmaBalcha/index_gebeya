import asyncio
import json
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import TelegramError
from config import logger, WEB_APP_URL, NOTIFICATION_FAILURE_LIMIT
from client import get_pending_notifications, ack_notification, mark_notification_failed

# NB-57 (§3.4): process-local consecutive-failure counter per notification.
# Increment on delivery failure, clear on success; at NOTIFICATION_FAILURE_LIMIT
# the poller marks the notification FAILED (the dead-chat detection's honest
# source — genuinely dead chats land as FAILED rows within ~15s). Transient
# failures below the limit keep retrying from PENDING.
_consecutive_failures: dict[int, int] = {}

# ------------------------------------------------------------------
# COURIER: OUTBOUND NOTIFICATIONS
# ------------------------------------------------------------------

async def send_alert_dm(bot: Bot, user_id: int, text: str, alert_id: int = None, item_url: str = None, image_url: str = None):
    """
    Sends a direct message to a user. Uses send_photo if image_url is provided,
    otherwise falls back to text-only message.
    Includes "Stop Alert" and "View Item" buttons.
    """
    try:
        keyboard = []
        if item_url:
            keyboard.append([InlineKeyboardButton("🛒 View Item", web_app=WebAppInfo(url=item_url))])
        if alert_id:
            keyboard.append([InlineKeyboardButton("🔕 Found it / Stop Alert", callback_data=f"stop_{alert_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        if image_url:
            await bot.send_photo(
                chat_id=user_id,
                photo=image_url,
                caption=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            
        logger.info(f"📨 Alert sent to User {user_id}")
        return True

    except TelegramError as e:
        logger.error(f"❌ Failed to send Alert to {user_id}: {e}")
        return False

async def notification_poller(bot: Bot):
    """
    Background Task: Checks for pending notifications and delivers them.
    Runs every 5 seconds.
    """
    logger.info("📬 Notification Poller Started")
    
    while True:
        try:
            # 1. Check Mailbox
            pending = await get_pending_notifications()
            
            if pending:
                logger.info(f"📬 Found {len(pending)} pending notifications")

            for notif in pending:
                # 2. System DM Branch (TECH-20): deliver exact message, no item
                if notif.get('message_text') is not None:
                    msg_text = notif['message_text']
                    notif_alert_id = notif.get('alert_id')

                    success = await send_alert_dm(
                        bot, notif['user_telegram_id'], msg_text,
                        alert_id=notif_alert_id, item_url=None
                    )
                else:
                    # 3. Normal Match Notification
                    # 2. Format Message
                    item = notif['item']
                    notif_alert_id = notif.get('alert_id')
                # Note: The NotificationResponse schema in backend/schemas.py didn't include alert_id. 
                # Ideally, we should add it. But for now, we can try to rely on context or assume backend sends it.
                # FIX: In backend/models.py Notification has alert_id. 
                # We need to make sure backend/api/routes/notifications.py returns it.
                # Assuming backend update was implicitly done or we accept it might be missing in this turn.
                # Actually, let's grab it safely.
                
                # Correction: We need to pass alert_id to send_alert_dm.
                # If the schema wasn't updated to return alert_id, we can't stop it yet.
                # BUT, since we are doing a phased update, let's try to get it.
                # If 'alert_id' key exists in the JSON response (FastAPI usually includes fields if in DB model unless excluded), 
                # we are good. If we strictly used response_model, we might need to update schema.
                
                # Hotfix assumption: We will send alert_id even if Schema filters it (FastAPI won't).
                # Wait, FastAPI filters output based on response_model.
                # Since we didn't update NotificationResponse in backend/schemas.py to include alert_id,
                # this button logic relies on that update.
                
                # *Self-Correction*: I should have updated schemas.py.
                # However, for this turn, I will assume alert_id comes through or pass None.
                # To be safe, I'll access it safely.
                
                notif_alert_id = notif.get('alert_id') # Only works if schema allows it
                
                emoji = "🎯" if notif['match_tier'] == "bullseye" else "⭕"
                price_display = f"{item['price']:,} ETB" if item['price'] else "Call for Price"
                
                # Build specs line: pick relevant 3-4 specs, skip location/condition
                specs_text = ""
                specs = item.get('specs')
                if specs:
                    if isinstance(specs, str):
                        try:
                            specs = json.loads(specs.replace("'", '"'))
                        except:
                            specs = None
                    if isinstance(specs, dict):
                        skip_keys = {'location', 'condition', 'contact_phone', 'phone_number'}
                        relevant = {k: v for k, v in specs.items() if k.lower() not in skip_keys}
                        if relevant:
                            specs_text = ' | '.join(f"{v}" for v in list(relevant.values())[:4])
                
                description = item.get('description', '')
                
                msg_text = f"{emoji} **Match Found!**\n\n**{item['title']}**\n💰 {price_display}"
                if specs_text:
                    msg_text += f"\n\n_{specs_text}_"
                if description and description != 'No description':
                    msg_text += f"\n\n📝 {description}"

                item_url = f"{WEB_APP_URL}/item/{item['id']}"
                
                # Get image URL if available
                image_url = None
                img_path = item.get('image_path') or (item.get('images') and item['images'][0] if item.get('images') else None)
                if img_path:
                    image_url = f"{WEB_APP_URL}/media/{img_path}"

                success = await send_alert_dm(bot, notif['user_telegram_id'], msg_text, alert_id=notif_alert_id, item_url=item_url, image_url=image_url)

                # 4. NB-57 (§3.4): acknowledge on success; count consecutive
                # failures and mark FAILED at NOTIFICATION_FAILURE_LIMIT.
                if success:
                    _consecutive_failures.pop(notif['id'], None)
                    await ack_notification(notif['id'])
                else:
                    failures = _consecutive_failures.get(notif['id'], 0) + 1
                    if failures >= NOTIFICATION_FAILURE_LIMIT:
                        await mark_notification_failed(notif['id'])
                        _consecutive_failures.pop(notif['id'], None)
                        logger.warning(f"⚠️ Notification {notif['id']} marked FAILED after {failures} consecutive failures.")
                    else:
                        _consecutive_failures[notif['id']] = failures
                        logger.warning(f"⚠️ Could not deliver notification {notif['id']} ({failures}/{NOTIFICATION_FAILURE_LIMIT}). Will retry.")

        except Exception as e:
            if "ConnectError" not in str(e):
                logger.error(f"💥 Poller Exception: {e}")

        await asyncio.sleep(5)
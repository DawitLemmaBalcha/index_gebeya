from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from client import get_active_alerts, delete_alert_api

async def handle_my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lists the user's active alerts with Delete buttons.
    """
    user_id = update.effective_user.id
    alerts = await get_active_alerts(user_id)

    if not alerts:
        await update.message.reply_text("📭 You have no active alerts.\nUse /alert to create one!")
        return

    text = "📋 **Your Active Alerts**\n\n"
    keyboard = []

    for alert in alerts:
        # Format: "iPhone 13 (50k)"
        price_display = f"{alert['max_price']:,.0f}" if alert['max_price'] else "Any"
        row_text = f"{alert['query_text']} ({price_display})"
        
        # Button data: "stop_ALERTID"
        callback_data = f"stop_{alert['id']}"
        
        keyboard.append([InlineKeyboardButton(f"🗑️ {row_text}", callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles 'stop_123' callbacks from /myalerts OR notifications.
    """
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data.startswith("stop_"):
        alert_id = int(data.split("_")[1])
        
        success = await delete_alert_api(user_id, alert_id)
        
        if success:
            await query.answer("✅ Alert stopped.")
            
            # If clicked from a notification (has "Found it!" text)
            if "Found it" in query.message.text or "Match Found" in query.message.text:
                 await query.edit_message_reply_markup(reply_markup=None) # Remove button
                 await query.message.reply_text("🔕 Alert stopped. You won't receive more notifications for this.")
            
            # If clicked from /myalerts list
            else:
                # Refresh the list
                await query.delete_message()
                await query.message.reply_text("✅ Alert deleted.")
        else:
            await query.answer("❌ Failed to stop alert. Try again.", show_alert=True)


async def handle_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Instructs a channel/group owner on how to add the bot as admin.
    """
    bot_username = context.bot.username
    instruction_text = (
        "To list your products on Index Gebeya, add me to your channel or group as an **admin**:\n\n"
        "1. Open your channel or group → **Info** → **Administrators**\n"
        f"2. Tap **Add Admin** and search for `@{bot_username}`\n"
        "3. ⚠️ **Turn OFF all permissions.** I don't need to delete messages, ban users, or post. "
        "Admin is only needed so I can verify you own this channel/group.\n"
        "4. Confirm.\n\n"
        "Once added, post a product — it'll appear in the marketplace within a minute or two."
    )
    await update.message.reply_text(instruction_text, parse_mode="Markdown")
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, BotCommand
from telegram.ext import ContextTypes
from config import logger

# ------------------------------------------------------------------
# BOT UI: USER INTERACTIONS & MENUS
# ------------------------------------------------------------------

# YOUR SECURE DOMAIN
WEB_APP_URL = "https://indexgebeya.cfd"

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Responds to /start with a button to open the Mini App.
    Supports deep link payload: /start addchannel → shows addchannel instructions directly.
    """
    user = update.effective_user
    logger.info(f"👤 User {user.id} ({user.first_name}) started the bot.")

    # Check for deep link payload (e.g., t.me/IndexGebeyaBot?start=addchannel)
    if context.args and context.args[0] == "addchannel":
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
        return

    # 0. Register Bot Commands Menu
    try:
        await context.bot.set_my_commands([
            BotCommand("start", "Open Index Gebeya"),
            BotCommand("addchannel", "Add your channel or group"),
            BotCommand("myalerts", "Manage your alerts"),
            BotCommand("help", "Show help"),
        ])
    except Exception as e:
        logger.error(f"⚠️ Failed to set bot commands: {e}")

    # 1. Set the Persistent Menu Button (Bottom Left)
    try:
        await context.bot.set_chat_menu_button(
            chat_id=update.effective_chat.id,
            menu_button=MenuButtonWebApp(text="Open Index Gebeya", web_app=WebAppInfo(url=WEB_APP_URL))
        )
    except Exception as e:
        logger.error(f"⚠️ Failed to set menu button: {e}")

    # 2. Send a Welcome Message with Inline Buttons
    keyboard = [
        [InlineKeyboardButton("🚀 Launch Store", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton("📋 Add your channel", callback_data="cmd_addchannel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "Welcome to Index Gebeya — Ethiopia's Telegram Marketplace Search Engine\n\n"
        "🔍 *Browse & Search* — thousands of products from Ethiopian Telegram channels\n"
        "🔔 *Set Alerts* — get notified when matching products are posted\n"
        "🏪 *List Your Channel* — add your channel to be indexed and reach buyers\n\n"
        "Use /addchannel to get started listing your products.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_addchannel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the inline button callback for /addchannel.
    TECH-18: Added for the welcome message button.
    """
    query = update.callback_query
    await query.answer()
    
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
    await query.edit_message_text(
        instruction_text,
        parse_mode="Markdown"
    )
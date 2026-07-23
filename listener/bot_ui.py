from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp
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
    """
    user = update.effective_user
    logger.info(f"👤 User {user.id} ({user.first_name}) started the bot.")

    # 1. Set the Persistent Menu Button (Bottom Left)
    try:
        await context.bot.set_chat_menu_button(
            chat_id=update.effective_chat.id,
            menu_button=MenuButtonWebApp(text="Open Index Gebeya", web_app=WebAppInfo(url=WEB_APP_URL))
        )
    except Exception as e:
        logger.error(f"⚠️ Failed to set menu button: {e}")

    # 2. Send a Welcome Message with an Inline Button
    keyboard = [
        [InlineKeyboardButton("🚀 Launch Store", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "Welcome to **Index Gebeya**. Browse items instantly without leaving Telegram.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
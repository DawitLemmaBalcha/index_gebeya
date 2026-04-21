from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from client import create_alert_api

# STATES
CHOOSING_PRODUCT = 1
CHOOSING_FILTERS = 2 
CHOOSING_PRICE = 3

async def start_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: User types /alert"""
    context.user_data["alert_query"] = None
    context.user_data["preferences"] = {"strict_brand": False, "strict_model": False}
    
    await update.message.reply_text(
        "🔔 **Create a New Alert**\n\n"
        "What are you looking for? (e.g., 'iPhone 13 Pro', 'Toyota Vitz')",
        parse_mode="Markdown"
    )
    return CHOOSING_PRODUCT

async def receive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User types the product name. Next: Ask for Filters"""
    user_query = update.message.text
    context.user_data["alert_query"] = user_query

    await _show_filter_menu(update, context)
    return CHOOSING_FILTERS

async def _show_filter_menu(update_obj, context):
    """Helper to render the filter toggle menu"""
    prefs = context.user_data.get("preferences", {})
    
    brand_icon = "✅" if prefs.get("strict_brand") else "⬜"
    model_icon = "✅" if prefs.get("strict_model") else "⬜"
    
    keyboard = [
        [
            InlineKeyboardButton(f"{brand_icon} Strict Brand", callback_data="toggle_brand"),
            InlineKeyboardButton(f"{model_icon} Strict Model", callback_data="toggle_model")
        ],
        [InlineKeyboardButton("➡️ Next: Set Budget", callback_data="next_step")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"Looking for: **{context.user_data['alert_query']}**\n\n"
        "**Smart Filters:**\n"
        "• **Strict Brand:** Matches 'iPhone' but ignores 'Samsung'.\n"
        "• **Strict Model:** Matches 'iPhone 13' exactly, ignores 'iPhone 12'."
    )
    
    if hasattr(update_obj, "message"):
        await update_obj.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_obj.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def toggle_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles toggle clicks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    prefs = context.user_data["preferences"]
    
    if data == "toggle_brand":
        prefs["strict_brand"] = not prefs["strict_brand"]
    elif data == "toggle_model":
        prefs["strict_model"] = not prefs["strict_model"]
        
    await _show_filter_menu(query, context)
    return CHOOSING_FILTERS

async def finish_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicks Next. Ask for Price."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💰 Any Price", callback_data="any_price")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Filters Set.\n\n"
        "**What is your max budget in ETB?**\n"
        "Type a number (e.g. '50000') or tap 'Any Price'.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return CHOOSING_PRICE

async def receive_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User types a specific price"""
    text = update.message.text.strip().replace(',', '')
    
    if not text.isdigit():
        await update.message.reply_text("⚠️ Please enter a valid number (e.g. 15000).")
        return CHOOSING_PRICE

    max_price = float(text)
    return await _finalize_alert(update, context, max_price)

async def receive_price_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicks 'Any Price'"""
    query = update.callback_query
    await query.answer()
    return await _finalize_alert(query, context, None) 

async def _finalize_alert(update_obj, context, max_price):
    """Saves the alert to the backend"""
    query_text = context.user_data["alert_query"]
    
    # FIX: Robust user ID extraction
    if hasattr(update_obj, "effective_user") and update_obj.effective_user:
        user_id = update_obj.effective_user.id
    elif hasattr(update_obj, "from_user") and update_obj.from_user:
        user_id = update_obj.from_user.id
    else:
        # Fallback if both fail (unlikely)
        user_id = update_obj.message.chat.id

    # Determine message target
    message_target = update_obj.message if hasattr(update_obj, "message") else update_obj

    status_msg = await message_target.reply_text("⏳ Saving alert...")

    from client import create_alert_api
    
    success = await create_alert_api(
        user_id, 
        query_text, 
        max_price, 
        preferences=context.user_data["preferences"]
    )

    if success:
        price_str = f"{max_price:,.0f} ETB" if max_price else "Any Price"
        prefs = context.user_data["preferences"]
        filters_str = ", ".join([k.replace("strict_", "").title() for k,v in prefs.items() if v]) or "None"

        await status_msg.edit_text(
            f"✅ **Alert Saved!**\n\n"
            f"🎯 Product: {query_text}\n"
            f"⚡ Filters: {filters_str}\n"
            f"💸 Budget: {price_str}\n\n"
            "I'll notify you when I find a match!",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Failed to save alert. Please try again later.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the conversation"""
    await update.message.reply_text("🚫 Alert creation cancelled.")
    return ConversationHandler.END

# EXPORT HANDLER
alert_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("alert", start_alert)],
    states={
        CHOOSING_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product)],
        CHOOSING_FILTERS: [
            CallbackQueryHandler(toggle_filter, pattern="^toggle_"),
            CallbackQueryHandler(finish_filters, pattern="^next_step$")
        ],
        CHOOSING_PRICE: [
            MessageHandler(filters.Regex(r'^\d+'), receive_price_text),
            CallbackQueryHandler(receive_price_button, pattern="^any_price$")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)
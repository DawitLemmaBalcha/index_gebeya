from telegram import ChatMemberUpdated, Update
from telegram.ext import ContextTypes
from telegram import error as telegram_error
from config import logger
from client import upsert_channel_api


async def handle_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles my_chat_member status changes for bot onboarding into channels/groups.

    Only fire when the bot's own membership status changes in a chat.
    Forwards DMs to the inviter on every meaningful state transition.
    """

    # --- Extract data from the update ---
    chat = update.my_chat_member.chat
    new_status = update.my_chat_member.new_chat_member.status
    old_status = update.my_chat_member.old_chat_member.status
    inviter = update.my_chat_member.from_user

    # --- Guard: inviter is None (bot joined via public invite link) ---
    if inviter is None:
        logger.warning("No inviter found — bot likely joined via public link. Cannot DM anyone.")
        return

    # --- Guard: ignore private chats ---
    if chat.type == "private":
        logger.info(f"my_chat_member fired for private chat {chat.id} — ignoring.")
        return

    # --- Guard: ignore non-target statuses ---
    if new_status == "restricted":
        logger.info(f"my_chat_member: restricted status — ignoring for chat {chat.id}")
        return

    # --- Extract chat identifiers ---
    chat_username = chat.username
    chat_display = f"@{chat_username}" if chat_username else chat.title or "unknown"
    inviter_id = inviter.id

    async def _dm(text: str) -> None:
        """Send a DM to the inviter, swallowing TelegramError so one failure doesn't crash the handler."""
        try:
            await context.bot.send_message(chat_id=inviter_id, text=text)
        except telegram_error.TelegramError as e:
            logger.warning(f"Failed to DM inviter {inviter_id} for {chat_display}: {e}")

    # =========================================================================
    # State 1 — Added as Administrator WITH public username (SUCCESS)
    # =========================================================================
    if new_status == "administrator" and chat_username is not None:
        # Register/update the channel
        await upsert_channel_api(
            username=chat_username,
            title=chat.title or chat_username,
            registered_by=inviter_id,
            telegram_id=chat.id,
        )
        await _dm(
            f"✅ {chat_display} is now live on Index Gebeya. "
            "Your listings will appear in the marketplace within a minute or two of posting."
        )
        logger.info(f"✅ Channel/group onboarded: {chat_display} (inviter={inviter_id})")
        return

    # =========================================================================
    # State 2 — Added as Administrator WITHOUT public username (REJECTED)
    # =========================================================================
    if new_status == "administrator" and chat_username is None:
        await _dm(
            "This channel/group is private. We can only index public channels and groups "
            "that have a @username. Please add me to a public channel/group instead."
        )
        logger.info(f"❌ Private channel rejected: chat_id={chat.id} (inviter={inviter_id})")
        return

    # =========================================================================
    # State 4 — Demoted (admin → member)
    # =========================================================================
    if new_status == "member" and old_status == "administrator":
        await _dm(
            f"I've lost admin status on {chat_display}. "
            "I'll stop indexing your listings. Add me back as admin to resume."
        )
        logger.info(f"⬇️ Demoted to member on {chat_display} (inviter={inviter_id})")
        return

    # =========================================================================
    # State 3 — Added as Regular Member (NOT admin)
    # =========================================================================
    if new_status == "member":
        await _dm(
            "To verify you own this channel/group, add me as admin. "
            "No permissions needed — you can turn them all off. "
            "Just remove me and re-add me as admin."
        )
        logger.info(f"👤 Added as regular member on {chat_display} (inviter={inviter_id})")
        return

    # =========================================================================
    # State 5 — Removed (kicked or left)
    # =========================================================================
    if new_status in ("kicked", "left"):
        await _dm(
            f"I've been removed from {chat_display}. "
            "Your listings are no longer being updated. Add me back anytime to resume."
        )
        logger.info(f"🚪 Removed from {chat_display} (inviter={inviter_id})")
        return

    # Fallback for any other status
    logger.info(f"Unhandled my_chat_member transition: {old_status} → {new_status} on {chat_display}")

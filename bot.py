import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
import config
import parser as tx_parser
import db
import threading
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_YOUR"):
    logger.warning("توکن بات در config.py تنظیم نشده است. لطفا BOT_TOKEN را قرار دهید.")


def format_number(n: int) -> str:
    return f"{n:,}"


async def reply_with_balance(bot, chat_id: int, reply_to_message_id: int, asset: str):
    bal = db.get_balance(chat_id, asset)
    text = f"موجودی {asset} : {format_number(bal)}"
    await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = "✅ ربات ثبت ورود/خروج فعال شد. برای مشاهده‌ی جدول کلی موجودی‌ها دکمه را بزنید."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 موجودی لحظه‌ای", callback_data="show_balances")]])
    if update.message:
        await update.message.reply_text(txt, reply_markup=kb)
    else:
        await update.effective_chat.send_message(txt, reply_markup=kb)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_balances_callback(update.effective_chat.id, context.bot, update.message)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from db import _write_db, _default_db
    chat_id = update.effective_chat.id
    _write_db(chat_id, _default_db())
    await update.message.reply_text("✅ همه تراکنش‌های این گروه پاک شدند. موجودی صفر شد.")


async def send_balances_callback(chat_id, bot, reply_message=None):
    totals = db.get_report_table(chat_id)
    if not totals:
        text = "هنوز تراکنشی ثبت نشده."
        if reply_message:
            await reply_message.reply_text(text)
        else:
            await bot.send_message(chat_id=chat_id, text=text)
        return

    lines = []
    for asset, vals in totals.items():
        line_header = f"*{asset}*"
        line_data = f"ورود: {format_number(vals.get('in',0))}    خروج: {format_number(vals.get('out',0))}"
        lines.append(line_header)
        lines.append(line_data)
    text = "\n".join(lines)

    if reply_message:
        await reply_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "show_balances":
        totals = db.get_report_table(update.effective_chat.id)
        if not totals:
            await query.answer()
            await query.message.reply_text("هنوز تراکنشی ثبت نشده.")
            return
        lines = []
        for asset, vals in totals.items():
            line_header = f"*{asset}*"
            line_data = f"ورود: {format_number(vals.get('in',0))}    خروج: {format_number(vals.get('out',0))}"
            lines.append(line_header)
            lines.append(line_data)
        text = "\n".join(lines)
        await query.answer()
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await query.answer()


async def handle_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    text = update.message.text
    parsed = tx_parser.parse_message(text)
    if not parsed:
        return
    added = db.add_transaction(chat_id, msg_id, parsed)
    await reply_with_balance(context.bot, chat_id, msg_id, parsed["asset"])
    logger.info("Added tx: chat=%s msg=%s parsed=%s added=%s", chat_id, msg_id, parsed, added)


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.edited_message if update.edited_message else update.message
    if msg is None or msg.text is None:
        return
    chat_id = update.effective_chat.id
    msg_id = msg.message_id
    text = msg.text
    parsed = tx_parser.parse_message(text)
    if not parsed:
        return
    updated = db.update_transaction(chat_id, msg_id, parsed)
    await reply_with_balance(context.bot, chat_id, msg_id, parsed["asset"])
    logger.info("Updated tx: chat=%s msg=%s parsed=%s updated=%s", chat_id, msg_id, parsed, updated)


def run_telethon_listener():
    if not config.TELETHON_ENABLE:
        return
    try:
        from telethon import TelegramClient, events
    except Exception as e:
        logger.error("Telethon نصب نشده یا قابل ایمپورت نیست: %s", e)
        return

    api_id = config.TELETHON_API_ID
    api_hash = config.TELETHON_API_HASH
    session = config.TELETHON_SESSION_NAME

    if not api_id or not api_hash:
        logger.error("برای فعال‌سازی Telethon باید TELETHON_API_ID و TELETHON_API_HASH را پر کنید.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = TelegramClient(session, api_id, api_hash, loop=loop)

    @client.on(events.MessageDeleted)
    async def handler(event):
        for chat_id, ids in event.deleted_ids.items():
            for mid in ids:
                removed = db.remove_transaction(chat_id, mid)
                logger.info("Telethon: removed tx for chat=%s msg=%s removed=%s", chat_id, mid, removed)

    logger.info("Starting Telethon listener (برای دریافت حذف پیام‌ها)...")
    client.start()
    client.run_until_disconnected()


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_new_message))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_edited_message))

    if config.TELETHON_ENABLE:
        t = threading.Thread(target=run_telethon_listener, daemon=True)
        t.start()

    logger.info("Bot started. Polling...")
    application.run_polling()


if __name__ == "__main__":
    main()

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
    # از فرمت با کاما استفاده می‌کنیم
    return f"{int(n):,}"


async def cmd_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام داشبورد پایه‌ای با دکمه نمایش موجودی."""
    txt = "📊 مدیریت صندوق:\nبرای مشاهده موجودی روی دکمه زیر کلیک کنید."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 موجودی لحظه‌ای", callback_data="show_balances")]])
    sent = await update.message.reply_text(txt, reply_markup=kb)
    # ذخیره id پیام داشبورد برای ادیت‌های بعدی
    db.set_dashboard_message_id(update.effective_chat.id, sent.message_id)


def _build_balances_text_and_kb(chat_id: int):
    totals = db.get_report_table(chat_id)
    confirmed = db.get_confirmed_balances(chat_id)
    balances = db.get_all_balances(chat_id)

    if not totals and not confirmed:
        text = "هنوز تراکنشی ثبت نشده."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 نمایش مجدد موجودی", callback_data="show_balances")]])
        return text, kb

    lines = []
    assets = sorted(set(list(balances.keys()) + list(confirmed.keys()) + list(totals.keys())))
    for asset in assets:
        prev = confirmed.get(asset, 0)
        t = totals.get(asset, {"in": 0, "out": 0})
        cur = balances.get(asset, 0)
        lines.append(f"*{asset}*")
        lines.append(f"مانده تأییدشدهٔ قبل: {format_number(prev)}")
        lines.append(f"ورود: {format_number(t.get('in',0))}    خروج: {format_number(t.get('out',0))}")
        lines.append(f"موجودی فعلی: {format_number(cur)}")
        lines.append("")  # فاصله بین دارایی‌ها
    text = "\n".join(lines).strip()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تایید موجودی روز", callback_data="confirm_day")]])
    return text, kb


async def send_balances_callback(query, chat_id: int):
    """ویرایش پیام (edit) برای نمایش موجودی و دکمه تایید."""
    text, kb = _build_balances_text_and_kb(chat_id)
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception as e:
        logger.warning("send_balances_callback edit failed: %s", e)
        # fallback: try to answer
        try:
            await query.answer()
        except Exception:
            pass


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # acknowledge quickly
    chat_id = update.effective_chat.id
    data = query.data

    if data == "show_balances":
        await send_balances_callback(query, chat_id)
    elif data == "confirm_day":
        # انجام تایید روز
        db.confirm_day(chat_id)
        confirmed = db.get_confirmed_balances(chat_id)
        lines = ["✅ موجودی روز تایید شد.\nمانده صندوق:"]
        for asset, val in confirmed.items():
            lines.append(f"*{asset}*: {format_number(val)}")
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 مشاهده مجدد موجودی", callback_data="show_balances")]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception as e:
            logger.warning("confirm_day edit failed: %s", e)
    else:
        # هیچکس
        pass


async def _update_dashboard_message(chat_id: int, bot):
    """اگر پیام داشبورد ثبت شده باشد، آن را ادیت کن تا آخرین وضعیت نشان داده شود."""
    msg_id = db.get_dashboard_message_id(chat_id)
    if not msg_id:
        return
    text, kb = _build_balances_text_and_kb(chat_id)
    try:
        await bot.edit_message_text(text, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception as e:
        # ممکن است پیام حذف شده باشد یا بات دسترسی نداشته باشد
        logger.debug("Could not edit dashboard message (chat=%s msg=%s): %s", chat_id, msg_id, e)


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
    logger.info("Added tx: chat=%s msg=%s parsed=%s added=%s", chat_id, msg_id, parsed, added)
    # ادیت خودکار پیام داشبورد (اگر وجود داشته باشد)
    await _update_dashboard_message(chat_id, context.bot)


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
    logger.info("Updated tx: chat=%s msg=%s parsed=%s updated=%s", chat_id, msg_id, parsed, updated)
    await _update_dashboard_message(chat_id, context.bot)


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
                # سعی کن داشبورد را بروزرسانی کنی (داخل loop Telethon هست، دسترسی به PTB bot ممکن است نباشد)
                # اگر خواستی می‌تونی یک HTTP endpoint اضافه کنی یا از یک صف استفاده کنی.
    logger.info("Starting Telethon listener (برای دریافت حذف پیام‌ها)...")
    client.start()
    client.run_until_disconnected()


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("bal", cmd_bal))
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

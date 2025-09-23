import logging
import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram.constants import ParseMode

import config
import parser as tx_parser
import db
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = config.BOT_TOKEN
if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_YOUR"):
    logger.warning("توکن بات در config.py تنظیم نشده است. لطفا BOT_TOKEN را قرار دهید.")


def format_number(n: int) -> str:
    # جداکننده هزار با کاما (پیکربندی در config)
    return f"{n:,}"


def reply_with_balance(bot, chat_id: int, reply_to_message_id: int, asset: str):
    bal = db.get_balance(asset)
    text = f"موجودی {asset} : {format_number(bal)}"
    bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id)


def cmd_start(update, context):
    txt = "ربات ثبت ورود/خروج فعال شد. برای مشاهده‌ی جدول کلی موجودی‌ها دکمه را بزنید."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("موجودی لحظه‌ای", callback_data="show_balances")]])
    if update.message:
        update.message.reply_text(txt, reply_markup=kb)
    else:
        update.effective_chat.send_message(txt, reply_markup=kb)


def cmd_balance(update, context):
    # این دستور جدول کلی را می‌فرستد
    send_balances_callback(update.effective_chat.id, context.bot, update.message)


def send_balances_callback(chat_id, bot, reply_message=None):
    totals = db.get_report_table()
    if not totals:
        text = "هنوز تراکنشی ثبت نشده."
        if reply_message:
            reply_message.reply_text(text)
        else:
            bot.send_message(chat_id=chat_id, text=text)
        return
    # تولید جدول: برای هر دارایی دو ردیف: (ردیف اول: اسم دارایی) / (ردیف دوم: ورود | خروج)
    lines = []
    for asset, vals in totals.items():
        line_header = f"*{asset}*"
        line_data = f"ورود: {format_number(vals.get('in',0))}    خروج: {format_number(vals.get('out',0))}"
        lines.append(line_header)
        lines.append(line_data)
    text = "\n".join(lines)
    if reply_message:
        reply_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)


def callback_query_handler(update, context):
    query = update.callback_query
    data = query.data
    if data == "show_balances":
        totals = db.get_report_table()
        if not totals:
            query.answer()
            query.message.reply_text("هنوز تراکنشی ثبت نشده.")
            return
        lines = []
        for asset, vals in totals.items():
            line_header = f"*{asset}*"
            line_data = f"ورود: {format_number(vals.get('in',0))}    خروج: {format_number(vals.get('out',0))}"
            lines.append(line_header)
            lines.append(line_data)
        text = "\n".join(lines)
        query.answer()
        query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        query.answer()


def handle_new_message(update, context):
    # پیام جدید در گروه دریافت شد
    if update.message is None or update.message.text is None:
        return
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    text = update.message.text
    parsed = tx_parser.parse_message(text)
    if not parsed:
        return
    added = db.add_transaction(chat_id, msg_id, parsed)
    # حتی اگر قبلاً وجود داشت؛ برای اطمینان دوباره reply بزن
    reply_with_balance(context.bot, chat_id, msg_id, parsed["asset"])
    logger.info("Added tx: chat=%s msg=%s parsed=%s added=%s", chat_id, msg_id, parsed, added)


def handle_edited_message(update, context):
    # پیام ویرایش شد؛ update.edited_message یا update.message ممکن است داشته باشیم بسته به نسخه
    # در اینجا هر دو حالت را بررسی می‌کنیم.
    msg = update.edited_message if hasattr(update, "edited_message") and update.edited_message else update.message
    if msg is None or msg.text is None:
        return
    chat_id = update.effective_chat.id
    msg_id = msg.message_id
    text = msg.text
    parsed = tx_parser.parse_message(text)
    if not parsed:
        # اگر پارسر نتواند چیزی بخواند، احتمالاً می‌خواهیم اگر قبل رکوردی وجود داشت آن را حذف کنیم
        # اما برای احتیاط این کار را انجام نمی‌کنیم؛ بهتر است رفتار حذف را صریح نگه داریم.
        return
    updated = db.update_transaction(chat_id, msg_id, parsed)
    reply_with_balance(context.bot, chat_id, msg_id, parsed["asset"])
    logger.info("Updated tx: chat=%s msg=%s parsed=%s updated=%s", chat_id, msg_id, parsed, updated)


# --- Telethon (اختیاری) برای دریافت حذف پیام ---
# توضیح: Bot API معمولاً حذف پیام‌ها را به بات اطلاع نمی‌دهد. اگر نیاز دارید پیام‌های حذف شده
# هم در سابقه حذف شوند، می‌توانید یک userbot (Telethon) همزمان اجرا کنید که حذف پیام را می‌شنود
# و سپس db.remove_transaction را صدا بزند.
#
# برای فعال‌سازی:
# - TELETHON_ENABLE = True در config.py
# - TELETHON_API_ID و TELETHON_API_HASH را پر کنید
# - هنگام اجرای برای اولین بار، یک session ساخته خواهد شد (احراز هویت توسط شماره‌ی موبایل)
#
# توجه: استفاده از userbot یعنی شما از حساب شخصی استفاده می‌کنید و این راه‌حل نیازمند
# آگاهی از مسائل امنیتی/قوانین تلگرام است.
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

    client = TelegramClient(session, api_id, api_hash)

    @client.on(events.MessageDeleted)
    async def handler(event):
        # event.deleted_ids: dict از chat_id -> [message_ids]
        # حذف هر پیام را در دیتابیس پاک کن
        for chat_id, ids in event.deleted_ids.items():
            for mid in ids:
                removed = db.remove_transaction(chat_id, mid)
                logger.info("Telethon: removed tx for chat=%s msg=%s removed=%s", chat_id, mid, removed)
                # در صورت نیاز می‌توان اینجا پیام اطلاع‌رسانی هم فرستاد (اختیاری)

    logger.info("Starting Telethon listener (برای دریافت حذف پیام‌ها)...")
    client.start()
    client.run_until_disconnected()


def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("balance", cmd_balance))
    dp.add_handler(CallbackQueryHandler(callback_query_handler))

    # پیام جدید
    dp.add_handler(MessageHandler(Filters.text & Filters.group, handle_new_message))
    # پیام ویرایش شده - در برخی نسخه‌ها باید edited_updates=True ست شود؛ این کتابخانه معمولاً
    # ویرایش‌ها را با همین Handler هم می‌فرستد. اگر دریافت نمی‌شود، در مستندات نسخه‌ی مورد استفاده
    # پارامتر مربوطه را فعال کنید.
    dp.add_handler(MessageHandler(Filters.text & Filters.group, handle_edited_message))

    # Telethon را در یک ترد جدا اجرا کن (اختیاری)
    if config.TELETHON_ENABLE:
        t = threading.Thread(target=run_telethon_listener, daemon=True)
        t.start()

    updater.start_polling()
    logger.info("Bot started. Polling...")
    updater.idle()


if __name__ == "__main__":
    main()

BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

# مسیر دیتابیس (JSON). فایل و فولدر در صورت نبود خودکار ساخته می‌شود.
DB_PATH = "data/db.json"

# دارایی پیش‌فرض وقتی بین ضریب و حرف و/خ خالی باشد
DEFAULT_ASSET = "دلار"

# اگر اسم دارایی شامل یکی از این‌ها بود، "تا" = 1 (سکه‌های طلا) نه 1000
COIN_ASSETS = ["امامی", "نیم", "ربع", "تمام"]

# اگر بخواهید حذف پیام (delete) هم توسط userbot دریافت شود:
TELETHON_ENABLE = False
TELETHON_API_ID = None        # e.g. 123456
TELETHON_API_HASH = None     # e.g. "abcdef123456..."
TELETHON_SESSION_NAME = "user_session"

# لیست آی‌دی ادمین (اختیاری) برای گزارش‌ها یا لاگ‌های بیشتر
ADMIN_IDS = []

# فرمت نمایش اعدادی که در پیام‌ها نشان داده می‌شود
# (از جداکننده‌ی هزار استفاده می‌کنیم؛ در اینجا از کاما استفاده شده)
THOUSAND_SEPARATOR = ","

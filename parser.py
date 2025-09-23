import re
from typing import Optional, Dict
import config

# نگاشت ارقام فارسی -> انگلیسی
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

# نگاشت کلمات عددی ساده
_UNITS = {
    "صفر": 0, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "شیش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15,
    "شانزده": 16, "هفده": 17, "هجده": 18, "نوزده": 19
}
_TENS = {
    "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50,
    "شصت": 60, "هفتاد": 70, "هشتاد": 80, "نود": 90
}
_HUNDREDS = {
    "صد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
    "پانصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800, "نهصد": 900
}

def _persian_to_english_digits(s: str) -> str:
    return s.translate(PERSIAN_DIGITS)

def _words_to_number(text: str) -> Optional[int]:
    """
    تلاش می‌کند مجموعه‌ای از کلمات عددی فارسی (مثلاً "بیست و هفت") را به عدد تبدیل کند.
    اگر تبدیل ممکن نباشد، None برمی‌گرداند.
    الگوریتم ساده است و برای اعداد معمول روزمره کافی است.
    """
    text = text.strip()
    if not text:
        return None
    # جداسازی با "و" یا space
    parts = re.split(r'[\s،]+', text)
    total = 0
    found = False
    for p in parts:
        if not p:
            continue
        if p in _HUNDREDS:
            total += _HUNDREDS[p]
            found = True
            continue
        if p in _TENS:
            total += _TENS[p]
            found = True
            continue
        if p in _UNITS:
            total += _UNITS[p]
            found = True
            continue
        # گاهی "بیست و هفت" بصورت "بیست و هفت" جدا شده با "و"
        # اگر نتوان شناختیم، رد می‌کنیم
    return total if found else None

def _extract_number_and_multiplier(text_before_dir: str):
    """
    از متن پیش از حرف (و/خ) عدد و ضریب را استخراج می‌کند.
    برمی‌گرداند: (number:int, multiplier_word: str | None, number_span: (start,end), mult_span: (start,end))
    """
    s = _persian_to_english_digits(text_before_dir)
    # ابتدا به دنبال اعداد انگلیسی/فارسی (اکنون به انگلیسی تبدیل شده) بگرد
    m = re.search(r'\d+', s)
    if m:
        number = int(m.group())
        num_span = (m.start(), m.end())
        # بعد از عدد به دنبال "تا" یا "عدد" باش
        after = s[m.end():]
        mm = re.search(r'\b(تا|عدد)\b', after)
        if mm:
            # تبدیل موقعیت نسبی به موقعیت کلی در s
            mult_start = m.end() + mm.start()
            mult_end = m.end() + mm.end()
            mult_word = after[mm.start():mm.end()]
            return number, mult_word, num_span, (mult_start, mult_end)
        else:
            return number, None, num_span, None
    # اگر عددی پیدا نشد، ممکن است عدد با کلمه فارسی نوشته شده باشد:
    # جستجو برای کلمات عددی (مثلاً "پنج" یا "بیست و هفت")
    # به‌طور ساده کل رشته را امتحان می‌کنیم
    # پاکسازی اضافی
    cleaned = re.sub(r'[^\u0600-\u06FF\s]', ' ', text_before_dir)  # فقط حروف فارسی و فاصله نگه‌دار
    cleaned = cleaned.strip()
    if not cleaned:
        return None, None, None, None
    # اگر کلمه 'عدد' آمده و هیچ عددی نیامده، عدد را 1 درنظر می‌گیریم
    if re.search(r'\bعدد\b', cleaned):
        # عدد به صورت ضمنی = 1
        number = 1
        mult_word = 'عدد'
        # تعیین بازه‌های فرضی
        return number, mult_word, (0,1), (1,1)
    # تلاش تبدیل کل عبارت به عدد
    num = _words_to_number(cleaned)
    if num is not None:
        # آیا عبارت شامل کلمه 'تا' یا 'عدد' است؟
        mm = re.search(r'\b(تا|عدد)\b', cleaned)
        if mm:
            return num, mm.group(1), (0,len(cleaned)), (mm.start(), mm.end())
        else:
            return num, None, (0,len(cleaned)), None
    return None, None, None, None

def parse_message(text: str) -> Optional[Dict]:
    """
    اگر متن الگوی مورد انتظار را داشت، دیکشنری زیر را برمی‌گرداند:
    {
      "asset": "دلار",
      "amount": 27000,
      "direction": "و" or "خ",
      "counterparty": "نام طرف حساب",
      "raw": original text
    }
    در غیر این صورت None می‌دهد.
    """
    if not text or not isinstance(text, str):
        return None
    orig = text.strip()
    # نرمال‌سازی اولیه
    s = orig.replace('\n', ' ').strip()
    s = re.sub(r'\s+', ' ', s)  # چند فاصله => یک فاصله
    s = s.strip()
    # پیدا کردن حرف ورود/خروج: یک حرف 'و' یا 'خ' که به‌صورت مستقل (محاط در فاصله) بیاید
    # (ما فرض می‌کنیم کاربر از یک حرف جدا شده استفاده می‌کند)
    dir_match = re.search(r'(?<=\s|^)([وخ])(?=\s)', s)
    if not dir_match:
        # اگر حرف در انتها باشد (بدون فاصله بعدی) هم بگرد
        dir_match = re.search(r'(?<=\s|^)([وخ])(?=$|[:\-])', s)
    if not dir_match:
        return None
    direction = dir_match.group(1)
    # طرف حساب: هر چیزی بعد از آن (تا پایان یا تا علامت :)
    counterparty = s[dir_match.end():].strip()
    # اگر شروع با ":" یا "-" بود، آن را پاک کن
    counterparty = counterparty.lstrip(':').strip()
    # متن پیش از حرف جهت
    before = s[:dir_match.start()].strip()
    # استخراج عدد و ضریب از before
    number, mult_word, num_span, mult_span = _extract_number_and_multiplier(before)
    if number is None:
        return None
    # تعیین اسم دارایی: متن بین ضریب(یا عدد) و حرف جهت
    asset = None
    if mult_span:
        # موقعیت mult_span بازه‌ای نسبی نسبت به before؛ آن را استفاده می‌کنیم
        # اما برای سادگی، به دنبال کلمه 'تا' یا 'عدد' در before می‌گردیم و بخش بعدی را دارایی می‌گیریم
        mm = re.search(r'\b(تا|عدد)\b', before)
        if mm:
            after_mult = before[mm.end():].strip()
            asset = after_mult.split()[0] if after_mult else ""
            # اگر asset بیش از یک کلمه است (مثلاً "دلار استرالیا")، بهتر است تا قبل از حرف جهت همه را بگیریم.
            # اما چون قبل از حرف جهت، تمام before تا dir_match.start است، باید asset تمام متن بعد از mult تا dir باشد:
            asset = after_mult if after_mult else ""
    else:
        # اگر ضریبی نداشتیم، ممکن است عدد مستقیماً قبل از اسم دارایی باشد:
        # متن after_num = قبل از حرف جهت بعد از عدد
        if num_span:
            # num_span ممکن است بر اساس نسخه تبدیل‌شده بوده باشد؛ باز هم ساده کنیم:
            # تلاش برای یافتن اولین عدد (digits) و گرفتن مابقی عبارت تا قبل از حرف جهت
            m = re.search(r'\d+', _persian_to_english_digits(before))
            if m:
                # find index of this number in original 'before' (نه تبدیل‌شده)
                # برای سادگی: جداکننده را بر اساس رخداد اول عدد جدا می‌کنیم
                parts = re.split(r'\d+', before, maxsplit=1)
                if len(parts) >= 2:
                    after_num = parts[1].strip()
                    asset = after_num if after_num else ""
            else:
                # تلاش برای کلمات عددی: جدا کردن based on known number words
                # سعی می‌کنیم هر کلمه‌ی عددی را از ابتدای رشته برداریم
                cleaned = before
                # حذف احتمالی کلمات متصل مثل "تا" بعدا
                cleaned = re.sub(r'\b(تا|عدد)\b', '', cleaned).strip()
                # اگر چیزی ماند، آن را asset در نظر بگیر
                asset = cleaned
    asset = (asset or "").strip()
    # اگر asset خالی بود، مقدار پیش‌فرض را بگذار
    if not asset:
        asset = config.DEFAULT_ASSET
    # حال ضریب (عامل) را تعیین کن
    factor = 1
    if mult_word and "تا" in mult_word:
        # اگر دارایی یکی از سکه‌ها باشد، تا=1
        # بررسی اسامی سکه‌ای (case-insensitive)
        asset_lower = asset.strip().lower()
        is_coin = any(a.lower() in asset_lower for a in config.COIN_ASSETS)
        factor = 1 if is_coin else 1000
    elif mult_word and "عدد" in mult_word:
        factor = 1
    else:
        # اگر ضریب مشخص نشده، پیش‌فرض factor = 1
        factor = 1
    amount = number * factor
    # نتیجه
    return {
        "asset": asset.strip(),
        "amount": int(amount),
        "direction": direction,
        "counterparty": counterparty.strip(),
        "raw": orig
    }

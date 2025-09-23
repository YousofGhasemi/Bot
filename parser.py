import re
from typing import Optional, Dict
import config

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

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
    text = text.strip()
    if not text:
        return None
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
    return total if found else None


def _extract_number_and_multiplier(text_before_dir: str):
    s = _persian_to_english_digits(text_before_dir)
    m = re.search(r'\d+', s)
    if m:
        number = int(m.group())
        after = s[m.end():]
        mm = re.search(r'\b(تا|عدد)\b', after)
        if mm:
            mult_word = after[mm.start():mm.end()]
            return number, mult_word, (m.start(), m.end()), (m.end()+mm.start(), m.end()+mm.end())
        return number, None, (m.start(), m.end()), None
    cleaned = re.sub(r'[^\u0600-\u06FF\s]', ' ', text_before_dir).strip()
    if not cleaned:
        return None, None, None, None
    if re.search(r'\bعدد\b', cleaned):
        return 1, "عدد", (0, 1), (1, 1)
    num = _words_to_number(cleaned)
    if num is not None:
        mm = re.search(r'\b(تا|عدد)\b', cleaned)
        if mm:
            return num, mm.group(1), (0, len(cleaned)), (mm.start(), mm.end())
        return num, None, (0, len(cleaned)), None
    return None, None, None, None


def parse_message(text: str) -> Optional[Dict]:
    if not text or not isinstance(text, str):
        return None
    orig = text.strip()
    s = re.sub(r'\s+', ' ', orig.replace("\n", " ")).strip()
    dir_match = re.search(r'(?:^|\s)([وخ])(?=\s|$|[:\-])', s)
    if not dir_match:
        return None
    direction = dir_match.group(1)
    counterparty = s[dir_match.end():].lstrip(':').strip()
    before = s[:dir_match.start()].strip()
    number, mult_word, _, mult_span = _extract_number_and_multiplier(before)
    if number is None:
        return None
    asset = None
    if mult_span:
        mm = re.search(r'\b(تا|عدد)\b', before)
        if mm:
            after_mult = before[mm.end():].strip()
            asset = after_mult
    else:
        m = re.search(r'\d+', _persian_to_english_digits(before))
        if m:
            parts = re.split(r'\d+', before, maxsplit=1)
            if len(parts) >= 2:
                asset = parts[1].strip()
        else:
            cleaned = re.sub(r'\b(تا|عدد)\b', '', before).strip()
            asset = cleaned
    asset = (asset or "").strip() or config.DEFAULT_ASSET
    factor = 1
    if mult_word and "تا" in mult_word:
        is_coin = any(a.lower() in asset.lower() for a in config.COIN_ASSETS)
        factor = 1 if is_coin else 1000
    elif mult_word and "عدد" in mult_word:
        factor = 1
    amount = number * factor
    return {
        "asset": asset,
        "amount": int(amount),
        "direction": direction,
        "counterparty": counterparty,
        "raw": orig
    }

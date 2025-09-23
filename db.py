import json
import os
import time
from filelock import FileLock
import config
from typing import Optional, Dict

_DB_PATH = config.DB_PATH
_LOCK_PATH = _DB_PATH + ".lock"
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


def _default_db():
    return {"balances": {}, "totals": {}, "transactions": {}}


def _read_db() -> dict:
    if not os.path.exists(_DB_PATH):
        return _default_db()
    with FileLock(_LOCK_PATH):
        with open(_DB_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return _default_db()


def _write_db(db: dict):
    with FileLock(_LOCK_PATH):
        with open(_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)


def _ensure_asset_struct(db: dict, asset: str):
    if asset not in db["balances"]:
        db["balances"][asset] = 0
    if asset not in db["totals"]:
        db["totals"][asset] = {"in": 0, "out": 0}


def add_transaction(chat_id: int, message_id: int, tx: Dict) -> bool:
    """
    اضافه کردن تراکنش جدید؛ اگر تراکنش با همین ماتریال (chat_id:message_id) موجود باشد،
    False برمی‌گرداند.
    """
    key = f"{chat_id}:{message_id}"
    db = _read_db()
    if key in db["transactions"]:
        return False
    asset = tx["asset"]
    amount = int(tx["amount"])
    direction = tx["direction"]
    _ensure_asset_struct(db, asset)
    # اعمال مقدار روی موجودی و totals
    if direction == "و":  # ورود => اضافه
        db["balances"][asset] += amount
        db["totals"][asset]["in"] += amount
    else:  # 'خ' => خروج => کم
        db["balances"][asset] -= amount
        db["totals"][asset]["out"] += amount
    tx_rec = tx.copy()
    tx_rec.update({
        "chat_id": chat_id,
        "message_id": message_id,
        "ts": int(time.time())
    })
    db["transactions"][key] = tx_rec
    _write_db(db)
    return True


def remove_transaction(chat_id: int, message_id: int) -> bool:
    """
    حذف تراکنش از ثبت (مثلاً وقتی پیام حذف شد). اگر وجود نداشت False برمی‌گرداند.
    """
    key = f"{chat_id}:{message_id}"
    db = _read_db()
    if key not in db["transactions"]:
        return False
    tx = db["transactions"].pop(key)
    asset = tx["asset"]
    amount = int(tx["amount"])
    direction = tx["direction"]
    _ensure_asset_struct(db, asset)
    # معکوس کردن اثر تراکنش
    if direction == "و":
        db["balances"][asset] -= amount
        db["totals"][asset]["in"] -= amount
    else:
        db["balances"][asset] += amount
        db["totals"][asset]["out"] -= amount
    _write_db(db)
    return True


def update_transaction(chat_id: int, message_id: int, new_tx: Dict) -> bool:
    """
    ویرایش تراکنش: اگر رکورد قبلاً وجود داشته باشد، اثر قبلی را برمی‌دارد و اثر جدید را می‌زند.
    در صورت نبود رکورد سابق، رفتار معادل add_transaction انجام می‌دهد.
    """
    key = f"{chat_id}:{message_id}"
    db = _read_db()
    if key in db["transactions"]:
        old = db["transactions"][key]
        # معکوس کردن اثر قدیمی
        old_asset = old["asset"]
        old_amount = int(old["amount"])
        old_dir = old["direction"]
        _ensure_asset_struct(db, old_asset)
        if old_dir == "و":
            db["balances"][old_asset] -= old_amount
            db["totals"][old_asset]["in"] -= old_amount
        else:
            db["balances"][old_asset] += old_amount
            db["totals"][old_asset]["out"] -= old_amount
    # سپس اضافه کردن نسخه جدید
    asset = new_tx["asset"]
    amount = int(new_tx["amount"])
    direction = new_tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["balances"][asset] += amount
        db["totals"][asset]["in"] += amount
    else:
        db["balances"][asset] -= amount
        db["totals"][asset]["out"] += amount
    new_rec = new_tx.copy()
    new_rec.update({
        "chat_id": chat_id,
        "message_id": message_id,
        "ts": int(time.time())
    })
    db["transactions"][key] = new_rec
    _write_db(db)
    return True


def get_balance(asset: str) -> int:
    db = _read_db()
    return int(db.get("balances", {}).get(asset, 0))


def get_all_balances() -> Dict[str, int]:
    db = _read_db()
    return db.get("balances", {}).copy()


def get_report_table() -> Dict[str, Dict[str, int]]:
    """
    برمی‌گرداند dict با ساختار:
    { asset: {"in": total_in, "out": total_out}, ... }
    """
    db = _read_db()
    return db.get("totals", {}).copy()


def get_transaction(key: str) -> Optional[Dict]:
    db = _read_db()
    return db.get("transactions", {}).get(key)

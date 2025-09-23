import json
import os
import time
from filelock import FileLock
import config
from typing import Optional, Dict

os.makedirs(config.DB_DIR, exist_ok=True)


def _db_path(chat_id: int) -> str:
    return os.path.join(config.DB_DIR, f"group_{chat_id}.json")


def _lock_path(chat_id: int) -> str:
    return _db_path(chat_id) + ".lock"


def _default_db():
    return {
        "confirmed_balance": {},   # مانده تاییدشده (baseline)
        "totals": {},              # { asset: {"in": 0, "out": 0} }
        "transactions": {},        # { message_id_str: tx_rec }
        "dashboard_message_id": None
    }


def _read_db(chat_id: int) -> dict:
    path = _db_path(chat_id)
    if not os.path.exists(path):
        return _default_db()
    with FileLock(_lock_path(chat_id)):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return _default_db()


def _write_db(chat_id: int, db: dict):
    path = _db_path(chat_id)
    with FileLock(_lock_path(chat_id)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)


def _ensure_asset_struct(db: dict, asset: str):
    if "totals" not in db:
        db["totals"] = {}
    if asset not in db["totals"]:
        db["totals"][asset] = {"in": 0, "out": 0}
    if "confirmed_balance" not in db:
        db["confirmed_balance"] = {}
    if asset not in db["confirmed_balance"]:
        db["confirmed_balance"][asset] = 0


# -- Dashboard message id helpers
def set_dashboard_message_id(chat_id: int, message_id: Optional[int]):
    db = _read_db(chat_id)
    db["dashboard_message_id"] = message_id
    _write_db(chat_id, db)


def get_dashboard_message_id(chat_id: int) -> Optional[int]:
    db = _read_db(chat_id)
    return db.get("dashboard_message_id")


# -- Transaction operations (affect totals only)
def add_transaction(chat_id: int, message_id: int, tx: Dict) -> bool:
    key = str(message_id)
    db = _read_db(chat_id)
    if key in db.get("transactions", {}):
        return False
    asset = tx["asset"]
    amount = int(tx["amount"])
    direction = tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["totals"][asset]["in"] += amount
    else:
        db["totals"][asset]["out"] += amount
    tx_rec = tx.copy()
    tx_rec.update({
        "chat_id": chat_id,
        "message_id": message_id,
        "ts": int(time.time())
    })
    db["transactions"][key] = tx_rec
    _write_db(chat_id, db)
    return True


def remove_transaction(chat_id: int, message_id: int) -> bool:
    key = str(message_id)
    db = _read_db(chat_id)
    if key not in db.get("transactions", {}):
        return False
    tx = db["transactions"].pop(key)
    asset = tx["asset"]
    amount = int(tx["amount"])
    direction = tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["totals"][asset]["in"] -= amount
    else:
        db["totals"][asset]["out"] -= amount
    _write_db(chat_id, db)
    return True


def update_transaction(chat_id: int, message_id: int, new_tx: Dict) -> bool:
    key = str(message_id)
    db = _read_db(chat_id)
    # revert old if exists
    if key in db.get("transactions", {}):
        old = db["transactions"][key]
        old_asset = old["asset"]
        old_amount = int(old["amount"])
        old_dir = old["direction"]
        _ensure_asset_struct(db, old_asset)
        if old_dir == "و":
            db["totals"][old_asset]["in"] -= old_amount
        else:
            db["totals"][old_asset]["out"] -= old_amount
    # apply new
    asset = new_tx["asset"]
    amount = int(new_tx["amount"])
    direction = new_tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["totals"][asset]["in"] += amount
    else:
        db["totals"][asset]["out"] += amount
    new_rec = new_tx.copy()
    new_rec.update({
        "chat_id": chat_id,
        "message_id": message_id,
        "ts": int(time.time())
    })
    db["transactions"][key] = new_rec
    _write_db(chat_id, db)
    return True


# -- Reporting / balances
def get_report_table(chat_id: int) -> Dict[str, Dict[str, int]]:
    db = _read_db(chat_id)
    return db.get("totals", {}).copy()


def get_confirmed_balances(chat_id: int) -> Dict[str, int]:
    db = _read_db(chat_id)
    return db.get("confirmed_balance", {}).copy()


def get_balance(chat_id: int, asset: str) -> int:
    db = _read_db(chat_id)
    _ensure_asset_struct(db, asset)
    confirmed = int(db.get("confirmed_balance", {}).get(asset, 0))
    totals = db.get("totals", {}).get(asset, {"in": 0, "out": 0})
    return confirmed + int(totals.get("in", 0)) - int(totals.get("out", 0))


def get_all_balances(chat_id: int) -> Dict[str, int]:
    db = _read_db(chat_id)
    assets = set(db.get("confirmed_balance", {}).keys()) | set(db.get("totals", {}).keys())
    out = {}
    for a in assets:
        out[a] = get_balance(chat_id, a)
    return out


def get_transaction(chat_id: int, message_id: int) -> Optional[Dict]:
    db = _read_db(chat_id)
    return db.get("transactions", {}).get(str(message_id))


# -- Confirm day: set confirmed_balance = current, zero totals, clear transactions
def confirm_day(chat_id: int):
    db = _read_db(chat_id)
    totals = db.get("totals", {})
    confirmed = db.get("confirmed_balance", {})
    assets = set(confirmed.keys()) | set(totals.keys())
    for asset in assets:
        _ensure_asset_struct(db, asset)
        cur = confirmed.get(asset, 0) + totals.get(asset, {}).get("in", 0) - totals.get(asset, {}).get("out", 0)
        db["confirmed_balance"][asset] = int(cur)
        db["totals"][asset] = {"in": 0, "out": 0}
    # clear transactions (we consider them archived/consumed on confirm)
    db["transactions"] = {}
    _write_db(chat_id, db)

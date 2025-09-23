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
    return {"balances": {}, "totals": {}, "transactions": {}}


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
    if asset not in db["balances"]:
        db["balances"][asset] = 0
    if asset not in db["totals"]:
        db["totals"][asset] = {"in": 0, "out": 0}


def add_transaction(chat_id: int, message_id: int, tx: Dict) -> bool:
    key = str(message_id)
    db = _read_db(chat_id)
    if key in db["transactions"]:
        return False
    asset = tx["asset"]
    amount = int(tx["amount"])
    direction = tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["balances"][asset] += amount
        db["totals"][asset]["in"] += amount
    else:
        db["balances"][asset] -= amount
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
    if key not in db["transactions"]:
        return False
    tx = db["transactions"].pop(key)
    asset = tx["asset"]
    amount = int(tx["amount"])
    direction = tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["balances"][asset] -= amount
        db["totals"][asset]["in"] -= amount
    else:
        db["balances"][asset] += amount
        db["totals"][asset]["out"] -= amount
    _write_db(chat_id, db)
    return True


def update_transaction(chat_id: int, message_id: int, new_tx: Dict) -> bool:
    key = str(message_id)
    db = _read_db(chat_id)
    if key in db["transactions"]:
        old = db["transactions"][key]
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
    asset = new_tx["asset"]
    amount = int(new_tx["amount"])
    direction = new_tx["direction"]
    _ensure_asset_struct(db, asset)
    if direction == "و":
        db["balances"][asset] += amount
        db["totals"][asset]["in"] += amount
    else:
        db["balances"][asset] -= amount
        db["totals"][asset]["out"] -= amount
    new_rec = new_tx.copy()
    new_rec.update({
        "chat_id": chat_id,
        "message_id": message_id,
        "ts": int(time.time())
    })
    db["transactions"][key] = new_rec
    _write_db(chat_id, db)
    return True


def get_balance(chat_id: int, asset: str) -> int:
    db = _read_db(chat_id)
    return int(db.get("balances", {}).get(asset, 0))


def get_all_balances(chat_id: int) -> Dict[str, int]:
    db = _read_db(chat_id)
    return db.get("balances", {}).copy()


def get_report_table(chat_id: int) -> Dict[str, Dict[str, int]]:
    db = _read_db(chat_id)
    return db.get("totals", {}).copy()


def get_transaction(chat_id: int, message_id: int) -> Optional[Dict]:
    db = _read_db(chat_id)
    return db.get("transactions", {}).get(str(message_id))

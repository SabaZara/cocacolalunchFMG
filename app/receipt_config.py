"""Printer settings editable remotely, independent of meal/card data."""
import json
import os
from pathlib import Path
from threading import Lock

from .config import ROOT

CONFIG_PATH = ROOT / ".receipt-config.json"
_lock = Lock()


def read() -> dict:
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {"enabled": bool(saved["enabled"]), "printer": str(saved["printer"])}
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "enabled": os.getenv("RECEIPT_PRINTING", "false").strip().lower()
            in {"true", "1", "yes", "on"},
            "printer": os.getenv("RECEIPT_PRINTER", "").strip(),
        }


def save(printer: str, enabled: bool) -> dict:
    config = {"printer": printer.strip(), "enabled": enabled}
    with _lock:
        temporary = CONFIG_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        temporary.replace(CONFIG_PATH)
    return config

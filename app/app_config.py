"""Runtime-editable settings, changeable from the admin panel.

Stored in a gitignored JSON file on the kiosk (.app-config.json), so changes:
  * survive app restarts and remote updates (the file is preserved), and
  * need no code push / no .env edit / no kiosk access beyond the admin page.

Currently holds the meal "day split" time: meals scanned BEFORE the split count
as პირველი კვება, at/after it as მეორე კვება (real, clock-corrected time).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import ROOT

APP_CONFIG_PATH = ROOT / ".app-config.json"

DEFAULT_MEAL_SPLIT = "18:00"

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _load() -> dict:
    try:
        return json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(cfg: dict) -> None:
    APP_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                              encoding="utf-8")


def valid_hhmm(value: str) -> bool:
    return bool(_HHMM.match((value or "").strip()))


def get_meal_split() -> str:
    """The 'HH:MM' boundary between first and second lunch."""
    v = str(_load().get("meal_split", "")).strip()
    return v if valid_hhmm(v) else DEFAULT_MEAL_SPLIT


def set_meal_split(value: str) -> str:
    """Validate + persist the split time. Returns the stored value."""
    value = (value or "").strip()
    if not valid_hhmm(value):
        raise ValueError("დროის ფორმატი უნდა იყოს HH:MM (მაგ. 18:00).")
    cfg = _load()
    cfg["meal_split"] = value
    _save(cfg)
    return value


def get_settings_public() -> dict:
    """What the admin UI reads back."""
    return {"meal_split": get_meal_split(), "default_meal_split": DEFAULT_MEAL_SPLIT}

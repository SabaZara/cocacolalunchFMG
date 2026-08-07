"""Runtime-editable settings, changeable from the admin panel.

Stored in a gitignored JSON file on the kiosk (.app-config.json), so changes:
  * survive app restarts and remote updates (the file is preserved), and
  * need no code push / no .env edit / no kiosk access beyond the admin page.

Holds:
  * the meal "day split" time: meals scanned BEFORE the split count as
    პირველი კვება, at/after it as მეორე კვება (real, clock-corrected time);
  * the daily limit — ONE number for every card (see get_daily_limit).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import ROOT

APP_CONFIG_PATH = ROOT / ".app-config.json"

DEFAULT_MEAL_SPLIT = "18:00"

# Meals allowed per card per local day. ONE global number: there is no
# per-card limit any more, so changing this changes it for everybody.
DEFAULT_DAILY_LIMIT = 1

# Sanity bound for the admin-editable limit (0 = nobody eats, which is a valid
# "close the canteen" setting; the upper bound just stops a typo like 100).
MAX_DAILY_LIMIT = 20

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


def get_daily_limit() -> int:
    """Meals allowed per card per local day — the SAME number for every card.

    Falls back to the default if the file is missing or holds junk, so a bad
    edit can never lock the whole canteen out.
    """
    raw = _load().get("daily_limit", None)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_LIMIT
    if value < 0 or value > MAX_DAILY_LIMIT:
        return DEFAULT_DAILY_LIMIT
    return value


def set_daily_limit(value) -> int:  # noqa: ANN001
    """Validate + persist the global daily limit. Returns the stored value."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"ლიმიტი უნდა იყოს რიცხვი 0–{MAX_DAILY_LIMIT}.")
    if limit < 0 or limit > MAX_DAILY_LIMIT:
        raise ValueError(f"ლიმიტი უნდა იყოს 0–{MAX_DAILY_LIMIT}.")
    cfg = _load()
    cfg["daily_limit"] = limit
    _save(cfg)
    return limit


def get_settings_public() -> dict:
    """What the admin UI reads back."""
    return {
        "meal_split": get_meal_split(),
        "default_meal_split": DEFAULT_MEAL_SPLIT,
        "daily_limit": get_daily_limit(),
        "default_daily_limit": DEFAULT_DAILY_LIMIT,
        "max_daily_limit": MAX_DAILY_LIMIT,
    }

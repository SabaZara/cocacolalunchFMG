"""Configuration & startup safety checks.

Loads settings from the environment (.env), validates that the deployment
is safe to expose to the internet, and exposes the configured timezone.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

# Project root = the directory that contains this "app" package.
ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root (no error if it is missing).
load_dotenv(ROOT / ".env")

# Passwords we flatly refuse to start with.
_WEAK_PASSWORDS = {"", "changeme", "password", "admin", "123456", "lunch"}


class ConfigError(RuntimeError):
    """Raised when the configuration is unsafe / incomplete to start."""


@dataclass(frozen=True)
class Settings:
    timezone: str
    admin_username: str
    admin_password: str
    secret_key: str
    tunnel_secret: str
    host: str
    port: int
    db_path: Path
    seed_sample_cards: bool
    # Shown in the admin/reports topbar. Several kiosks share an identical UI,
    # so this labels which location you are actually looking at.
    location_name: str
    # The kiosk PC's clock runs AHEAD of real time by this many minutes, so
    # recorded scan times look later than reality. Reports subtract this to
    # show/bucket REAL times. Code default (not .env) so remote updates can
    # deliver it — .env is preserved on update and can still override.
    kiosk_clock_ahead_min: int
    # Meal time windows for the quantitative report, as "HH:MM" strings in
    # REAL local time ("24:00" allowed as an end). Defaults are code-level so
    # a future change ships via remote update; .env can override.
    meal1_start: str
    meal1_end: str
    meal2_start: str
    meal2_end: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def cookie_secure(self) -> bool:
        """Send the session cookie as Secure only when not bound to localhost-http.

        Over the remote tunnel the browser sees HTTPS, so the cookie is sent as
        Secure. We detect "served over the tunnel" at request time instead of
        here (see security.py); this flag is the default for non-local hosts.
        """
        return self.host not in ("127.0.0.1", "localhost")


def _get(name: str, default: str | None = None) -> str:
    val = os.environ.get(name)
    if val is None:
        val = default
    return val if val is not None else ""


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    timezone = _get("TIMEZONE", "Asia/Tbilisi").strip()
    admin_username = _get("ADMIN_USERNAME", "admin").strip()
    admin_password = _get("ADMIN_PASSWORD")
    secret_key = _get("SECRET_KEY").strip()
    tunnel_secret = _get("TUNNEL_SECRET").strip()
    host = _get("HOST", "127.0.0.1").strip()
    try:
        port = int(_get("PORT", "8000"))
    except ValueError:
        raise ConfigError("PORT must be an integer.")
    db_path_raw = _get("DB_PATH", "lunch.db").strip()
    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = ROOT / db_path

    # Default FALSE: a production kiosk should start with only the admin and the
    # real imported cards, not demo data. Tests/dev can set it true.
    seed_sample_cards = _get_bool("SEED_SAMPLE_CARDS", False)
    location_name = _get("LOCATION_NAME", "").strip()

    try:
        kiosk_clock_ahead_min = int(_get("KIOSK_CLOCK_AHEAD_MINUTES", "14"))
    except ValueError:
        kiosk_clock_ahead_min = 14

    meal1_start = _get("MEAL1_START", "00:00").strip()
    meal1_end = _get("MEAL1_END", "18:00").strip()
    meal2_start = _get("MEAL2_START", "18:00").strip()
    meal2_end = _get("MEAL2_END", "24:00").strip()

    return Settings(
        timezone=timezone,
        admin_username=admin_username,
        admin_password=admin_password,
        secret_key=secret_key,
        tunnel_secret=tunnel_secret,
        host=host,
        port=port,
        db_path=db_path,
        seed_sample_cards=seed_sample_cards,
        location_name=location_name,
        kiosk_clock_ahead_min=kiosk_clock_ahead_min,
        meal1_start=meal1_start,
        meal1_end=meal1_end,
        meal2_start=meal2_start,
        meal2_end=meal2_end,
    )


def validate_settings(settings: Settings) -> None:
    """Hard safety gate. Raises ConfigError with an actionable message.

    Called on app startup AND before launching uvicorn so a misconfigured
    deployment fails loudly instead of going live with a weak password.
    """
    problems: list[str] = []

    if settings.admin_password.strip().lower() in _WEAK_PASSWORDS:
        problems.append(
            "ADMIN_PASSWORD is blank or too weak. Set a strong password in .env."
        )

    if len(settings.secret_key) < 32:
        problems.append(
            "SECRET_KEY is missing or too short (need >= 32 chars). "
            'Generate one with:  python -c "import secrets; '
            'print(secrets.token_urlsafe(48))"'
        )

    try:
        ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        problems.append(
            f"TIMEZONE '{settings.timezone}' is not a valid IANA zone. "
            "(Is 'tzdata' installed? It is required on Windows.)"
        )

    if problems:
        raise ConfigError("\n  - ".join(["Refusing to start:"] + problems))


def validate_or_exit() -> Settings:
    """Validate; on failure print the message and exit(1) (used by entrypoints)."""
    settings = get_settings()
    try:
        validate_settings(settings)
    except ConfigError as exc:
        print(f"\n[CONFIG ERROR] {exc}\n", file=sys.stderr)
        sys.exit(1)
    return settings

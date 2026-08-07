"""Time helpers: UTC now + local calendar-day computation.

The "once per calendar day" rule resets at LOCAL midnight in the configured
timezone. We always STORE timestamps in UTC and derive the local_date from the
configured zone, so the rule is unambiguous regardless of server clock zone.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def local_date_for(dt_utc: datetime, tz: ZoneInfo) -> date:
    """The local calendar date (in tz) for a given UTC instant."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(tz).date()


def to_local(dt_utc: datetime, tz: ZoneInfo) -> datetime:
    """Convert a UTC instant to local tz (aware)."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(tz)


def local_time_str(dt_utc: datetime, tz: ZoneInfo) -> str:
    """HH:MM:SS in local tz — used for kiosk + reports display."""
    return to_local(dt_utc, tz).strftime("%H:%M:%S")

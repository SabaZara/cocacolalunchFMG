"""Core meal-limit scan decision.

Each person may claim up to `daily_limit` meals per LOCAL calendar day
(default 2). Statuses stay in English internally ("ALLOWED" / "DENIED") so other
code and tests can key on them; only the human-facing reason text is Georgian.

Race safety WITHOUT a unique constraint: we INSERT the scan, flush, then count
today's scans for this person. If the count exceeds the limit, this tap lost a
concurrent race and we roll it back. Combined with SQLite's serialized writes
(busy_timeout) this yields "at most daily_limit ALLOWED" under concurrent taps.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from .config import get_settings
from .models import Person, Scan
from .timeutil import local_date_for, local_time_str, utc_now

# Machine-readable statuses (never localized).
STATUS_ALLOWED = "ALLOWED"
STATUS_DENIED = "DENIED"

# Georgian reason codes shown to the user.
REASON_UNKNOWN_CARD = "უცნობი ბარათი"
REASON_INACTIVE = "ბარათი გათიშულია"
REASON_LIMIT_REACHED = "დღის ლიმიტი ამოიწურა"


@dataclass
class ScanResult:
    status: str
    reason: str | None = None
    scanned_at: str | None = None   # local HH:MM:SS for display
    remaining: int | None = None    # meals left today after this scan
    limit: int | None = None        # the person's daily limit


def normalize_card_id(raw: str) -> str:
    """Trim surrounding whitespace but preserve everything else (leading zeros)."""
    return (raw or "").strip()


def _count_today(session: Session, person_id: int, day) -> int:  # noqa: ANN001
    return int(session.exec(
        select(func.count()).select_from(Scan).where(
            Scan.person_id == person_id, Scan.local_date == day
        )
    ).one())


def decide_scan(session: Session, raw_card_id: str) -> ScanResult:
    settings = get_settings()
    tz = settings.tz

    card_id = normalize_card_id(raw_card_id)
    if not card_id:
        return ScanResult(status=STATUS_DENIED, reason=REASON_UNKNOWN_CARD)

    person = session.exec(select(Person).where(Person.card_id == card_id)).first()
    if person is None:
        return ScanResult(status=STATUS_DENIED, reason=REASON_UNKNOWN_CARD)
    if not person.active:
        return ScanResult(status=STATUS_DENIED, reason=REASON_INACTIVE)

    limit = max(int(person.daily_limit), 0)
    now = utc_now()
    today = local_date_for(now, tz)

    already = _count_today(session, person.id, today)
    if already >= limit:
        return ScanResult(status=STATUS_DENIED, reason=REASON_LIMIT_REACHED,
                          remaining=0, limit=limit)

    # Tentatively record the meal, then re-check under the actual row count to
    # stay correct if two taps raced past the SELECT above.
    scan = Scan(person_id=person.id, card_id=card_id, scanned_at=now, local_date=today)
    session.add(scan)
    session.flush()
    count_after = _count_today(session, person.id, today)
    if count_after > limit:
        # We over-committed in a race — undo this one.
        session.rollback()
        return ScanResult(status=STATUS_DENIED, reason=REASON_LIMIT_REACHED,
                          remaining=0, limit=limit)

    session.commit()
    session.refresh(scan)
    return ScanResult(
        status=STATUS_ALLOWED,
        scanned_at=local_time_str(scan.scanned_at, tz),
        remaining=max(limit - count_after, 0),
        limit=limit,
    )

"""Core meal-limit scan decision.

There is NO pre-approved list of cards. A card the app has never seen is
REGISTERED on its first tap and that tap counts as a meal — the card list
builds itself from real taps, and nobody is turned away at the kiosk. Names can
be filled in later from the admin panel (people.full_name already exists).

Every card gets the SAME daily limit, a single admin-editable number
(app_config.get_daily_limit, default 1). Cards carry no individual limit.

The one thing that still blocks a tap is an admin DEACTIVATING a card (lost /
stolen / left the company): a deactivated card is denied and is NOT silently
re-created by the auto-register path.

Statuses stay in English internally ("ALLOWED" / "DENIED") so other code and
tests can key on them; only the human-facing reason text is Georgian.

Race safety WITHOUT a unique constraint: we INSERT the scan, flush, then count
today's scans for this person. If the count exceeds the limit, this tap lost a
concurrent race and we roll it back. Combined with SQLite's serialized writes
(busy_timeout) this yields "at most daily_limit ALLOWED" under concurrent taps.
Auto-registration races on people.card_id (UNIQUE): the loser of an INSERT race
re-reads the row the winner committed instead of failing the tap.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from . import app_config as AC
from .config import get_settings
from .models import NAME_PLACEHOLDER, Person, Scan
from .timeutil import local_date_for, local_time_str, utc_now

# Machine-readable statuses (never localized).
STATUS_ALLOWED = "ALLOWED"
STATUS_DENIED = "DENIED"

# Georgian reason codes shown to the user.
# Kept for the empty-card-id case; a card simply being new is no longer a
# denial reason (unknown cards auto-register instead).
REASON_UNKNOWN_CARD = "უცნობი ბარათი"
REASON_INACTIVE = "ბარათი გათიშულია"
REASON_LIMIT_REACHED = "დღის ლიმიტი ამოიწურა"


@dataclass
class ScanResult:
    status: str
    reason: str | None = None
    scanned_at: str | None = None   # local HH:MM:SS for display
    remaining: int | None = None    # meals left today after this scan
    limit: int | None = None        # the daily limit (same for every card)
    registered: bool = False        # True when this tap created the card


def normalize_card_id(raw: str) -> str:
    """Trim surrounding whitespace but preserve everything else (leading zeros)."""
    return (raw or "").strip()


def _count_today(session: Session, person_id: int, day) -> int:  # noqa: ANN001
    return int(session.exec(
        select(func.count()).select_from(Scan).where(
            Scan.person_id == person_id, Scan.local_date == day
        )
    ).one())


def _get_or_create_person(session: Session, card_id: str) -> tuple[Person, bool]:
    """Return (person, created). Registers the card if it has never tapped.

    Two kiosks (or two fast taps) can reach the INSERT at once; people.card_id
    is UNIQUE, so the loser catches IntegrityError and re-reads the winner's
    row. The tap then proceeds normally instead of erroring at the reader.
    """
    person = session.exec(select(Person).where(Person.card_id == card_id)).first()
    if person is not None:
        return person, False

    person = Person(card_id=card_id, full_name=NAME_PLACEHOLDER, active=True)
    session.add(person)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.exec(
            select(Person).where(Person.card_id == card_id)
        ).first()
        if existing is None:
            raise
        return existing, False
    session.refresh(person)
    return person, True


def decide_scan(session: Session, raw_card_id: str) -> ScanResult:
    settings = get_settings()
    tz = settings.tz

    # One limit for everybody, read fresh so an admin change takes effect on
    # the very next tap without a restart.
    limit = max(AC.get_daily_limit(), 0)

    card_id = normalize_card_id(raw_card_id)
    if not card_id:
        return ScanResult(status=STATUS_DENIED, reason=REASON_UNKNOWN_CARD,
                          limit=limit)

    person, created = _get_or_create_person(session, card_id)
    if not person.active:
        # Deactivated by an admin — stays blocked, and is not re-registered.
        return ScanResult(status=STATUS_DENIED, reason=REASON_INACTIVE,
                          limit=limit)

    now = utc_now()
    today = local_date_for(now, tz)

    already = _count_today(session, person.id, today)
    if already >= limit:
        return ScanResult(status=STATUS_DENIED, reason=REASON_LIMIT_REACHED,
                          remaining=0, limit=limit, registered=created)

    # Tentatively record the meal, then re-check under the actual row count to
    # stay correct if two taps raced past the SELECT above.
    scan = Scan(person_id=person.id, card_id=card_id, scanned_at=now, local_date=today)
    session.add(scan)
    session.flush()
    count_after = _count_today(session, person.id, today)
    if count_after > limit:
        # We over-committed in a race — undo this one. The person row was
        # committed separately above, so a card registered by this tap stays
        # registered; only the surplus meal is dropped.
        session.rollback()
        return ScanResult(status=STATUS_DENIED, reason=REASON_LIMIT_REACHED,
                          remaining=0, limit=limit, registered=created)

    session.commit()
    session.refresh(scan)
    return ScanResult(
        status=STATUS_ALLOWED,
        scanned_at=local_time_str(scan.scanned_at, tz),
        remaining=max(limit - count_after, 0),
        limit=limit,
        registered=created,
    )

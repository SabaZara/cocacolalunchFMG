"""Database models.

people  — one row per ID card (identified by card_id; name optional, hidden in
          UI). Rows are created automatically the first time a card taps —
          there is no pre-approved card list (see scan_service).
scans   — one row per claimed meal. The count of today's scans is compared at
          scan time against ONE global daily limit that applies to every card
          (app_config.get_daily_limit), not against a per-card value.
admins  — operator login accounts.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field, SQLModel

from .timeutil import utc_now

# Placeholder used when a card is imported/added without a real name.
NAME_PLACEHOLDER = "----"

# Column default for people.daily_limit. The scan path does NOT read this — the
# real limit is the global app_config.get_daily_limit(). Kept only so the
# existing column (and old DBs) still have a sane value.
DEFAULT_DAILY_LIMIT = 1


class Person(SQLModel, table=True):
    __tablename__ = "people"

    id: int | None = Field(default=None, primary_key=True)
    # card_id is TEXT, unique, indexed, required. Never parsed as a number;
    # leading zeros are preserved end-to-end.
    card_id: str = Field(index=True, unique=True, nullable=False)
    # Kept in the schema so names can be added later with NO migration.
    # Hidden in the UI for now; defaults to the placeholder.
    full_name: str = Field(default=NAME_PLACEHOLDER)
    department: str | None = Field(default=None)
    # Set False by an admin to block a lost/stolen card. A deactivated card is
    # denied at the kiosk and is NOT re-created by auto-registration.
    active: bool = Field(default=True)
    # LEGACY per-card limit. No longer consulted when deciding a scan; the
    # limit is now one global number in app_config. Retained so existing
    # databases need no destructive migration.
    daily_limit: int = Field(default=DEFAULT_DAILY_LIMIT, nullable=False)
    created_at: datetime = Field(default_factory=utc_now)


class Scan(SQLModel, table=True):
    __tablename__ = "scans"

    id: int | None = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="people.id", index=True, nullable=False)
    # Snapshot of the card string actually tapped (so history survives reassigns).
    card_id: str = Field(nullable=False)
    scanned_at: datetime = Field(default_factory=utc_now, nullable=False)
    # Local calendar date (in the configured timezone) the meal counted for.
    local_date: date = Field(index=True, nullable=False)


class TapLog(SQLModel, table=True):
    """One row per CARD TAP — allowed and denied alike.

    `scans` only holds meals that were actually granted, so until now a denied
    tap left no trace at all: a person turned away at the reader was invisible
    afterwards, and there was no way to tell a busy day from a day full of
    rejections. This is the raw record of what the reader saw and what the
    screen showed back.

    Deliberately independent of `scans`: meal counting must not change because
    of logging, and a log row is never consulted when deciding a scan.
    """

    __tablename__ = "tap_log"

    id: int | None = Field(default=None, primary_key=True)
    # What the reader actually read (may be a card we have never seen).
    card_id: str = Field(index=True, nullable=False)
    # ALLOWED / DENIED, exactly as scan_service decided it.
    status: str = Field(index=True, nullable=False)
    # Georgian reason shown on the red screen; empty when allowed.
    reason: str = Field(default="")
    # True when this tap registered a brand-new card.
    registered: bool = Field(default=False)
    # The limit in force at that moment, and how many meals remained after.
    limit_at_tap: int = Field(default=0)
    remaining: int = Field(default=0)
    tapped_at: datetime = Field(default_factory=utc_now, nullable=False)
    # Local calendar date, so a day's log is one indexed lookup.
    local_date: date = Field(index=True, nullable=False)


class RosterEntry(SQLModel, table=True):
    """Coca-Cola personnel list: their card number -> that person's name.

    Imported from Coca-Cola's own export, so names are spelled exactly as their
    records spell them instead of being re-typed by hand. Keyed by the
    Coca-Cola code (`DDD-DDDDD`) because that is the only identifier the two
    systems share — our kiosk sees a POS id, which converts to this code
    one-way (see cardcode.pos_to_cc).

    Reference data only: it never decides whether somebody may eat.
    """

    __tablename__ = "roster"

    id: int | None = Field(default=None, primary_key=True)
    cc_code: str = Field(index=True, unique=True, nullable=False)
    full_name: str = Field(nullable=False)
    updated_at: datetime = Field(default_factory=utc_now)


class Admin(SQLModel, table=True):
    __tablename__ = "admins"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, nullable=False)
    password_hash: str = Field(nullable=False)

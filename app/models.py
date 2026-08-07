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


class Admin(SQLModel, table=True):
    __tablename__ = "admins"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, nullable=False)
    password_hash: str = Field(nullable=False)

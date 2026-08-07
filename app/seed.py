"""Seed helpers: create the admin from config, and optional sample cards.

seed_admin() is called on every startup (idempotent). seed_sample_cards() is
used by scripts/seed.py for a ready-to-demo dataset.
"""
from __future__ import annotations

from sqlmodel import Session, select

from .config import get_settings
from .db import engine
from .models import NAME_PLACEHOLDER, Admin, Person
from .security import hash_password

# A handful of demo cards: a normal card, a LEADING-ZERO card, and an inactive
# one. Names left as the placeholder, as required.
SAMPLE_CARDS: list[tuple[str, bool]] = [
    ("1001", True),
    ("1002", True),
    ("1003", True),
    ("0573856032", True),   # leading-zero example — must be preserved
    ("0000123", True),      # another leading-zero example
    ("9999", False),        # inactive card → should be denied at the kiosk
]


def seed_admin(session: Session) -> Admin:
    """Create the configured admin if it does not exist yet."""
    settings = get_settings()
    admin = session.exec(
        select(Admin).where(Admin.username == settings.admin_username)
    ).first()
    if admin is None:
        admin = Admin(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
    return admin


def seed_sample_cards(session: Session) -> int:
    """Insert sample cards that don't already exist. Returns count added."""
    added = 0
    for card_id, active in SAMPLE_CARDS:
        exists = session.exec(
            select(Person).where(Person.card_id == card_id)
        ).first()
        if exists is None:
            session.add(
                Person(card_id=card_id, full_name=NAME_PLACEHOLDER, active=active)
            )
            added += 1
    if added:
        session.commit()
    return added


def run_startup_seed() -> None:
    """Idempotent startup seeding: ensure the admin exists."""
    with Session(engine) as session:
        seed_admin(session)

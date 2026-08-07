"""Startup helper checks for the Windows launcher path."""
from __future__ import annotations

import importlib
import sys

from sqlmodel import Session, func, select


def _load_startup_stack(monkeypatch, db_path):
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("TIMEZONE", "Asia/Tbilisi")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "StrongTestPass!2026")
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("TUNNEL_SECRET", "t" * 32)
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8000")
    # This test asserts demo cards are seeded once; enable the opt-in flag.
    monkeypatch.setenv("SEED_SAMPLE_CARDS", "true")

    for name in (
        "app.config",
        "app.db",
        "app.security",
        "app.seed",
        "scripts.startup_prepare",
    ):
        if name in sys.modules:
            importlib.reload(sys.modules[name])

    import app.db as db
    import app.seed as seed
    import scripts.startup_prepare as startup_prepare

    importlib.reload(db)
    importlib.reload(seed)
    importlib.reload(startup_prepare)
    return startup_prepare, db


def test_startup_prepare_does_not_reseed_demo_cards_for_existing_db(tmp_path, monkeypatch):
    startup_prepare, db = _load_startup_stack(monkeypatch, tmp_path / "lunch.db")

    assert startup_prepare.main() == 0

    from app.models import Person

    with Session(db.engine) as session:
        initial_count = session.exec(select(func.count()).select_from(Person)).one()
        person = session.exec(select(Person).where(Person.card_id == "1001")).first()
        assert person is not None
        session.delete(person)
        session.commit()

    assert startup_prepare.main() == 0

    with Session(db.engine) as session:
        final_count = session.exec(select(func.count()).select_from(Person)).one()
        deleted = session.exec(select(Person).where(Person.card_id == "1001")).first()

    assert initial_count == 6
    assert final_count == 5
    assert deleted is None

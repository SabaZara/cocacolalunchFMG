"""Prepare the app for start.bat without re-adding demo data every run.

This validates unsafe config, creates the database tables, seeds the configured
admin account, and only inserts sample/demo cards when the database file did
not exist before startup. The standalone demo seed script remains available as
`python -m scripts.seed`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow "python scripts/startup_prepare.py" as well as module execution.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session  # noqa: E402

from app.config import validate_or_exit  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.seed import seed_admin, seed_sample_cards  # noqa: E402


def main() -> int:
    settings = validate_or_exit()
    db_existed = settings.db_path.exists()

    init_db()
    with Session(engine) as session:
        admin = seed_admin(session)
        admin_name = admin.username
        # Demo cards only when explicitly enabled AND the DB is brand new.
        # A production kiosk (SEED_SAMPLE_CARDS=false, the default) starts with
        # just the admin, so the real imported list stays clean.
        if settings.seed_sample_cards and not db_existed:
            sample_added = seed_sample_cards(session)
        else:
            sample_added = 0

    print(f"Admin ready: {admin_name}")
    if db_existed:
        print("Existing database found; left as-is.")
    elif settings.seed_sample_cards:
        print(f"New database created; sample cards added: {sample_added}")
    else:
        print("New database created; no demo cards (SEED_SAMPLE_CARDS is off).")
    print("Startup checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Seed the database with the admin + a few demo cards.

Run:  python -m scripts.seed
Creates the DB if missing, seeds the configured admin, and inserts the sample
cards (incl. a leading-zero card and one inactive card; names left as "----").
Idempotent — safe to run repeatedly.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow "python scripts/seed.py" as well as "python -m scripts.seed".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session  # noqa: E402

from app.config import validate_or_exit  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.seed import seed_admin, seed_sample_cards  # noqa: E402


def main() -> None:
    validate_or_exit()
    init_db()
    with Session(engine) as session:
        admin = seed_admin(session)
        admin_name = admin.username  # read inside the session (avoid detach)
        added = seed_sample_cards(session)
    print(f"Admin ready: {admin_name}")
    print(f"Sample cards added: {added}")
    print("Done.")


if __name__ == "__main__":
    main()

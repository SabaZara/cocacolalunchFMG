"""Create any new tables/columns the freshly-downloaded code expects.

WHY THIS RUNS SEPARATELY
------------------------
`init_db()` only runs when the app starts, so an update that adds a table used
to REQUIRE a restart: with "update without restart" the new code landed on
disk while the running app kept serving the old code against a database that
had no such table, and the new feature silently showed nothing.

This script is launched by the update endpoint as its own process, so it
imports the NEW code (the running app is still on the old code in memory) and
applies the schema to the same database file. SQLite handles the concurrent
access — CREATE TABLE is quick and `init_db` is idempotent — so the kiosk keeps
scanning throughout.

It only ever ADDS things. Nothing is dropped or rewritten, so running it
against an already-current database is a no-op.

Exit codes: 0 = schema is current, 1 = failed (the caller reports it).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        from app.db import init_db

        before = _tables()
        init_db()
        after = _tables()
        added = sorted(after - before)
        if added:
            print(f"[migrate] added: {', '.join(added)}")
        else:
            print("[migrate] schema already current")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[migrate] failed: {exc}", file=sys.stderr)
        return 1


def _tables() -> set[str]:
    """Table names currently in the database ( empty set if unreadable )."""
    try:
        import sqlite3

        from app.config import get_settings

        path = get_settings().db_path
        if not path.exists():
            return set()
        con = sqlite3.connect(str(path))
        try:
            return {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return set()


if __name__ == "__main__":
    raise SystemExit(main())

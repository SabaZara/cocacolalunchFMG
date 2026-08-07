"""Export the database as ONE self-contained file (WAL folded in).

Why this exists
---------------
SQLite in WAL mode keeps recent writes in `lunch.db-wal`, NOT in `lunch.db`.
Copying only `lunch.db` to a new install can therefore silently lose data (this
was caught in a dry run: 520 cards became 0). This script uses SQLite's online
backup API to produce `lunch-export.db`, a single file that already contains
everything, safe to copy on its own — even while the app is running.

Also prints a row count so you can VERIFY the export before trusting it.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return -1


def main() -> int:
    try:
        from app.config import get_settings
        src = get_settings().db_path
    except Exception:  # noqa: BLE001  (fall back if config can't load)
        src = ROOT / "lunch.db"

    if not src.exists():
        print(f"[export] no database found at {src}")
        return 1

    dest = ROOT / "lunch-export.db"
    if dest.exists():
        dest.unlink()

    src_conn = sqlite3.connect(str(src))
    try:
        # Fold any WAL content into the copy (consistent, even while running).
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    check = sqlite3.connect(str(dest))
    try:
        people = _count(check, "people")
        scans = _count(check, "scans")
    finally:
        check.close()

    size_kb = dest.stat().st_size / 1024
    print(f"[export] wrote {dest.name}  ({size_kb:.0f} KB)")
    print(f"[export]   cards : {people}")
    print(f"[export]   scans : {scans}")
    if people <= 0:
        print("[export] WARNING: no cards found - check you ran this in the")
        print("[export]          folder that holds the live lunch.db")
        return 1
    print("[export] OK - this single file contains everything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

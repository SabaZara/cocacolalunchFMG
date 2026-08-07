"""Database engine, session factory, and one-time initialization.

SQLite specifics:
  * check_same_thread=False so FastAPI's threadpool can share the engine.
  * WAL journal mode + busy_timeout so concurrent taps don't error out on a
    locked file.
  * PRAGMA foreign_keys=ON to enforce the FK.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def _migrate(conn) -> None:  # noqa: ANN001
    """Lightweight in-place migrations for existing SQLite DBs.

    1. Add people.daily_limit if missing (default 2).
    2. Drop the legacy UNIQUE(person_id, local_date) on scans, which used to
       enforce once-per-day. Multiple meals/day are now allowed, so the table is
       rebuilt without that constraint if it is present.
    """
    from .models import DEFAULT_DAILY_LIMIT

    # 1) people.daily_limit
    cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(people)").fetchall()]
    if cols and "daily_limit" not in cols:
        conn.exec_driver_sql(
            f"ALTER TABLE people ADD COLUMN daily_limit INTEGER NOT NULL "
            f"DEFAULT {int(DEFAULT_DAILY_LIMIT)}"
        )

    # 2) drop legacy unique constraint on scans, if it exists
    idx_rows = conn.exec_driver_sql("PRAGMA index_list(scans)").fetchall()
    has_legacy_unique = False
    for row in idx_rows:
        name = row[1]
        unique = bool(row[2])
        if not unique:
            continue
        cols_of_idx = [r[2] for r in conn.exec_driver_sql(
            f"PRAGMA index_info('{name}')").fetchall()]
        if set(cols_of_idx) == {"person_id", "local_date"}:
            has_legacy_unique = True
            break

    if has_legacy_unique:
        # Rebuild scans without the UNIQUE constraint (SQLite can't drop it).
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.exec_driver_sql("""
            CREATE TABLE scans_new (
                id INTEGER PRIMARY KEY,
                person_id INTEGER NOT NULL REFERENCES people(id),
                card_id VARCHAR NOT NULL,
                scanned_at DATETIME NOT NULL,
                local_date DATE NOT NULL
            )
        """)
        conn.exec_driver_sql(
            "INSERT INTO scans_new (id, person_id, card_id, scanned_at, local_date) "
            "SELECT id, person_id, card_id, scanned_at, local_date FROM scans"
        )
        conn.exec_driver_sql("DROP TABLE scans")
        conn.exec_driver_sql("ALTER TABLE scans_new RENAME TO scans")
        conn.exec_driver_sql("CREATE INDEX ix_scans_person_id ON scans (person_id)")
        conn.exec_driver_sql("CREATE INDEX ix_scans_local_date ON scans (local_date)")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def init_db() -> None:
    """Create tables if they do not exist, then run migrations. Idempotent."""
    # Importing models registers them on SQLModel.metadata.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        _migrate(conn)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session, closed after the request."""
    with Session(engine) as session:
        yield session

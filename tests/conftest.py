"""Test fixtures: a fresh temp DB + configured env per test session.

We set environment variables BEFORE importing the app so config picks them up,
then build a TestClient (which runs the lifespan: init_db + seed admin).
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADMIN_USER = "admin"
ADMIN_PASS = "StrongTestPass!2026"


@pytest.fixture()
def app_ctx(monkeypatch):
    """Yield (client, settings, modules) with a fresh DB for each test."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("TIMEZONE", "Asia/Tbilisi")
    monkeypatch.setenv("ADMIN_USERNAME", ADMIN_USER)
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASS)
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("TUNNEL_SECRET", "tunnel-secret-value-123456")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8000")
    # Deterministic clock correction + meal windows for report tests.
    monkeypatch.setenv("KIOSK_CLOCK_AHEAD_MINUTES", "14")
    monkeypatch.setenv("MEAL1_START", "00:00")
    monkeypatch.setenv("MEAL1_END", "18:00")
    monkeypatch.setenv("MEAL2_START", "18:00")
    monkeypatch.setenv("MEAL2_END", "24:00")

    # Reload config/db/app so the new env + fresh engine take effect.
    import app.config as config
    importlib.reload(config)
    config.get_settings.cache_clear()
    settings = config.get_settings()

    import app.db as db
    importlib.reload(db)
    import app.security as security
    importlib.reload(security)
    import app.scan_service as scan_service
    importlib.reload(scan_service)
    import app.seed as seed
    importlib.reload(seed)
    import app.tunnel_gate as tunnel_gate
    importlib.reload(tunnel_gate)
    import app.importer as importer
    importlib.reload(importer)
    import app.reports as reports
    importlib.reload(reports)
    import app.backup as backup
    importlib.reload(backup)
    # Isolate the GitHub backup config per test (never touch the real file).
    backup.GH_CONFIG_PATH = __import__("pathlib").Path(tmpdir) / "backup-config.json"
    import app.app_config as app_config
    importlib.reload(app_config)
    # Isolate runtime settings per test.
    app_config.APP_CONFIG_PATH = __import__("pathlib").Path(tmpdir) / "app-config.json"
    # Routers import the reloaded modules.
    import app.routers.scan, app.routers.auth, app.routers.people, app.routers.reports, app.routers.update, app.routers.backup, app.routers.settings  # noqa
    importlib.reload(app.routers.scan)
    importlib.reload(app.routers.auth)
    importlib.reload(app.routers.people)
    importlib.reload(app.routers.reports)
    importlib.reload(app.routers.update)
    importlib.reload(app.routers.backup)
    importlib.reload(app.routers.settings)
    import app.main as main
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        yield {
            "client": client,
            "settings": settings,
            "db": db,
            "seed": seed,
            "importer": importer,
            "reports": reports,
            "backup": backup,
            "app_config": app_config,
            "scan_service": scan_service,
            "headers": {"x-tunnel-secret": settings.tunnel_secret},
            "admin_user": ADMIN_USER,
            "admin_pass": ADMIN_PASS,
        }

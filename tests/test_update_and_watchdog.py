"""Update-application and watchdog behaviour.

These cover the two ways the kiosk can be left stranded with no remote fix:
  * an update that crashes partway through, and
  * an app that is simply not running after a failed restart / crash.
Both previously required somebody to physically walk to the kiosk PC.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _fake_repo_zip(tmp_path: Path) -> bytes:
    """Build a ZIP shaped like GitHub's archive of this repo."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        top = "cocacolalunchFMG-main"
        zf.writestr(f"{top}/app/__init__.py", '__version__ = "9.9.9"\n')
        zf.writestr(f"{top}/static/kiosk.js", "// new kiosk\n")
        zf.writestr(f"{top}/scripts/helper.py", "# helper\n")
        zf.writestr(f"{top}/tests/conftest.py", "# test config\n")
        zf.writestr(f"{top}/run.py", "# runner\n")
        zf.writestr(f"{top}/requirements.txt", "fastapi\n")
        zf.writestr(f"{top}/start.bat", "@echo off\n")
        # A .bat added AFTER the kiosk was installed — the case that broke.
        zf.writestr(f"{top}/install-autostart.bat", "@echo autostart\n")
        zf.writestr(f"{top}/brand-new-tool.bat", "@echo new\n")
    return buf.getvalue()


def _install_apply_update(monkeypatch, root: Path, zip_bytes: bytes):
    """Load apply_update pointed at `root`, with the download stubbed out."""
    import scripts.apply_update as au

    importlib.reload(au)
    monkeypatch.setattr(au, "ROOT", root)
    monkeypatch.setattr(au, "_download", lambda url: zip_bytes)
    return au


def test_update_succeeds_when_tests_dir_is_missing(tmp_path, monkeypatch):
    """An install without a tests/ folder must still update cleanly.

    apply_update copies test files into tests/; if that folder does not exist
    the copy used to raise FileNotFoundError and abort the whole update, which
    on the kiosk means a half-applied update and no way to retry remotely.
    """
    root = tmp_path / "install"
    (root / "app").mkdir(parents=True)
    (root / "static").mkdir()
    (root / "scripts").mkdir()
    (root / "app" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    # deliberately NO tests/ directory

    au = _install_apply_update(monkeypatch, root, _fake_repo_zip(tmp_path))
    assert au.main() == 0

    assert (root / "tests").is_dir()                      # created, not crashed
    assert (root / "tests" / "conftest.py").exists()
    assert '9.9.9' in (root / "app" / "__init__.py").read_text()


def test_update_preserves_local_data_and_secrets(tmp_path, monkeypatch):
    """.env, the database and runtime settings must survive an update."""
    root = tmp_path / "install"
    for d in ("app", "static", "scripts", "tests"):
        (root / d).mkdir(parents=True)
    (root / "app" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    (root / ".env").write_text("ADMIN_PASSWORD=RealSecret\n")
    (root / "lunch.db").write_bytes(b"SQLITE-DATA")
    (root / ".app-config.json").write_text('{"daily_limit": 4}')

    au = _install_apply_update(monkeypatch, root, _fake_repo_zip(tmp_path))
    assert au.main() == 0

    assert (root / ".env").read_text() == "ADMIN_PASSWORD=RealSecret\n"
    assert (root / "lunch.db").read_bytes() == b"SQLITE-DATA"
    assert (root / ".app-config.json").read_text() == '{"daily_limit": 4}'
    # ...and the new code did land
    assert '9.9.9' in (root / "app" / "__init__.py").read_text()


def test_update_delivers_newly_added_bat_files(tmp_path, monkeypatch):
    """A .bat added to the repo later must actually reach the kiosk.

    COPY_FILES was a hardcoded list, so a newly shipped script silently never
    got copied: the operator was told to run install-autostart.bat and did not
    have the file. Any *.bat in the repo is picked up now.
    """
    root = tmp_path / "install"
    for d in ("app", "static", "scripts", "tests"):
        (root / d).mkdir(parents=True)
    (root / "app" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    (root / "start.bat").write_text("@echo old\n")
    # The kiosk does NOT have these yet — they were added after it was set up.
    assert not (root / "install-autostart.bat").exists()
    assert not (root / "brand-new-tool.bat").exists()

    au = _install_apply_update(monkeypatch, root, _fake_repo_zip(tmp_path))
    assert au.main() == 0

    assert (root / "install-autostart.bat").exists(), "new .bat never delivered"
    assert (root / "brand-new-tool.bat").exists(), "unlisted .bat never delivered"
    assert "autostart" in (root / "install-autostart.bat").read_text()
    # existing scripts still updated
    assert "@echo off" in (root / "start.bat").read_text()


def test_update_snapshots_rollback_before_overwriting(tmp_path, monkeypatch):
    """The pre-update code is snapshotted so a bad push can be undone."""
    root = tmp_path / "install"
    for d in ("app", "static", "scripts", "tests"):
        (root / d).mkdir(parents=True)
    (root / "app" / "__init__.py").write_text('__version__ = "1.0.0"\n')

    au = _install_apply_update(monkeypatch, root, _fake_repo_zip(tmp_path))
    assert au.main() == 0

    snapshot = root / ".rollback" / "app" / "__init__.py"
    assert snapshot.exists()
    assert '1.0.0' in snapshot.read_text()   # the OLD version was preserved


# ------------------------------- watchdog ---------------------------------- #
def _load_watchdog(monkeypatch, root: Path):
    import scripts.watchdog as wd

    importlib.reload(wd)
    monkeypatch.setattr(wd, "ROOT", root)
    monkeypatch.setattr(wd, "LOG", root / "watchdog.log")
    return wd


def test_watchdog_does_nothing_when_app_is_healthy(tmp_path, monkeypatch):
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: True)
    relaunched = {"called": False}
    monkeypatch.setattr(wd, "_relaunch",
                        lambda v: relaunched.__setitem__("called", True) or True)

    assert wd.main([]) == 0
    assert relaunched["called"] is False   # a healthy app is never touched


def test_watchdog_relaunches_a_dead_app(tmp_path, monkeypatch):
    """The failed-update case: app is down, watchdog brings it back."""
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: False)
    monkeypatch.setattr(wd, "_uptime_seconds", lambda: 10_000.0)  # long since boot
    calls = {"n": 0}

    def fake_relaunch(verbose):
        calls["n"] += 1
        return True

    monkeypatch.setattr(wd, "_relaunch", fake_relaunch)
    monkeypatch.setattr(wd, "_wait_healthy", lambda port, seconds: True)

    assert wd.main([]) == 0
    assert calls["n"] == 1


def test_watchdog_waits_during_boot_grace(tmp_path, monkeypatch):
    """Right after power-on the logon task is still starting things.

    Launching a second copy on top of that would fight the logon task, so the
    watchdog stands down until the machine has been up a while.
    """
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: False)
    monkeypatch.setattr(wd, "_uptime_seconds", lambda: 5.0)   # just booted
    relaunched = {"called": False}
    monkeypatch.setattr(wd, "_relaunch",
                        lambda v: relaunched.__setitem__("called", True) or True)

    assert wd.main([]) == 0
    assert relaunched["called"] is False


def test_watchdog_reports_failure_when_revive_does_not_work(tmp_path, monkeypatch):
    """If the app cannot be revived the task must exit non-zero, not pretend."""
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: False)
    monkeypatch.setattr(wd, "_uptime_seconds", lambda: 10_000.0)
    monkeypatch.setattr(wd, "_relaunch", lambda v: True)
    monkeypatch.setattr(wd, "_wait_healthy", lambda port, seconds: False)

    assert wd.main([]) == 1


def test_watchdog_relaunch_never_opens_a_browser_tab(tmp_path, monkeypatch):
    """Reviving the app must not spawn another kiosk tab.

    quick-start.bat opens the kiosk page, so the watchdog calling it plainly
    gave the operator a second (and third...) tab every time it ran. It must
    pass /nobrowser, and /noupdate so a revive is immediate.
    """
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    (root / "quick-start.bat").write_text("@echo off\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd.os, "name", "nt")   # exercise the Windows branch
    captured = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd

    monkeypatch.setattr(wd.subprocess, "Popen", FakePopen)
    assert wd._relaunch(False) is True

    cmd = captured["cmd"]
    assert "/nobrowser" in cmd, f"watchdog would open a browser tab: {cmd}"
    assert "/noupdate" in cmd, f"watchdog would stall on a download: {cmd}"


def test_watchdog_clears_duplicate_ngrok_agents(tmp_path, monkeypatch):
    """Two ngrok agents on the free plan = no remote access at all.

    The plan allows ONE agent; a second is refused with ERR_NGROK_108, so a
    survivor from a crash silently breaks the tunnel while the app itself
    looks perfectly healthy. Nothing else in the system would notice.
    """
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: True)
    monkeypatch.setattr(wd, "_ngrok_agent_count", lambda: 2)
    killed = {"n": 0}
    relaunched = {"n": 0}
    monkeypatch.setattr(wd, "_kill_stray_ngrok",
                        lambda v: killed.__setitem__("n", killed["n"] + 1))
    monkeypatch.setattr(wd, "_relaunch",
                        lambda v: relaunched.__setitem__("n", relaunched["n"] + 1) or True)
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)

    assert wd.main([]) == 0
    assert killed["n"] == 1, "duplicate agents were not cleared"
    assert relaunched["n"] == 1, "tunnel was not restarted after clearing"


def test_watchdog_leaves_a_single_ngrok_agent_alone(tmp_path, monkeypatch):
    """One agent is the correct state — do not restart a working tunnel."""
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: True)
    monkeypatch.setattr(wd, "_ngrok_agent_count", lambda: 1)
    killed = {"n": 0}
    monkeypatch.setattr(wd, "_kill_stray_ngrok",
                        lambda v: killed.__setitem__("n", killed["n"] + 1))
    monkeypatch.setattr(wd, "_relaunch", lambda v: True)

    assert wd.main([]) == 0
    assert killed["n"] == 0, "a healthy single tunnel must not be disturbed"


def test_watchdog_clears_ngrok_before_reviving_a_dead_app(tmp_path, monkeypatch):
    """A survivor from the dead instance would hold the single free slot."""
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("PORT=8000\n")
    wd = _load_watchdog(monkeypatch, root)

    monkeypatch.setattr(wd, "_healthy", lambda port, timeout=3.0: False)
    monkeypatch.setattr(wd, "_uptime_seconds", lambda: 10_000.0)
    order = []
    monkeypatch.setattr(wd, "_kill_stray_ngrok", lambda v: order.append("kill"))
    monkeypatch.setattr(wd, "_relaunch",
                        lambda v: order.append("relaunch") or True)
    monkeypatch.setattr(wd, "_wait_healthy", lambda port, seconds: True)

    assert wd.main([]) == 0
    assert order == ["kill", "relaunch"], f"wrong order: {order}"


def test_watchdog_reads_port_from_env_file(tmp_path, monkeypatch):
    """The port must come from .env without importing the (possibly broken) app."""
    root = tmp_path / "install"
    root.mkdir()
    (root / ".env").write_text("# comment\nPORT=9123\nOTHER=x\n")
    wd = _load_watchdog(monkeypatch, root)
    assert wd._port() == 9123


def test_watchdog_port_falls_back_when_env_unreadable(tmp_path, monkeypatch):
    root = tmp_path / "install"
    root.mkdir()   # no .env at all
    wd = _load_watchdog(monkeypatch, root)
    assert wd._port() == 8000


# --------------------- schema migration without a restart ------------------- #
def test_migration_adds_new_tables_to_an_old_database(tmp_path, monkeypatch):
    """An update that adds a table must not need a restart.

    init_db() only runs at startup, so "update without restart" used to leave
    the new code on disk with no table to write to — the feature came up empty
    until somebody restarted. scripts/migrate_db.py closes that gap.
    """
    import sqlite3
    import subprocess

    db = tmp_path / "lunch.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE people (id INTEGER PRIMARY KEY, card_id VARCHAR UNIQUE NOT NULL,
          full_name VARCHAR, department VARCHAR, active BOOLEAN,
          daily_limit INTEGER NOT NULL DEFAULT 1, created_at DATETIME);
        CREATE TABLE scans (id INTEGER PRIMARY KEY,
          person_id INTEGER NOT NULL REFERENCES people(id), card_id VARCHAR NOT NULL,
          scanned_at DATETIME NOT NULL, local_date DATE NOT NULL);
        CREATE TABLE admins (id INTEGER PRIMARY KEY, username VARCHAR UNIQUE NOT NULL,
          password_hash VARCHAR NOT NULL);
        INSERT INTO people (card_id, full_name, active, daily_limit)
          VALUES ('3377269862','----',1,1);
        INSERT INTO scans (person_id, card_id, scanned_at, local_date)
          VALUES (1,'3377269862','2026-08-10 10:00:00','2026-08-10');
        """
    )
    con.commit()
    con.close()

    import os
    env = dict(
        os.environ, DB_PATH=str(db), TIMEZONE="Asia/Tbilisi", ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="StrongTestPass!2026", SECRET_KEY="x" * 48,
        TUNNEL_SECRET="t" * 32, HOST="127.0.0.1", PORT="8000",
    )
    py = sys.executable
    r = subprocess.run([py, str(ROOT / "scripts" / "migrate_db.py")],
                       cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(db)
    try:
        tables = {t[0] for t in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "tap_log" in tables and "roster" in tables
        # existing data untouched
        assert con.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == 1
    finally:
        con.close()

    # ...and running it again changes nothing
    r2 = subprocess.run([py, str(ROOT / "scripts" / "migrate_db.py")],
                        cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert r2.returncode == 0
    assert "already current" in r2.stdout


def test_update_endpoint_migrates_even_without_restart(app_ctx, monkeypatch):
    """POST /api/update?restart=false must still apply the new schema."""
    import app.routers.update as upd

    calls = []

    class _OK:
        returncode = 0
        stdout = "[update] applied 5 files\n"
        stderr = ""

    def fake_run(cmd, *a, **k):
        calls.append(str(cmd[-1]))
        return _OK()

    monkeypatch.setattr(upd.subprocess, "run", fake_run)
    ctx = app_ctx
    c = ctx["client"]
    H = ctx["headers"]
    c.post("/api/login", headers=H,
           json={"username": ctx["admin_user"], "password": ctx["admin_pass"]})

    j = c.post("/api/update?restart=false", headers=H).json()

    assert j["ok"] is True
    assert j["restarting"] is False
    assert j["migrated"] is True, "schema was not applied on the no-restart path"
    assert any("migrate_db.py" in call for call in calls), calls


def test_update_fails_loudly_when_nothing_was_copied(tmp_path, monkeypatch):
    """An update that copies nothing must NOT report success.

    apply_update exited 0 regardless, so a pull that silently changed nothing
    showed "updated" in admin while the version never moved — leaving the
    operator with a success message and no way to tell what went wrong.
    """
    import io
    import zipfile

    root = tmp_path / "install"
    root.mkdir()
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text('__version__ = "1.0.0"\n')

    # A zip whose top folder holds none of the paths we copy.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cocacolalunchFMG-main/UNRELATED.txt", "nothing to copy\n")

    au = _install_apply_update(monkeypatch, root, buf.getvalue())
    assert au.main() == 1, "reported success despite copying nothing"


def test_update_reports_the_version_that_landed(tmp_path, monkeypatch):
    """The operator needs to see the version actually written to disk."""
    root = tmp_path / "install"
    for d in ("app", "static", "scripts", "tests"):
        (root / d).mkdir(parents=True)
    (root / "app" / "__init__.py").write_text('__version__ = "1.0.0"\n')

    au = _install_apply_update(monkeypatch, root, _fake_repo_zip(tmp_path))
    assert au.main() == 0
    # _fake_repo_zip ships 9.9.9; the check reads it back off disk, not from
    # the version this process imported at boot.
    assert au._version_on_disk() == "9.9.9"

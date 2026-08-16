"""Remote update API. Gated (admin login + tunnel secret).

POST /api/update  ->  pull latest code from the configured GitHub repo,
                      then schedule a detached self-restart of app+proxy+tunnel.

This is the ONLY way to update the kiosk without physical access: the operator
clicks "Update from GitHub" in the admin panel (over the tunnel), the kiosk
fetches the new code, applies it (preserving .env / lunch.db / backups), and
restarts itself a few seconds later.

Security: behind get_current_admin AND the tunnel-secret gate, so only the
remote operator can trigger it. It runs whatever is on the repo's branch, so
keep the GitHub account + admin password secure.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends

from ..security import get_current_admin

router = APIRouter(prefix="/api/update", tags=["update"],
                   dependencies=[Depends(get_current_admin)])

ROOT = Path(__file__).resolve().parent.parent.parent


def _python() -> str:
    venv = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    return str(venv) if venv.exists() else sys.executable


@router.get("/status")
def update_status() -> dict:
    """Report the current version + configured repo so admin can show it."""
    from .. import __version__
    repo = os.environ.get("GITHUB_REPO", "SabaZara/cocacolalunchFMG")
    return {"version": __version__, "repo": repo}


@router.post("")
def run_update(restart: bool = True) -> dict:
    """Pull latest code; if restart=True, schedule a detached app restart."""
    py = _python()

    # 1) apply the update synchronously, capture output
    proc = subprocess.run(
        [py, str(ROOT / "scripts" / "apply_update.py")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0

    from .. import __version__  # may be stale until restart; report pre-restart

    # What version actually landed on disk. Read from the file rather than
    # imported, because THIS process is still running the old code — an update
    # that quietly changed nothing would otherwise report the old version as
    # if it were the new one.
    def _disk_version() -> str:
        try:
            text = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.strip().startswith("__version__"):
                    return line.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            pass
        return ""

    on_disk = _disk_version()
    result = {
        "ok": ok,
        "applied": ok,
        "output": output.strip(),
        "version_before_restart": __version__,
        "version_on_disk": on_disk,
        # True when the download really moved us to different code. If this is
        # False after a "successful" update, the pull did nothing.
        "version_changed": bool(on_disk and on_disk != __version__),
        "restarting": False,
    }
    if not ok:
        return result

    # 2) apply any schema the NEW code expects, in a separate process so it
    #    imports the just-downloaded models rather than the ones this process
    #    loaded at boot. Without this an update that adds a table needed a
    #    restart: the new page would come up empty because its table did not
    #    exist yet. Only ever adds; safe while the kiosk keeps scanning.
    try:
        mig = subprocess.run(
            [py, str(ROOT / "scripts" / "migrate_db.py")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        result["migrated"] = mig.returncode == 0
        result["migrate_output"] = ((mig.stdout or "") + (mig.stderr or "")).strip()
    except Exception as exc:  # noqa: BLE001
        # A migration failure must not lose the code we just applied; the
        # restart path (or the next startup) will run init_db anyway.
        result["migrated"] = False
        result["migrate_output"] = f"migration skipped: {exc}"

    # 3) schedule the detached self-restart (so this response can flush first)
    if restart:
        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            start_new_session = True
        subprocess.Popen(
            [py, str(ROOT / "scripts" / "self_restart.py")],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
        result["restarting"] = True

    return result

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

    result = {
        "ok": ok,
        "applied": ok,
        "output": output.strip(),
        "version_before_restart": __version__,
        "restarting": False,
    }
    if not ok:
        return result

    # 2) schedule the detached self-restart (so this response can flush first)
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

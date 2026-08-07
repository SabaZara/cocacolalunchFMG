"""Keep the kiosk alive: if the app is not answering, relaunch it.

Registered by install-autostart.bat as a Windows Scheduled Task that runs every
few minutes. It exists because a remote update (or a crash, or a bad shutdown)
can leave the app dead with no way to fix it remotely — the thing that would
restart the app IS the app. This runs outside the app, so it always can.

What it does, in order:
  1. GET http://127.0.0.1:<PORT>/healthz
  2. if that answers 200 -> nothing to do, exit 0
  3. otherwise -> run quick-start.bat (which relaunches app + proxy + tunnel)
  4. wait for /healthz to come back and report the outcome

Deliberately NOT done here:
  * never stops or closes anything (shutdown stays the operator's choice);
  * never touches the database, .env, or any local data;
  * never updates code — that is apply_update.py's job.

Stdlib only. Runs on Windows (the kiosk) and POSIX (so it is testable here).
Exit codes: 0 = app is up (or was revived), 1 = could not revive it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "watchdog.log"

# Give a laptop that just booted time to get going before declaring it dead.
BOOT_GRACE_SECONDS = 90


def _log(msg: str, verbose: bool = False) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    if verbose:
        print(line)
    try:
        # Keep the log from growing without bound (roughly the last ~500 lines).
        if LOG.exists() and LOG.stat().st_size > 200_000:
            tail = LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]
            LOG.write_text("\n".join(tail) + "\n", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _port() -> int:
    """Read PORT from .env without importing the app (which may be broken)."""
    try:
        for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw.startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            if key.strip() == "PORT":
                return int(value.strip())
    except (OSError, ValueError):
        pass
    return 8000


def _healthy(port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=timeout
        ) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _wait_healthy(port: int, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _healthy(port):
            return True
        time.sleep(2)
    return False


def _uptime_seconds() -> float:
    """Seconds since boot, so we don't fight a machine that is still starting."""
    try:
        if os.name == "nt":
            import ctypes
            return ctypes.windll.kernel32.GetTickCount64() / 1000.0
        return time.time() - psutil_boot()  # pragma: no cover - POSIX fallback
    except Exception:  # noqa: BLE001
        return float("inf")  # unknown -> assume long up, don't skip the check


def psutil_boot() -> float:  # pragma: no cover - only used on POSIX
    """Boot time without a psutil dependency (best effort)."""
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime"):
                    return float(line.split()[1])
    except OSError:
        pass
    return 0.0


def _relaunch(verbose: bool) -> bool:
    """Run quick-start.bat (Windows) to bring app + proxy + tunnel back."""
    starter = ROOT / "quick-start.bat"
    if os.name == "nt":
        if not starter.exists():
            _log("[watchdog] quick-start.bat missing; cannot relaunch.", verbose)
            return False
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", "/min", str(starter)],
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except OSError as exc:
            _log(f"[watchdog] relaunch failed: {exc}", verbose)
            return False

    # POSIX (this Mac): start the app directly so the watchdog is testable.
    venv = ROOT / ".venv/bin/python"
    py = str(venv) if venv.exists() else sys.executable
    try:
        subprocess.Popen(
            [py, str(ROOT / "run.py")],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError as exc:
        _log(f"[watchdog] relaunch failed: {exc}", verbose)
        return False


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args

    port = _port()

    if _healthy(port):
        _log(f"[watchdog] app healthy on port {port}.", verbose)
        return 0

    # A machine that just booted may simply not be up yet — the logon task is
    # probably still starting things. Don't pile a second launch on top.
    up = _uptime_seconds()
    if up < BOOT_GRACE_SECONDS:
        _log(f"[watchdog] app not up yet, but only {int(up)}s since boot — waiting.",
             verbose)
        return 0

    _log(f"[watchdog] app NOT responding on port {port} — relaunching…", verbose)
    if not _relaunch(verbose):
        return 1

    if _wait_healthy(port, seconds=45):
        _log("[watchdog] app is back up.", verbose)
        return 0

    _log("[watchdog] relaunch did not bring the app back within 45s.", verbose)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

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


def _prune_logs(verbose: bool) -> None:
    """Keep the app's own log files from growing without bound.

    These are append-only and the kiosk runs for months, so app.log / proxy.log
    / tunnel.log quietly become the biggest files on the machine. Trim each to
    its newest ~2000 lines rather than deleting, so a recent crash is still
    diagnosable.
    """
    LOG_MAX_BYTES = 5_000_000       # ~5 MB before trimming
    LOG_KEEP_LINES = 2000
    for name in ("app.log", "proxy.log", "tunnel.log", "update-rollback.log"):
        p = ROOT / name
        try:
            if not p.exists() or p.stat().st_size <= LOG_MAX_BYTES:
                continue
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            p.write_text("\n".join(lines[-LOG_KEEP_LINES:]) + "\n", encoding="utf-8")
            _log(f"[watchdog] trimmed {name} (was over 5 MB).", verbose)
        except OSError:
            pass


def _free_disk_mb() -> float:
    """Free space on the drive holding the install. -1 if unknown."""
    try:
        import shutil as _sh
        return _sh.disk_usage(str(ROOT)).free / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return -1.0


def _check_disk(verbose: bool) -> None:
    """Warn loudly in the log when the disk is nearly full.

    SQLite cannot write when the disk fills, so scans would start failing at
    the reader. Browser caches and Windows updates are the usual culprits on a
    small kiosk laptop, and nobody is watching the machine day to day.
    """
    free = _free_disk_mb()
    if free < 0:
        return
    if free < 500:
        _log(f"[watchdog] WARNING: only {free:.0f} MB free — the database may "
             f"stop accepting scans. Clear browser cache / temp files.", True)
    elif free < 1500:
        _log(f"[watchdog] note: {free:.0f} MB free on the kiosk drive.", verbose)


def _ngrok_agent_count() -> int:
    """How many ngrok agents are running locally.

    The free plan allows exactly ONE. Two agents means the newer one is being
    refused (ERR_NGROK_108) and remote access is broken, so this is worth
    detecting rather than silently living with a dead tunnel.
    Returns -1 when it cannot be determined.
    """
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq ngrok.exe", "/NH"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            return sum(1 for line in out.splitlines() if "ngrok.exe" in line.lower())
        out = subprocess.run(["pgrep", "-f", "ngrok"],
                             capture_output=True, text=True, timeout=15).stdout
        return len([line for line in out.splitlines() if line.strip()])
    except (OSError, subprocess.SubprocessError):
        return -1


def _kill_stray_ngrok(verbose: bool) -> None:
    """Leave at most zero agents running, so the next start gets the slot."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/IM", "ngrok.exe", "/T", "/F"],
                           capture_output=True, timeout=20)
        else:
            subprocess.run(["pkill", "-f", "ngrok"], capture_output=True, timeout=20)
        _log("[watchdog] cleared stray ngrok agent(s).", verbose)
    except (OSError, subprocess.SubprocessError):
        pass


def _relaunch(verbose: bool) -> bool:
    """Run quick-start.bat (Windows) to bring app + proxy + tunnel back."""
    starter = ROOT / "quick-start.bat"
    if os.name == "nt":
        if not starter.exists():
            _log("[watchdog] quick-start.bat missing; cannot relaunch.", verbose)
            return False
        try:
            # /nobrowser: reviving a dead app must never spawn another kiosk
            # tab — that is how the operator ended up with duplicates.
            # /noupdate: come back NOW; a GitHub pull would delay the revive.
            subprocess.Popen(
                ["cmd", "/c", "start", "", "/min", str(starter),
                 "/nobrowser", "/noupdate"],
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

    # Housekeeping every pass: cheap, and it is the only thing that runs
    # regularly on an unattended kiosk.
    _prune_logs(verbose)
    _check_disk(verbose)

    if _healthy(port):
        # The app is fine — but a duplicate ngrok agent still breaks remote
        # access on the free plan, and nothing else would ever notice.
        agents = _ngrok_agent_count()
        if agents > 1:
            _log(f"[watchdog] {agents} ngrok agents running — the free plan "
                 f"allows ONE, so the extra ones are being refused "
                 f"(ERR_NGROK_108). Clearing and restarting the tunnel.", verbose)
            _kill_stray_ngrok(verbose)
            time.sleep(2)
            _relaunch(verbose)   # /nobrowser /noupdate: brings the tunnel back
            return 0
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
    # quick-start starts a fresh tunnel; a survivor from the dead instance
    # would take the single free-plan slot and refuse the new one.
    _kill_stray_ngrok(verbose)
    if not _relaunch(verbose):
        return 1

    if _wait_healthy(port, seconds=45):
        _log("[watchdog] app is back up.", verbose)
        return 0

    _log("[watchdog] relaunch did not bring the app back within 45s.", verbose)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

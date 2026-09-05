"""Restart the LUNCH app + proxy + tunnel from OUTSIDE the app process.

The running app can't cleanly kill and relaunch itself in one request, so the
/api/update endpoint spawns THIS script detached. It:
  1. waits a few seconds (so the HTTP response to the admin browser flushes),
  2. kills the current app/proxy/tunnel (PIDs in lunch-pids.txt),
  3. relaunches them via start_hidden.py (app + proxy + ngrok if configured).

Stdlib only. Windows + POSIX compatible (used on the kiosk; testable on mac).

Args: none. Reads PORT/PROXY_PORT/NGROK_* from .env via read_env-style parse.
"""
from __future__ import annotations

import os
import json
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PIDS = ROOT / "lunch-pids.txt"
VENV_PY = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
PYEXE = str(VENV_PY) if VENV_PY.exists() else sys.executable
IS_WINDOWS = os.name == "nt"


def _port_from_env(default: int = 8000) -> int:
    """Read PORT straight from .env, WITHOUT importing app code.

    Importing the app here is how a restart could die before starting
    anything: if the freshly-updated code has an import error, _settings()
    raises, this script exits, and nothing is ever launched — the app stays
    down with no rollback attempted. Parsing the file cannot fail that way.
    """
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
    return default


def _settings():
    from app.config import get_settings
    return get_settings()


def _kill_stray_ngrok() -> None:
    """Kill ANY ngrok agent, recorded or not.

    The free ngrok plan permits exactly ONE agent per account. A survivor from
    a crash, a hard power-off, or a deleted/stale pid file makes the new agent
    fail with ERR_NGROK_108 — and remote access is then gone entirely, which
    cannot be fixed remotely. The pid file is not trustworthy on its own, so
    sweep by process name too.
    """
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/IM", "ngrok.exe", "/F"],
                           capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
    except OSError:
        pass


def _listener_pids(ports: set[int]) -> set[int]:
    """Actual Windows listeners, including Python children of venv launchers."""
    if not IS_WINDOWS:
        return set()
    try:
        result = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                capture_output=True, text=True, timeout=10)
        found = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) != 5 or parts[0] != "TCP" or parts[3] != "LISTENING":
                continue
            host, _, port = parts[1].rpartition(":")
            if host not in {"127.0.0.1", "0.0.0.0", "[::]", "[::1]"}:
                continue
            if port.isdigit() and int(port) in ports and parts[4].isdigit():
                found.add(int(parts[4]))
        return found
    except (OSError, subprocess.TimeoutExpired):
        return set()


def _kill_old() -> None:
    port = _port_from_env()
    # Stop the actual service listeners as well as launcher PIDs. A missing or
    # stale PID file must not leave the old Python serving the same port.
    pids = _listener_pids({port, port + 1})
    if PIDS.exists():
        for line in PIDS.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                pids.add(int(parts[1]))
    for pid in sorted(pids):
        if pid <= 0 or pid == os.getpid():
            continue
        try:
            if IS_WINDOWS:
                # NO /T: the running app spawned THIS helper. Killing its
                # process tree also kills the helper before it can relaunch.
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=10)
            else:
                os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
            pass
    if PIDS.exists():
        try:
            PIDS.unlink()
        except OSError:
            pass

    # Always sweep ngrok, even when the pid file was missing or incomplete.
    _kill_stray_ngrok()
    # Let the old agent's session drop server-side before starting a new one.
    time.sleep(2)


def _spawn(label: str, cmd: list[str], env: dict | None = None) -> None:
    full = [PYEXE, str(ROOT / "scripts" / "start_hidden.py"),
            "--label", label, "--log", f"{label}.log",
            "--pid-file", str(PIDS), "--"] + cmd
    extra = os.environ.copy()
    if env:
        extra.update(env)
    subprocess.run(full, cwd=str(ROOT), env=extra)


def _healthy(port: int, seconds: float = 30.0, expected_version: str = "",
             expected_instance: str = "") -> bool:
    """Verify the newly launched process, not merely any surviving old app."""
    import urllib.request
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=2
            ) as r:
                if r.status != 200:
                    continue
            if expected_version or expected_instance:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=2) as r:
                    info = json.load(r)
                if expected_version and info.get("version") != expected_version:
                    time.sleep(1)
                    continue
                if expected_instance and info.get("instance_id") != expected_instance:
                    time.sleep(1)
                    continue
            return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return False


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    try:
        with (ROOT / "update-rollback.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main() -> int:
    _log("[self_restart] restart helper started")
    # Let the HTTP response to the admin browser flush first.
    time.sleep(4)
    _kill_old()
    time.sleep(1)

    # NOTE: never import app code here. If the update we just applied has a
    # syntax/import error, importing it would kill this script and nothing
    # would be started OR rolled back — the kiosk would simply stay dead.
    app_port = _port_from_env()
    proxy_port = app_port + 1

    # app
    instance = uuid.uuid4().hex
    _spawn("app", [PYEXE, str(ROOT / "run.py")], env={"LUNCH_INSTANCE_ID": instance})
    # proxy
    _spawn("proxy", [PYEXE, str(ROOT / "tunnel_proxy.py")],
           env={"PROXY_PORT": str(proxy_port)})

    # tunnel (only if ngrok present + configured)
    ngrok = ROOT / ("ngrok.exe" if os.name == "nt" else "ngrok")
    domain = (os.environ.get("NGROK_DOMAIN") or "").strip()
    token = (os.environ.get("NGROK_AUTHTOKEN") or "").strip()
    # pull domain/token from .env if not in env
    if not domain or not token:
        try:
            for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
                if "=" in raw and not raw.strip().startswith("#"):
                    k, _, v = raw.partition("=")
                    k = k.strip(); v = v.strip()
                    if k == "NGROK_DOMAIN" and not domain:
                        domain = v
                    elif k == "NGROK_AUTHTOKEN" and not token:
                        token = v
        except OSError:
            pass
    for scheme in ("https://", "http://"):
        if domain.startswith(scheme):
            domain = domain[len(scheme):]
    domain = domain.rstrip("/")

    if ngrok.exists() and domain and token:
        try:
            subprocess.run([str(ngrok), "config", "add-authtoken", token],
                           capture_output=True, cwd=str(ROOT))
        except OSError:
            pass
        _spawn("tunnel", [str(ngrok), "http", "--url", domain,
                          f"http://127.0.0.1:{proxy_port}"])

    _log("[self_restart] relaunched app + proxy" +
         (" + tunnel" if (ngrok.exists() and domain and token) else ""))

    # ---- auto-rollback safety net -----------------------------------------
    # If the (possibly just-updated) app does not become healthy, restore the
    # pre-update code from .rollback/ and relaunch it, so a bad update can
    # never strand the kiosk.
    if _healthy(app_port, seconds=30, expected_instance=instance):
        _log("[self_restart] app healthy.")
        return 0

    rollback = ROOT / ".rollback"
    if not rollback.exists():
        _log("[self_restart] app NOT healthy and no .rollback snapshot exists.")
        return 1

    _log("[self_restart] app NOT healthy — rolling back to previous code ...")
    try:
        # Self-contained restore (no import of possibly-broken updated code).
        import shutil
        restored = 0
        for item in rollback.rglob("*"):
            rel = item.relative_to(rollback)
            target = ROOT / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                restored += 1
        _log(f"[self_restart] restored {restored} files from .rollback/")
    except Exception as exc:  # noqa: BLE001
        _log(f"[self_restart] rollback restore failed: {exc}")
        return 1

    _kill_old()
    time.sleep(1)
    _spawn("app", [PYEXE, str(ROOT / "run.py")])
    _spawn("proxy", [PYEXE, str(ROOT / "tunnel_proxy.py")],
           env={"PROXY_PORT": str(proxy_port)})
    if ngrok.exists() and domain and token:
        _spawn("tunnel", [str(ngrok), "http", "--url", domain,
                          f"http://127.0.0.1:{proxy_port}"])

    if _healthy(app_port, seconds=30):
        _log("[self_restart] ROLLED BACK successfully — previous version is running.")
        return 0
    _log("[self_restart] rollback relaunch still unhealthy — manual attention needed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

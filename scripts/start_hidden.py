"""Start a background process hidden on Windows, with logs and PID tracking.

Used by start.bat so the app, proxy, and tunnel run quietly in the background
instead of opening extra console windows. Stdlib only.

Usage:
  python scripts/start_hidden.py --label app --log app.log --pid-file lunch-pids.txt -- python run.py
  python scripts/start_hidden.py --label proxy --env PROXY_PORT=8001 --log proxy.log -- python tunnel_proxy.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--pid-file", default="lunch-pids.txt")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command after --")
    return args


def main() -> int:
    args = _parse_args()
    env = os.environ.copy()
    for item in args.env:
        if "=" not in item:
            print(f"[start_hidden] bad --env value: {item}", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        env[key] = value

    log_path = ROOT / args.log
    log = log_path.open("ab")

    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        # CREATE_NO_WINDOW hides the console. Do NOT also pass DETACHED_PROCESS:
        # the two are mutually exclusive and CreateProcess fails with
        # ERROR_INVALID_PARAMETER (87) if both are set. CREATE_NEW_PROCESS_GROUP
        # is compatible and lets stop.bat kill the whole tree.
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        start_new_session = True

    try:
        proc = subprocess.Popen(
            args.command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
    except OSError as exc:
        # Surface the real reason into the log so start.bat's "type app.log" shows it.
        msg = f"[start_hidden] FAILED to launch {args.label}: {exc}\n"
        log.write(msg.encode("utf-8", "replace"))
        log.flush()
        print(msg, file=sys.stderr)
        return 1

    pid_file = ROOT / args.pid_file
    with pid_file.open("a", encoding="ascii") as f:
        f.write(f"{args.label} {proc.pid} {' '.join(args.command)}\n")

    print(f"[start_hidden] {args.label} started (pid {proc.pid}, log {args.log})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

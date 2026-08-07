"""Emit selected .env values as safe Windows `set` statements.

start.bat parses .env poorly (special chars in secrets/domains break the
parser and can silently abort the script). Instead we read .env here and print
lines that start.bat captures via:  for /f "delims=" %%i in ('... read_env.py') do %%i

Only emits the keys start.bat needs (PORT, NGROK_*), never the secrets. Strips
http(s):// and a trailing slash from NGROK_DOMAIN. Values are wrapped in
set "KEY=VALUE" so spaces/specials are tolerated.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

WANTED = ("PORT", "NGROK_AUTHTOKEN", "NGROK_DOMAIN")
DEFAULTS = {"PORT": "8000", "NGROK_AUTHTOKEN": "", "NGROK_DOMAIN": ""}


def _read() -> dict[str, str]:
    values = dict(DEFAULTS)
    if not ENV.exists():
        return values
    for raw in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key in WANTED:
            values[key] = val.strip()
    return values


def main() -> int:
    v = _read()

    # Clean the ngrok domain (no scheme, no trailing slash).
    domain = v["NGROK_DOMAIN"]
    for scheme in ("https://", "http://"):
        if domain.startswith(scheme):
            domain = domain[len(scheme):]
    domain = domain.rstrip("/")
    v["NGROK_DOMAIN"] = domain

    # PROXY_PORT = PORT + 1 (fall back to 8001 if PORT is non-numeric).
    try:
        proxy_port = int(v["PORT"]) + 1
    except ValueError:
        v["PORT"] = "8000"
        proxy_port = 8001

    print(f'set "PORT={v["PORT"]}"')
    print(f'set "PROXY_PORT={proxy_port}"')
    print(f'set "NGROK_AUTHTOKEN={v["NGROK_AUTHTOKEN"]}"')
    print(f'set "NGROK_DOMAIN={v["NGROK_DOMAIN"]}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())

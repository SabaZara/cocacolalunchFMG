"""Ensure .env has a strong SECRET_KEY and a TUNNEL_SECRET.

Called by start.bat. If either is blank/missing, generate a random value and
write it back into .env (creating .env from .env.example if needed). Does NOT
touch ADMIN_PASSWORD — the operator must set that themselves.
"""
from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def _read_lines() -> list[str]:
    if ENV.exists():
        return ENV.read_text(encoding="utf-8").splitlines()
    if EXAMPLE.exists():
        return EXAMPLE.read_text(encoding="utf-8").splitlines()
    return []


def _value_of(lines: list[str], key: str) -> str | None:
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=(.*)$")
    for ln in lines:
        m = pat.match(ln)
        if m:
            return m.group(1).strip()
    return None


def _set_value(lines: list[str], key: str, value: str) -> list[str]:
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    out = []
    found = False
    for ln in lines:
        if pat.match(ln):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    return out


def main() -> int:
    lines = _read_lines()
    changed = False

    if not _value_of(lines, "SECRET_KEY"):
        lines = _set_value(lines, "SECRET_KEY", secrets.token_urlsafe(48))
        changed = True
    if not _value_of(lines, "TUNNEL_SECRET"):
        lines = _set_value(lines, "TUNNEL_SECRET", secrets.token_hex(32))
        changed = True

    if changed or not ENV.exists():
        ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("[secrets] SECRET_KEY / TUNNEL_SECRET ensured in .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())

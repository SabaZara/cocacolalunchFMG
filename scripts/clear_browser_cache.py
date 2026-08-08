"""Delete the kiosk browser's HTTP cache (Chrome / Edge), leaving profiles alone.

WHY
---
The kiosk page is served with `Cache-Control: no-store`, so the browser should
never reuse a stale copy — but that governs correctness, not disk usage. A
laptop that runs the same page every day for months still accumulates a large
Cache/Code Cache/GPUCache directory, and a nearly full disk is a real failure
mode: SQLite cannot write, so scans start failing at the reader.

A corrupted cache is the other half. It has already happened once on this
kiosk (hence the cache-busting `?t=` in quick-start.bat): a poisoned entry made
the scan page render wrongly until someone hard-refreshed it.

WHAT IT DELETES
---------------
Only cache directories — the disk-backed copies of fetched resources, which
every browser recreates on demand:
    Cache, Code Cache, GPUCache, ShaderCache, DawnCache, Service Worker/CacheStorage

It does NOT touch history, bookmarks, cookies, saved passwords, or profiles, so
nobody is logged out of anything and no settings are lost.

Skipped entirely while the browser is running, because deleting a live cache is
how you corrupt a profile. Run it at logon BEFORE the kiosk page opens.

Stdlib only. Windows + POSIX (so it is testable off-kiosk). Never raises: this
is housekeeping and must never block the kiosk from starting.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Cache subfolders, relative to a browser profile directory.
CACHE_DIRS = [
    "Cache",
    "Code Cache",
    "GPUCache",
    "ShaderCache",
    "DawnCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "Service Worker/CacheStorage",
    "Service Worker/ScriptCache",
]

# Profile folders to sweep inside each browser's User Data directory.
PROFILE_NAMES = ["Default", "Profile 1", "Profile 2", "Profile 3", "System Profile"]


def _browser_roots() -> list[tuple[str, Path]]:
    """(process name, User Data dir) for Chrome/Edge/Brave on this machine."""
    roots: list[tuple[str, Path]] = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if not local:
            return roots
        base = Path(local)
        candidates = [
            ("chrome.exe", base / "Google/Chrome/User Data"),
            ("msedge.exe", base / "Microsoft/Edge/User Data"),
            ("brave.exe", base / "BraveSoftware/Brave-Browser/User Data"),
        ]
    else:  # pragma: no cover - dev machines only
        home = Path.home()
        candidates = [
            ("Google Chrome", home / "Library/Application Support/Google/Chrome"),
            ("Microsoft Edge", home / "Library/Application Support/Microsoft Edge"),
        ]
    for proc, path in candidates:
        if path.is_dir():
            roots.append((proc, path))
    return roots


def _is_running(process_name: str) -> bool:
    """True if the browser is running. Deleting a live cache corrupts profiles."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
                capture_output=True, text=True, timeout=20,
            ).stdout
            return process_name.lower() in out.lower()
        out = subprocess.run(["pgrep", "-f", process_name],
                             capture_output=True, text=True, timeout=20).stdout
        return bool(out.strip())
    except (OSError, subprocess.SubprocessError):
        return True  # unknown -> assume running, and skip (fail safe)


def _dir_size_mb(path: Path) -> float:
    total = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total / (1024 * 1024)


def clear_caches(verbose: bool = False) -> float:
    """Delete cache dirs for every non-running browser. Returns MB freed."""
    freed = 0.0
    for process_name, user_data in _browser_roots():
        if _is_running(process_name):
            if verbose:
                print(f"[cache] {process_name} is running — skipped (safe).")
            continue
        for profile in PROFILE_NAMES:
            profile_dir = user_data / profile
            if not profile_dir.is_dir():
                continue
            for rel in CACHE_DIRS:
                target = profile_dir / rel
                if not target.is_dir():
                    continue
                size = _dir_size_mb(target)
                try:
                    shutil.rmtree(target, ignore_errors=True)
                    freed += size
                    if verbose and size > 1:
                        print(f"[cache] cleared {target} ({size:.0f} MB)")
                except OSError:
                    pass
    return freed


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    try:
        freed = clear_caches(verbose=verbose)
        if verbose:
            print(f"[cache] freed about {freed:.0f} MB.")
    except Exception as exc:  # noqa: BLE001
        # Housekeeping must never stop the kiosk from starting.
        if verbose:
            print(f"[cache] skipped: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

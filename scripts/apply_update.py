"""Download the latest code from the public GitHub repo and apply it.

Used by update.bat to update the kiosk WITHOUT git installed: it downloads the
repo's branch ZIP, extracts it, and copies code files over the current install
while PRESERVING local data and secrets (.env, lunch.db, backups/, ngrok.exe).

Stdlib only. Safe to run repeatedly.

Config (edit these or pass via env):
  GITHUB_REPO   e.g. "yourname/lunchFMG"     (required)
  GITHUB_BRANCH e.g. "main"                  (default: main)

What it copies:  app/, scripts/, static/, tests/, *.py, *.bat, requirements.txt,
                 README.md, .env.example
What it NEVER touches:  .env, *.db / *.db-*, backups/, .venv/, ngrok.exe,
                        tests/data/real_cards.xlsx, *.log, tunnel-url.txt
"""
from __future__ import annotations

import io
import os
import re
import shutil
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- repo config: EDIT THESE (or set the env vars in update.bat) ------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "SabaZara/cocacolalunchFMG").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

# Directories copied wholesale (their contents replace the local ones).
COPY_DIRS = ["app", "scripts", "static"]
# tests/ is copied EXCEPT tests/data (which holds the gitignored real cards).
COPY_TESTS_CODE = True
# Individual top-level files copied if present in the download.
COPY_FILES = [
    "run.py", "tunnel_proxy.py", "requirements.txt", "README.md", ".env.example",
    "start.bat", "quick-start.bat", "kiosk.bat", "kiosk-test.bat",
    "stop.bat", "diagnose.bat", "update.bat",
    "install-autostart.bat", "uninstall-autostart.bat",
]

# Any OTHER top-level .bat shipped in the repo is copied too. This list used to
# be the only source of truth, so a newly added .bat silently never reached the
# kiosk — you could not run a script you did not have. Anything matching these
# patterns is picked up automatically from now on.
COPY_GLOBS = ["*.bat"]

# Never overwrite / never delete these (local data + secrets + binaries).
PRESERVE = {
    ".env", "lunch.db", "ngrok.exe",
    ".backup-config.json", ".app-config.json",
    "tests/data/real_cards.xlsx",
}


def _zip_url() -> str:
    return f"https://github.com/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"


def _download(url: str) -> bytes:
    # Try certifi first (Windows often can't verify via the system store).
    contexts = []
    try:
        import certifi
        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:  # noqa: BLE001
        pass
    contexts.append(None)
    unver = ssl.create_default_context()
    unver.check_hostname = False
    unver.verify_mode = ssl.CERT_NONE
    contexts.append(unver)

    last = None
    for ctx in contexts:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lunch-update"})
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"download failed: {last}")


def _version_on_disk(base: Path | None = None) -> str:
    """Read __version__ straight out of the file we just wrote.

    Importing app would return the version THIS process started with, which is
    the stale one — the whole point is to confirm what actually landed.
    """
    try:
        text = ((base or ROOT) / "app" / "__init__.py").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.strip().startswith("__version__"):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def _top_level_files(base: Path) -> list[str]:
    """Top-level files to copy: the explicit list plus anything matching
    COPY_GLOBS that `base` actually contains (de-duplicated, stable order)."""
    names = list(COPY_FILES)
    seen = set(names)
    if base.exists():
        for pattern in COPY_GLOBS:
            for item in sorted(base.glob(pattern)):
                if item.is_file() and item.name not in seen:
                    seen.add(item.name)
                    names.append(item.name)
    return names


def _copy_tree(src: Path, dst: Path) -> int:
    """Copy src dir onto dst dir (overwrite files); returns files copied."""
    count = 0
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            # copy2 preserves the SOURCE mtime, which for a GitHub zip can be
            # older than the .pyc already cached next to it. Python then keeps
            # running the stale bytecode and the update appears to do nothing.
            # Copy the bytes, then stamp the file as new.
            shutil.copyfile(item, target)
            try:
                os.utime(target, None)      # now
            except OSError:
                pass
            count += 1
    return count


def _purge_bytecode(base: Path) -> int:
    """Delete every __pycache__ under `base`. Returns directories removed.

    Belt and braces alongside the mtime fix above: with no cached bytecode
    Python must re-read the .py files it just received. This is why an update
    could land new files on disk while the app kept serving the old code —
    static files have no bytecode, so they updated instantly, and only the
    Python modules appeared frozen.
    """
    removed = 0
    for cache in base.rglob("__pycache__"):
        try:
            shutil.rmtree(cache, ignore_errors=True)
            removed += 1
        except OSError:
            pass
    return removed


def snapshot_current(root: Path | None = None) -> Path:
    """Snapshot the CURRENT code into .rollback/ before applying an update.

    If the updated app fails to come back up, scripts/self_restart.py restores
    this snapshot and relaunches — so a bad push can't strand the kiosk.
    Snapshots exactly what the update replaces (code only; never data).
    """
    base = root or ROOT
    dest = base / ".rollback"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    for d in COPY_DIRS:
        src = base / d
        if src.exists():
            _copy_tree(src, dest / d)
    if (base / "tests").exists():
        (dest / "tests").mkdir(exist_ok=True)
        for item in (base / "tests").glob("*.py"):
            shutil.copy2(item, dest / "tests" / item.name)
    for f in _top_level_files(base):
        src = base / f
        if src.exists():
            shutil.copy2(src, dest / f)
    return dest


def restore_rollback(root: Path | None = None) -> int:
    """Restore code from .rollback/ over the install. Returns files restored."""
    base = root or ROOT
    src = base / ".rollback"
    if not src.exists():
        return 0
    return _copy_tree(src, base)


def main(archive: Path | None = None) -> int:
    if "REPLACE_ME" in GITHUB_REPO:
        print("[update] GITHUB_REPO is not set. Edit scripts/apply_update.py or set")
        print("[update] GITHUB_REPO in update.bat, e.g. yourname/lunchFMG")
        return 2

    try:
        if archive is not None:
            print(f"[update] reading local release {archive}")
            data = archive.read_bytes()
        else:
            url = _zip_url()
            print(f"[update] downloading {url}")
            data = _download(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[update] {exc}")
        print("[update] Check the repo name/branch and the kiosk's internet.")
        return 1

    zf = zipfile.ZipFile(io.BytesIO(data))
    # GitHub zips contain a single top folder like "lunchFMG-main/"
    top = zf.namelist()[0].split("/")[0]
    tmp = ROOT / ".update-tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    zf.extractall(tmp)
    extracted = tmp / top
    if not extracted.exists():
        print("[update] unexpected zip layout; aborting.")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    # A locally installed release may be ahead of GitHub. Autostart must not
    # silently replace it with an older version at the next reboot.
    installed, incoming = _version_on_disk(), _version_on_disk(extracted)
    if all(re.fullmatch(r"\d+\.\d+\.\d+", value) for value in (installed, incoming)):
        if tuple(map(int, incoming.split("."))) < tuple(map(int, installed.split("."))):
            print(f"[update] skipped older version {incoming}; keeping installed {installed}.")
            shutil.rmtree(tmp, ignore_errors=True)
            return 0

    # Snapshot the current (working) code BEFORE overwriting anything, so the
    # restart step can auto-rollback if the new code fails to start.
    snapshot_current()
    print("[update] previous code snapshotted to .rollback/")

    copied = 0
    # whole directories
    for d in COPY_DIRS:
        src = extracted / d
        if src.exists():
            copied += _copy_tree(src, ROOT / d)
    # tests code (but NOT tests/data). Create the folder first: an install that
    # never had tests/ (or had it deleted) must not crash the whole update.
    if COPY_TESTS_CODE and (extracted / "tests").exists():
        (ROOT / "tests").mkdir(parents=True, exist_ok=True)
        for item in (extracted / "tests").glob("*.py"):
            shutil.copy2(item, ROOT / "tests" / item.name)
            copied += 1
    # individual files (explicit list + any *.bat the repo ships)
    for f in _top_level_files(extracted):
        src = extracted / f
        if src.exists() and f not in PRESERVE:
            shutil.copy2(src, ROOT / f)
            copied += 1

    shutil.rmtree(tmp, ignore_errors=True)

    # Drop stale bytecode so the next start really loads what we just wrote.
    purged = _purge_bytecode(ROOT)
    if purged:
        print(f"[update] cleared {purged} __pycache__ folder(s)")

    source_label = str(archive) if archive is not None else f"{GITHUB_REPO}@{GITHUB_BRANCH}"
    print(f"[update] applied {copied} files from {source_label}")

    # Prove the copy actually landed. Reporting success while nothing changed
    # is worse than failing: the operator sees "updated", the version never
    # moves, and there is nothing to act on. Read the version back OFF DISK
    # (this process still holds the old one in memory).
    if copied == 0:
        print("[update] ERROR: downloaded the repo but copied 0 files.",
              file=sys.stderr)
        print("[update] The install folder may be read-only, or in use.",
              file=sys.stderr)
        return 1

    on_disk = _version_on_disk()
    if on_disk:
        print(f"[update] version now on disk: {on_disk}")
    else:
        print("[update] WARNING: could not read the new version from disk.",
              file=sys.stderr)
    print("[update] .env, lunch.db, backups/ and ngrok.exe were left untouched.")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        help="Apply a local release ZIP instead of downloading GitHub")
    sys.exit(main(parser.parse_args().archive))

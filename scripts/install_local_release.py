r"""Apply a prepared ZIP to an existing POS install. Stop the kiosk first.

Run this script FROM THE EXTRACTED RELEASE with the existing POS Python:
  C:\POS\.venv\Scripts\python.exe C:\Release\scripts\install_local_release.py C:\Release.zip --target C:\POS
The updater preserves .env, databases, backups and the virtual environment.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import apply_update


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--target', type=Path, required=True, help='Existing POS project folder')
    args = parser.parse_args()
    target = args.target.resolve()
    if not all((target / name).is_file() for name in ('run.py', 'app/__init__.py', '.env')):
        parser.error('Target must be the existing POS installation containing run.py, app/ and .env')
    if not args.archive.is_file():
        parser.error('Release ZIP was not found')
    apply_update.ROOT = target
    return apply_update.main(args.archive.resolve())


if __name__ == '__main__':
    raise SystemExit(main())

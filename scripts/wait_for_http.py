"""Wait for a local HTTP endpoint to become ready.

Used by start.bat after launching hidden background processes. This makes
startup failures visible in the main command window instead of silently opening
a browser to a dead port.
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--label", default="service")
    args = parser.parse_args()

    deadline = time.time() + args.seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(args.url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    print(f"[ready] {args.label}: {args.url}")
                    return 0
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.5)

    print(f"[ERROR] {args.label} did not become ready: {args.url}", file=sys.stderr)
    if last_error:
        print(f"[ERROR] Last error: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

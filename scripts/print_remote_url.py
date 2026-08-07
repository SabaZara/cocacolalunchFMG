"""Print + save the public remote-admin URL.

Called by start.bat after launching ngrok. In stable-domain mode the operator
sets NGROK_DOMAIN in .env, so we can print the constant URL immediately. If the
domain is missing, fall back to polling tunnel.log for a public ngrok URL.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ROOT

load_dotenv(ROOT / ".env")
LOG = ROOT / "tunnel.log"
OUT = ROOT / "tunnel-url.txt"

URL_RE = re.compile(r"https://[a-z0-9.-]+\.ngrok(?:-free)?\.(?:app|dev)")


def _configured_url() -> str | None:
    import os

    domain = os.environ.get("NGROK_DOMAIN", "").strip()
    if not domain:
        return None
    if domain.startswith("http://"):
        domain = domain.removeprefix("http://")
    elif domain.startswith("https://"):
        domain = domain.removeprefix("https://")
    return f"https://{domain.rstrip('/')}"


def main() -> None:
    configured = _configured_url()
    if configured:
        OUT.write_text(configured + "\n", encoding="utf-8")
        print()
        print("===========================================================")
        print(f"  REMOTE ADMIN URL:  {configured}")
        print(f"  (open {configured}/admin  or  {configured}/reports )")
        print("===========================================================")
        return

    deadline = time.time() + 30
    url = None
    while time.time() < deadline:
        if LOG.exists():
            text = LOG.read_text(encoding="utf-8", errors="ignore")
            m = URL_RE.search(text)
            if m:
                url = m.group(0)
                break
        time.sleep(0.5)

    if url:
        OUT.write_text(url + "\n", encoding="utf-8")
        print()
        print("===========================================================")
        print(f"  REMOTE ADMIN URL:  {url}")
        print(f"  (open {url}/admin  or  {url}/reports )")
        print("===========================================================")
    else:
        print("[tunnel] Could not detect the public URL yet.")
        print("[tunnel] Check tunnel.log; the URL may appear there shortly.")


if __name__ == "__main__":
    main()

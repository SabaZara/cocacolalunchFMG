"""Download ngrok.exe for Windows, robust against SSL cert issues.

Some Windows Python installs can't verify TLS certs via the system store
(urllib raises SSLCertVerificationError "unable to get local issuer
certificate"). We try, in order:
  1. certifi's CA bundle (certifi ships in our deps),
  2. the default SSL context,
  3. (last resort) an UNVERIFIED context, with a clear warning — acceptable
     here because the download is a fixed, well-known URL and ngrok itself is
     re-verified by Windows when it runs.

Exits 0 on success (or if ngrok.exe already exists), 1 on failure.
"""
from __future__ import annotations

import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NGROK_EXE = ROOT / "ngrok.exe"
ZIP_PATH = ROOT / "ngrok.zip"
URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"


def _download(context: ssl.SSLContext | None) -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": "lunch-setup"})
    with urllib.request.urlopen(req, timeout=120, context=context) as resp:
        ZIP_PATH.write_bytes(resp.read())


def _extract() -> None:
    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extract("ngrok.exe", path=ROOT)
    ZIP_PATH.unlink(missing_ok=True)


def main() -> int:
    if NGROK_EXE.exists():
        print("[ngrok] ngrok.exe already present.")
        return 0

    attempts: list[tuple[str, ssl.SSLContext | None]] = []

    # 1) certifi CA bundle
    try:
        import certifi  # bundled via httpx
        attempts.append(("certifi CA bundle", ssl.create_default_context(cafile=certifi.where())))
    except Exception:  # noqa: BLE001
        pass

    # 2) default context
    attempts.append(("default SSL context", None))

    # 3) unverified (last resort)
    unverified = ssl.create_default_context()
    unverified.check_hostname = False
    unverified.verify_mode = ssl.CERT_NONE
    attempts.append(("UNVERIFIED SSL (last resort)", unverified))

    for label, ctx in attempts:
        try:
            print(f"[ngrok] downloading via {label} ...")
            _download(ctx)
            _extract()
            print("[ngrok] ngrok.exe downloaded.")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"[ngrok] {label} failed: {exc}")
            ZIP_PATH.unlink(missing_ok=True)

    print("[ngrok] Could not download ngrok.exe by any method.")
    print("[ngrok] Manual fix: download the Windows ZIP from")
    print("[ngrok]   https://ngrok.com/download")
    print("[ngrok] and place ngrok.exe next to start.bat, then re-run start.bat.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

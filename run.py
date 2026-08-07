"""Entry point used by start.bat.

Validates configuration (refuses weak password / missing SECRET_KEY) BEFORE
binding the socket, then launches uvicorn bound to the configured host/port.
Host defaults to 127.0.0.1 so the app is NOT reachable from the cafeteria LAN.
"""
from __future__ import annotations

import uvicorn

from app.config import validate_or_exit


def main() -> None:
    settings = validate_or_exit()
    print(f"[lunch] starting on http://{settings.host}:{settings.port}  (tz={settings.timezone})")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        # No reload in production; single worker keeps SQLite simple.
        workers=1,
    )


if __name__ == "__main__":
    main()

"""Remote-only gate (DENY BY DEFAULT).

The kiosk PC must only ever see the scan screen. Admin / reports / login and
their APIs are reachable ONLY through the remote tunnel/proxy, which injects a
shared secret header on every tunneled request.

Security model:
  * A small ALLOWLIST of paths is served locally with no secret — exactly the
    surface the offline kiosk needs (scan page, scan API, static assets, health).
  * `/kiosk-test` is a LOCAL-ONLY helper: served only when the request did NOT
    arrive through the tunnel/proxy.
  * EVERYTHING ELSE requires the exact TUNNEL_SECRET header. This is
    deny-by-default: an unknown or future path is protected automatically rather
    than accidentally exposed.

If TUNNEL_SECRET is unset we fail CLOSED (block everything but the allowlist),
so a misconfigured deploy never exposes admin on the LAN.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import get_settings

TUNNEL_HEADER = "x-tunnel-secret"
FORWARDED_PROTO_HEADER = "x-forwarded-proto"

# Always served locally (no secret) — the offline kiosk surface.
# /api/version leaks nothing (just a version string) and lets the admin page
# show the running version even before other gated calls.
_ALWAYS_OPEN_EXACT = {"/", "/healthz", "/favicon.ico", "/api/version"}
_ALWAYS_OPEN_PREFIXES = ("/static/", "/api/scan")

# Local-only helper page (must NOT be reachable through the tunnel/proxy).
_LOCAL_ONLY_EXACT = {"/kiosk-test", "/static/kiosk-test.js", "/static/kiosk-test.css"}

GEO_REMOTE_ONLY = "ეს გვერდი ხელმისაწვდომია მხოლოდ დისტანციურად (ტუნელით)."
GEO_LOCAL_ONLY = "ტესტის გვერდი მხოლოდ ლოკალურად იხსნება."


def _is_always_open(path: str) -> bool:
    if path in _ALWAYS_OPEN_EXACT:
        return True
    return any(path == p or path.startswith(p) for p in _ALWAYS_OPEN_PREFIXES)


def _came_through_tunnel(request: Request, secret: str) -> bool:
    """True if the request arrived via the tunnel/proxy.

    The proxy injects the shared secret AND X-Forwarded-Proto: https. We treat
    either signal as "remote": the secret is the authoritative gate, and the
    forwarded-proto guards the local-only page even if the secret is blank.
    """
    if secret and request.headers.get(TUNNEL_HEADER) == secret:
        return True
    return request.headers.get(FORWARDED_PROTO_HEADER, "").lower() == "https"


class TunnelGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        path = request.url.path
        settings = get_settings()
        secret = settings.tunnel_secret

        # 1) Local-only helper: block if it came through the tunnel/proxy.
        if path in _LOCAL_ONLY_EXACT:
            if _came_through_tunnel(request, secret):
                return JSONResponse(status_code=403, content={"detail": GEO_LOCAL_ONLY})
            return await call_next(request)

        # 2) Offline kiosk surface: always open locally.
        if _is_always_open(path):
            return await call_next(request)

        # 3) Everything else is protected: require the exact secret (deny default).
        if not secret or request.headers.get(TUNNEL_HEADER) != secret:
            return JSONResponse(status_code=403, content={"detail": GEO_REMOTE_ONLY})

        return await call_next(request)

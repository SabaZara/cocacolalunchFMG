"""Tiny localhost header-injecting reverse proxy (stdlib only).

WHY THIS EXISTS
---------------
The public tunnel should never point straight at the app. To make the
remote-only gate airtight with a shared secret, we put this small proxy between
the tunnel agent and the app:

    browser --HTTPS--> ngrok --> ngrok.exe(local) --> THIS PROXY --> app

THIS PROXY:
  * listens on 127.0.0.1:<PROXY_PORT> (NOT on the LAN),
  * adds  X-Tunnel-Secret: <TUNNEL_SECRET>  to every forwarded request,
  * forwards everything to the app on 127.0.0.1:<APP_PORT>.

ngrok points at the proxy port; the app (gated) sees the secret only on
tunneled traffic. The kiosk PC's own browser hits the APP port directly, which
has no secret, so /admin etc. stay blocked locally. Both ports are 127.0.0.1
only, so the cafeteria LAN can reach neither.

Run:  python tunnel_proxy.py            (reads env: PROXY_PORT, PORT, TUNNEL_SECRET, HOST)
"""
from __future__ import annotations

import http.client
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.config import get_settings

_settings = get_settings()
APP_HOST = "127.0.0.1"
APP_PORT = _settings.port
PROXY_PORT = int(os.environ.get("PROXY_PORT", str(APP_PORT + 1)))
TUNNEL_SECRET = _settings.tunnel_secret

# Hop-by-hop headers must not be forwarded verbatim.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):  # silence access log
        pass

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = self.rfile.read(length) if length else None
        except (ConnectionError, OSError):
            return  # client went away while sending the body

        out_headers = {}
        for k, v in self.headers.items():
            if k.lower() in _HOP_BY_HOP:
                continue
            out_headers[k] = v
        # Inject the shared secret proving "this came through the tunnel".
        out_headers["X-Tunnel-Secret"] = TUNNEL_SECRET
        # Tell the app it's effectively HTTPS (so cookies are marked Secure).
        out_headers.setdefault("X-Forwarded-Proto", "https")

        # Retry briefly instead of failing the page outright. The app is
        # momentarily absent during a restart (remote update, watchdog revive),
        # and a browser tab that has been idle in the background will otherwise
        # show a raw "502 WinError 10061" the instant the operator returns to
        # it. A few short retries cover that window invisibly.
        UPSTREAM_TRIES = 4
        RETRY_DELAY = 0.75
        resp = data = None
        last_exc: Exception | None = None
        for attempt in range(UPSTREAM_TRIES):
            conn = None
            try:
                # Generous timeout: large .xlsx/CSV exports take a few seconds.
                # Constructed INSIDE the try so a failure here is retried too
                # rather than escaping as an unhandled traceback.
                conn = http.client.HTTPConnection(APP_HOST, APP_PORT, timeout=120)
                conn.request(method, self.path, body=body, headers=out_headers)
                resp = conn.getresponse()
                data = resp.read()
                break
            except Exception as exc:  # noqa: BLE001  (upstream/app unreachable)
                last_exc = exc
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
                # Only idempotent requests are safe to replay; a POST could be
                # applied twice. Never retry one with a body.
                if body or method not in ("GET", "HEAD"):
                    break
                if attempt < UPSTREAM_TRIES - 1:
                    time.sleep(RETRY_DELAY)

        if resp is None:
            self._unavailable(last_exc)
            return

        try:
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in _HOP_BY_HOP:
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            # HEAD responses must carry headers but no body.
            if data and method != "HEAD":
                self.wfile.write(data)
        except (ConnectionError, OSError):
            # Client disconnected mid-response — normal for kiosk refreshes /
            # tunnel hiccups. Drop quietly instead of dumping a traceback.
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def _unavailable(self, exc: Exception | None) -> None:
        """Serve a self-refreshing "starting up" page instead of a raw 502.

        The app being briefly absent is a normal, self-healing state here (an
        update restart, or the watchdog reviving it). The stock error page
        showed the operator a Python-level "WinError 10061" and left them to
        refresh by hand; this waits and reloads itself, so the page comes back
        on its own once the app is listening again.
        """
        page = (
            "<!doctype html><html lang='ka'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='refresh' content='5'>"
            "<title>იტვირთება…</title><style>"
            "body{font-family:system-ui,'Segoe UI',sans-serif;background:#0f1720;"
            "color:#e8eef7;display:flex;align-items:center;justify-content:center;"
            "height:100vh;margin:0;text-align:center;padding:24px}"
            ".b{max-width:520px}h1{font-size:22px;margin:0 0 12px}"
            "p{opacity:.75;line-height:1.6;margin:6px 0}"
            ".s{margin-top:18px;font-size:13px;opacity:.5}"
            "</style></head><body><div class='b'>"
            "<h1>აპლიკაცია იტვირთება…</h1>"
            "<p>გვერდი თავისით განახლდება რამდენიმე წამში.</p>"
            "<p>თუ 5 წუთში არ ჩაიტვირთა, გადატვირთეთ ლეპტოპი.</p>"
            "<p class='s'>სკანირება ლოკალურად მუშაობს დამოუკიდებლად.</p>"
            "</div></body></html>"
        ).encode("utf-8")
        try:
            # 503 + Retry-After is the honest status: temporarily unavailable,
            # not a permanent gateway failure.
            self.send_response(503)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Retry-After", "5")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)
        except (ConnectionError, OSError):
            pass

    def _safe_error(self, code: int, message: str) -> None:
        try:
            self.send_error(code, message)
        except (ConnectionError, OSError):
            pass

    def do_GET(self):     self._proxy("GET")      # noqa: E704
    def do_POST(self):    self._proxy("POST")     # noqa: E704
    def do_PUT(self):     self._proxy("PUT")      # noqa: E704
    def do_DELETE(self):  self._proxy("DELETE")   # noqa: E704
    def do_PATCH(self):   self._proxy("PATCH")    # noqa: E704
    def do_HEAD(self):    self._proxy("HEAD")     # noqa: E704


def main() -> None:
    if not TUNNEL_SECRET:
        print("[tunnel_proxy] TUNNEL_SECRET is empty; refusing to start.", file=sys.stderr)
        sys.exit(1)
    server = ThreadingHTTPServer((APP_HOST, PROXY_PORT), ProxyHandler)
    print(f"[tunnel_proxy] 127.0.0.1:{PROXY_PORT} -> app 127.0.0.1:{APP_PORT} (+secret header)")
    server.serve_forever()


if __name__ == "__main__":
    main()

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

        # Generous timeout: large .xlsx/CSV exports can take a few seconds.
        conn = http.client.HTTPConnection(APP_HOST, APP_PORT, timeout=120)
        try:
            conn.request(method, self.path, body=body, headers=out_headers)
            resp = conn.getresponse()
            data = resp.read()
        except Exception as exc:  # noqa: BLE001  (upstream/app unreachable)
            self._safe_error(502, f"upstream error: {exc}")
            conn.close()
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
            conn.close()

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

"""Tunnel proxy behaviour when the app is momentarily absent.

The app disappears for ~10s on every update restart, and briefly whenever the
watchdog revives it. That is normal and self-healing — but the operator used to
see a raw "502 upstream error: [WinError 10061]" the instant they came back to
an idle admin tab, with no indication that waiting would fix it.
"""
from __future__ import annotations

import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def proxy(monkeypatch):
    """Run tunnel_proxy against an app port that starts out dead."""
    import importlib

    app_port = _free_port()
    proxy_port = _free_port()

    monkeypatch.setenv("PORT", str(app_port))
    monkeypatch.setenv("PROXY_PORT", str(proxy_port))
    monkeypatch.setenv("ADMIN_PASSWORD", "StrongTestPass!2026")
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("TUNNEL_SECRET", "t" * 32)
    monkeypatch.setenv("TIMEZONE", "Asia/Tbilisi")

    import app.config as config
    importlib.reload(config)
    config.get_settings.cache_clear()

    import tunnel_proxy as tp
    importlib.reload(tp)
    # Keep the test fast; the real thing waits longer.
    monkeypatch.setattr(tp, "APP_PORT", app_port, raising=False)

    server = ThreadingHTTPServer(("127.0.0.1", proxy_port), tp.ProxyHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield {"proxy_port": proxy_port, "app_port": app_port, "tp": tp}
    finally:
        server.shutdown()
        server.server_close()


def _start_fake_app(port: int, seen: list) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _reply(self):
            seen.append((self.command, self.path))
            body = b"OK-FROM-APP"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _reply
        do_POST = _reply

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_shows_friendly_page_instead_of_raw_502(proxy):
    """A dead app must not surface a Python WinError to the operator."""
    url = f"http://127.0.0.1:{proxy['proxy_port']}/admin"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(url, timeout=30)

    # 503 (temporarily unavailable) is honest; 502 implied a broken gateway.
    assert exc.value.code == 503
    body = exc.value.read().decode("utf-8")
    assert "იტვირთება" in body                 # "loading..."
    assert 'http-equiv="refresh"' in body or "http-equiv='refresh'" in body
    assert "WinError" not in body
    assert exc.value.headers.get("Retry-After") == "5"


def test_retries_until_the_app_comes_back(proxy):
    """An app that returns mid-request should be served, not failed.

    This is the restart window: the operator's idle tab reconnects while the
    app is still starting, and a single attempt would fail.
    """
    seen: list = []
    srv = None

    def start_late():
        nonlocal srv
        time.sleep(1.0)          # app comes up after the first attempt fails
        srv = _start_fake_app(proxy["app_port"], seen)

    threading.Thread(target=start_late, daemon=True).start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{proxy['proxy_port']}/", timeout=30
        ) as r:
            assert r.status == 200
            assert r.read() == b"OK-FROM-APP"
        assert len(seen) == 1, "request should reach the app exactly once"
    finally:
        if srv:
            srv.shutdown()
            srv.server_close()


def test_never_replays_a_post(proxy):
    """Retrying a POST could apply it twice — a duplicate meal or card edit.

    Counted with a raw socket client so the instrumentation cannot leak into
    the urllib connection the test itself uses to reach the proxy.
    """
    import socket

    tp = proxy["tp"]
    attempts = {"n": 0}

    def counting_conn(*a, **k):
        attempts["n"] += 1
        raise OSError("refused")

    original = tp.http.client.HTTPConnection
    tp.http.client.HTTPConnection = counting_conn
    try:
        s = socket.create_connection(("127.0.0.1", proxy["proxy_port"]), timeout=30)
        body = b'{"card_id":"X"}'
        s.sendall(
            b"POST /api/scan HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        raw = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            raw += chunk
        s.close()
        assert b"503" in raw.split(b"\r\n", 1)[0], raw[:120]
    finally:
        tp.http.client.HTTPConnection = original

    assert attempts["n"] == 1, (
        f"POST was attempted {attempts['n']}x — a replayed write can double-"
        f"apply a scan or an edit"
    )


def test_retries_a_get_several_times(proxy):
    """GET is idempotent, so it SHOULD be retried across the restart window."""
    tp = proxy["tp"]
    attempts = {"n": 0}

    def counting_conn(*a, **k):
        attempts["n"] += 1
        raise OSError("refused")

    import socket

    original = tp.http.client.HTTPConnection
    tp.http.client.HTTPConnection = counting_conn
    try:
        s = socket.create_connection(("127.0.0.1", proxy["proxy_port"]), timeout=30)
        s.sendall(b"GET /admin HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                  b"Connection: close\r\n\r\n")
        raw = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            raw += chunk
        s.close()
        assert b"503" in raw.split(b"\r\n", 1)[0], raw[:120]
    finally:
        tp.http.client.HTTPConnection = original

    assert attempts["n"] > 1, "a GET during a restart should be retried"

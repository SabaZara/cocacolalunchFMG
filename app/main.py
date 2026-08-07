"""FastAPI application entrypoint.

Wires routers, the remote-only tunnel gate, static assets, and the page routes.
On startup it creates the DB and seeds the admin. Validation of unsafe config
happens here too, so importing the app with a weak password fails loudly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ConfigError, get_settings, validate_settings
from .db import init_db
from . import backup as B
from .routers import auth, backup, people, reports, scan, settings as settings_router, update
from .seed import run_startup_seed
from .tunnel_gate import TunnelGateMiddleware

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


def _run_due_backups() -> None:
    """Weekly local snapshot + (if configured) GitHub upload. Best-effort."""
    try:
        B.auto_backup_if_due()
        B.auto_github_upload_if_due()
    except Exception:  # noqa: BLE001
        pass


def _backup_ticker(stop: "threading.Event") -> None:
    """Background daemon: re-check the weekly-due backups periodically, so they
    run on their own even if the kiosk app is never restarted."""
    # first check shortly after startup, then every 6 hours
    if stop.wait(30):
        return
    while not stop.is_set():
        _run_due_backups()
        if stop.wait(6 * 3600):
            break


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import threading

    settings = get_settings()
    # Fail loudly on unsafe configuration before serving anything.
    validate_settings(settings)
    init_db()
    run_startup_seed()
    # Backups run automatically: an immediate check now, then a background
    # ticker keeps the weekly cadence without needing a restart.
    _run_due_backups()
    stop = threading.Event()
    ticker = threading.Thread(target=_backup_ticker, args=(stop,), daemon=True)
    ticker.start()
    try:
        yield
    finally:
        stop.set()


app = FastAPI(title="LUNCH meal-access", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def _no_store(request, call_next):  # noqa: ANN001
    """Forbid browser caching of the app's pages and assets.

    A kiosk browser once served a corrupted CACHED copy of the scan page
    (garbage instead of "დაადეთ ბარათი") that survived restarts. Nothing about
    this app benefits from caching — everything is served from localhost — so we
    tell the browser never to store it. That makes a poisoned cache impossible
    and guarantees an update's new HTML/JS/CSS is picked up immediately.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Remote-only gate FIRST so it sees every request.
app.add_middleware(TunnelGateMiddleware)

# API routers.
app.include_router(scan.router)      # always-open (offline kiosk)
app.include_router(auth.router)      # gated
app.include_router(people.router)    # gated
app.include_router(reports.router)   # gated
app.include_router(update.router)    # gated (remote self-update)
app.include_router(backup.router)    # gated (backups + GitHub upload)
app.include_router(settings_router.router)  # gated (editable meal-split time)

# Static assets (css/js). The gate always allows /static/.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


# --- Pages ---------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def kiosk_page() -> FileResponse:
    # Always-open: the kiosk scan screen.
    return _page("kiosk.html")


@app.get("/kiosk-test", include_in_schema=False)
def kiosk_test_page() -> FileResponse:
    # Local-only helper for testing the real kiosk flow without a card reader.
    return _page("kiosk-test.html")


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return _page("login.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return _page("admin.html")


@app.get("/reports", include_in_schema=False)
def reports_page() -> FileResponse:
    return _page("reports.html")


@app.get("/healthz", include_in_schema=False)
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/version", include_in_schema=False)
def version() -> JSONResponse:
    from . import __version__
    return JSONResponse({"version": __version__})

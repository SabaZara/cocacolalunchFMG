"""Login / logout / me. Gated by the tunnel middleware (remote-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..models import Admin
from ..security import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    authenticate,
    check_rate_limit,
    cookie_is_secure,
    get_current_admin,
    make_session_token,
    register_failure,
    register_success,
)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    # Behind the tunnel, trust X-Forwarded-For's first hop for rate-limit keying.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    ip = _client_ip(request)
    username = payload.username.strip()

    remaining = check_rate_limit(username, ip)
    if remaining > 0:
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"ბევრი მცდელობა. სცადეთ {int(remaining) + 1} წამში."
            },
        )

    admin = authenticate(session, username, payload.password)
    if admin is None:
        register_failure(username, ip)
        return JSONResponse(
            status_code=401,
            content={"detail": "მომხმარებელი ან პაროლი არასწორია."},
        )

    register_success(username, ip)
    token = make_session_token(admin.id)
    resp = JSONResponse(content={"ok": True, "username": admin.username})
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=cookie_is_secure(request),
        samesite="lax",
        path="/",
    )
    return resp


@router.post("/logout")
def logout(request: Request) -> Response:
    resp = JSONResponse(content={"ok": True})
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp


@router.get("/me")
def me(admin: Admin = Depends(get_current_admin)) -> dict:
    return {"username": admin.username}

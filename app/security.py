"""Authentication: password hashing, signed-cookie sessions, rate limiting.

Sessions are a signed token (itsdangerous) stored in an httponly cookie. The
signature uses SECRET_KEY, so cookies survive restarts and cannot be forged
without the key. Login is rate-limited per username+IP to stop guessing.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlmodel import Session, select

from .config import get_settings
from .db import get_session
from .models import Admin

_settings = get_settings()

COOKIE_NAME = "lunch_session"
# Session lifetime (seconds) — 7 days; cookie is refreshed on each request use.
SESSION_MAX_AGE = 7 * 24 * 3600

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(_settings.secret_key, salt="lunch-session")


# ----------------------------- passwords ---------------------------------- #
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


# ----------------------------- sessions ------------------------------------ #
def make_session_token(admin_id: int) -> str:
    return _serializer.dumps({"aid": admin_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("aid") if isinstance(data, dict) else None


def cookie_is_secure(request: Request) -> bool:
    """Mark the cookie Secure when the client reached us over HTTPS.

    Behind the remote tunnel the browser uses HTTPS and the proxy sets
    X-Forwarded-Proto: https. Locally (http://127.0.0.1) we must NOT set Secure
    or the browser would drop the cookie.
    """
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


# --------------------------- rate limiting --------------------------------- #
@dataclass
class _Bucket:
    fails: int = 0
    locked_until: float = 0.0
    window_start: float = field(default_factory=time.monotonic)


_MAX_FAILS = 5
_LOCKOUT_SECONDS = 300  # 5 minutes cooldown after too many failures
_WINDOW_SECONDS = 300   # failures decay after this idle window
_buckets: dict[str, _Bucket] = defaultdict(_Bucket)


def _bucket_key(username: str, ip: str) -> str:
    return f"{username.lower()}|{ip}"


def check_rate_limit(username: str, ip: str) -> float:
    """Return remaining lockout seconds (>0 means currently locked out)."""
    b = _buckets[_bucket_key(username, ip)]
    now = time.monotonic()
    if b.locked_until and now < b.locked_until:
        return b.locked_until - now
    # Reset the failure counter if the window has elapsed since last activity.
    if now - b.window_start > _WINDOW_SECONDS:
        b.fails = 0
        b.window_start = now
    return 0.0


def register_failure(username: str, ip: str) -> None:
    b = _buckets[_bucket_key(username, ip)]
    now = time.monotonic()
    if now - b.window_start > _WINDOW_SECONDS:
        b.fails = 0
        b.window_start = now
    b.fails += 1
    if b.fails >= _MAX_FAILS:
        b.locked_until = now + _LOCKOUT_SECONDS


def register_success(username: str, ip: str) -> None:
    _buckets.pop(_bucket_key(username, ip), None)


# ------------------------- auth dependencies ------------------------------- #
def get_current_admin(
    session: Session = Depends(get_session),
    lunch_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Admin:
    """Dependency that requires a valid session cookie; else 401."""
    if not lunch_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ავტორიზაცია საჭიროა")
    admin_id = read_session_token(lunch_session)
    if admin_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ავტორიზაცია საჭიროა")
    admin = session.get(Admin, admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ავტორიზაცია საჭიროა")
    return admin


def authenticate(session: Session, username: str, password: str) -> Admin | None:
    admin = session.exec(select(Admin).where(Admin.username == username)).first()
    if admin and verify_password(password, admin.password_hash):
        return admin
    return None

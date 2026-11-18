"""Local accounts, scrypt passwords, signed sessions, CSRF (BRIEF-5 Lot 2)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

Role = Literal["viewer", "analyst", "evaluator"]
ROLES: frozenset[str] = frozenset({"viewer", "analyst", "evaluator"})

SESSION_COOKIE = "dataia_session"
CSRF_COOKIE = "dataia_csrf"
CSRF_FORM_FIELD = "csrf_token"
MIN_SECRET_LEN = 32

# scrypt parameters (stdlib); unique salt per account.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64

# In-memory login attempt limiter (process-local).
_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 10
_WINDOW_SEC = 300.0


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: Role
    disabled: bool = False


class AuthError(ValueError):
    """Public auth/config error (never includes secrets)."""


def _scrypt_hash(password: str, salt: bytes) -> str:
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return dk.hex()


def hash_password(password: str, *, salt: bytes | None = None) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) with a unique salt."""
    if salt is None:
        salt = secrets.token_bytes(16)
    return salt.hex(), _scrypt_hash(password, salt)


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    actual = bytes.fromhex(_scrypt_hash(password, salt))
    return hmac.compare_digest(actual, expected)


def default_users_path() -> Path:
    from data_ia.config import REPO_ROOT

    return REPO_ROOT / "data" / "ui" / "users.json"


def load_users(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    users = data.get("users") if isinstance(data, dict) else data
    if not isinstance(users, list):
        raise AuthError("users file is malformed")
    return [u for u in users if isinstance(u, dict)]


def save_users(path: Path, users: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"users": users}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def find_user(path: Path, username: str) -> dict[str, Any] | None:
    for user in load_users(path):
        if str(user.get("username", "")) == username:
            return user
    return None


def add_user(
    path: Path,
    *,
    username: str,
    password: str,
    role: Role,
) -> None:
    if role not in ROLES:
        raise AuthError(f"invalid role (allowed: {sorted(ROLES)})")
    if not username or not username.strip():
        raise AuthError("username required")
    if len(password) < 8:
        raise AuthError("password too short")
    users = load_users(path)
    if any(str(u.get("username")) == username for u in users):
        raise AuthError("username already exists")
    salt_hex, hash_hex = hash_password(password)
    users.append(
        {
            "username": username.strip(),
            "role": role,
            "salt": salt_hex,
            "password_hash": hash_hex,
            "disabled": False,
        }
    )
    save_users(path, users)


def set_user_disabled(path: Path, username: str, disabled: bool) -> None:
    users = load_users(path)
    found = False
    for user in users:
        if str(user.get("username")) == username:
            user["disabled"] = disabled
            found = True
            break
    if not found:
        raise AuthError("user not found")
    save_users(path, users)


def authenticate(path: Path, username: str, password: str) -> AuthUser:
    user = find_user(path, username)
    if user is None:
        raise AuthError("invalid credentials")
    if user.get("disabled"):
        raise AuthError("account disabled")
    if not verify_password(password, str(user.get("salt", "")), str(user.get("password_hash", ""))):
        raise AuthError("invalid credentials")
    role = str(user.get("role", "viewer"))
    if role not in ROLES:
        raise AuthError("invalid role on account")
    return AuthUser(username=username, role=role, disabled=False)  # type: ignore[arg-type]


def check_login_rate(key: str) -> None:
    now = time.monotonic()
    stamps = [t for t in _login_attempts.get(key, []) if now - t < _WINDOW_SEC]
    if len(stamps) >= _MAX_ATTEMPTS:
        raise AuthError("too many login attempts")
    stamps.append(now)
    _login_attempts[key] = stamps


def clear_login_rate(key: str) -> None:
    _login_attempts.pop(key, None)


def reset_login_rate_limiter() -> None:
    _login_attempts.clear()


def serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="data-ia-platform-session")


def dump_session(secret_key: str, user: AuthUser) -> str:
    return serializer(secret_key).dumps(
        {"u": user.username, "r": user.role},
    )


def load_session(
    secret_key: str,
    token: str,
    *,
    max_age_seconds: int,
) -> AuthUser | None:
    try:
        data = serializer(secret_key).loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired, Exception):
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("u")
    role = data.get("r")
    if not isinstance(username, str) or role not in ROLES:
        return None
    return AuthUser(username=username, role=role)  # type: ignore[arg-type]


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="data-ia-platform-csrf")


def sign_csrf(secret_key: str, token: str) -> str:
    return csrf_serializer(secret_key).dumps(token)


def verify_csrf(secret_key: str, signed: str, submitted: str, *, max_age_seconds: int = 3600) -> bool:
    try:
        expected = csrf_serializer(secret_key).loads(signed, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired, Exception):
        return False
    if not isinstance(expected, str):
        return False
    return hmac.compare_digest(expected, submitted)

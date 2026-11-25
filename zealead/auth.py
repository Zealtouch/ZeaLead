"""User accounts for the console: scrypt password hashes and HS256 session tokens.

Standard library only. The signing key lives in the keys directory (mode 0600),
kept apart from the data directory like ZeaLead's keys/ volume, so sessions
survive container rebuilds. A token carries a fingerprint of the user's current
password hash: changing a password signs that user out everywhere.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

TOKEN_TTL_SECONDS = 7 * 24 * 3600
MIN_PASSWORD_LENGTH = 10
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=_unb64(salt), dklen=32, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(calc, _unb64(dk))
    except (ValueError, TypeError):
        return False


# Spent on unknown usernames so a login reply takes the same time either way.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def check_login(password: str, stored: str | None) -> bool:
    if stored is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, stored)


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > 256:
        return "password is too long"
    return None


def valid_username(name: str) -> bool:
    return 1 <= len(name) <= 64 and all(c.isalnum() or c in "._-@" for c in name)


# ---------------------------------------------------------------- keys
def keys_dir(db_path: str) -> Path:
    d = os.environ.get("ZEALEAD_KEYS_DIR")
    if d:
        return Path(d)
    base = Path(db_path).resolve().parent if db_path != ":memory:" else Path.cwd()
    return base / "keys"


def load_signing_key(db_path: str) -> bytes:
    """Read keys/jwt.key, creating it on first start. In-memory databases get a throwaway key."""
    if db_path == ":memory:":
        return secrets.token_bytes(32)
    d = keys_dir(db_path)
    p = d / "jwt.key"
    if p.exists():
        return _unb64(p.read_text().strip())
    d.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(_b64(key))
    return key


# ---------------------------------------------------------------- tokens
def password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def issue_token(key: bytes, user: dict, ttl: int = TOKEN_TTL_SECONDS) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": user["username"], "uid": user["id"], "role": user["role"],
                               "pwf": password_fingerprint(user["password_hash"]), "iat": now, "exp": now + ttl},
                              separators=(",", ":")).encode())
    sig = _b64(hmac.new(key, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(key: bytes, token: str) -> dict | None:
    """Payload of a valid, unexpired token signed with `key`; None otherwise."""
    try:
        header, payload, sig = token.split(".")
        want = hmac.new(key, f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(want, _unb64(sig)):
            return None
        if json.loads(_unb64(header)).get("alg") != "HS256":
            return None
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) < time.time():
            return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


class LoginLimiter:
    """At most `limit` failed logins per client address within `window` seconds."""

    def __init__(self, limit: int = 10, window: int = 300):
        self.limit, self.window = limit, window
        self._fails: dict[str, list[float]] = {}

    def blocked(self, addr: str) -> bool:
        now = time.time()
        recent = [t for t in self._fails.get(addr, []) if now - t < self.window]
        self._fails[addr] = recent
        return len(recent) >= self.limit

    def fail(self, addr: str) -> None:
        self._fails.setdefault(addr, []).append(time.time())

    def reset(self, addr: str) -> None:
        self._fails.pop(addr, None)

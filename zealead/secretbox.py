"""Encryption for secrets stored in the database (LLM API keys, gateway headers).

AES-256-GCM under keys/llm.key (mode 0600, created on first use), kept in the keys
directory apart from the database, so a copied zealead.db alone doesn't leak keys.
"""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .auth import keys_dir

PREFIX = "v1:"
AAD = b"llm-profile-secret"   # fixed context string; never derived from the product name


class SecretBox:
    def __init__(self, key: bytes):
        self._aead = AESGCM(key)

    @classmethod
    def for_db(cls, db_path: str) -> "SecretBox":
        if db_path == ":memory:":
            return cls(secrets.token_bytes(32))
        d = keys_dir(db_path)
        p: Path = d / "llm.key"
        if p.exists():
            return cls(base64.urlsafe_b64decode(p.read_text().strip()))
        d.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # another process created it first
            return cls(base64.urlsafe_b64decode(p.read_text().strip()))
        with os.fdopen(fd, "w") as f:
            f.write(base64.urlsafe_b64encode(key).decode())
        return cls(key)

    def seal(self, plain: str) -> str:
        if not plain:
            return ""
        nonce = secrets.token_bytes(12)
        return PREFIX + base64.urlsafe_b64encode(nonce + self._aead.encrypt(nonce, plain.encode(), AAD)).decode()

    def open(self, sealed: str) -> str:
        if not sealed:
            return ""
        if not sealed.startswith(PREFIX):
            raise ValueError("unknown secret format")
        raw = base64.urlsafe_b64decode(sealed[len(PREFIX):])
        return self._aead.decrypt(raw[:12], raw[12:], AAD).decode()


def hint(key: str) -> str:
    """A masked preview the UI can show: first 3 and last 4 characters."""
    key = key.strip()
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * 6
    return f"{key[:3]}…{key[-4:]}"

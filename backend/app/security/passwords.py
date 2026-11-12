"""Password hashing with scrypt, a memory-hard KDF from the Python standard library.

Stored format: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``. The cost parameters travel with each
hash, so they can be raised later without invalidating existing accounts (see ``needs_rehash``).
Parameters follow the OWASP Password Storage Cheat Sheet (N=2^15, r=8, p=3).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

N, R, P = 2**15, 8, 3
DKLEN = 32
SALT_BYTES = 16
MAXMEM = 64 * 1024 * 1024
MIN_LENGTH = 12
MAX_LENGTH = 256  # bounds the work an attacker can force per login attempt


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=MAXMEM, dklen=DKLEN)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = _derive(password[:MAX_LENGTH], base64.b64decode(salt_b64), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    try:
        _, n, r, p, *_ = stored.split("$")
        return (int(n), int(r), int(p)) != (N, R, P)
    except ValueError:
        return True


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """A hash to verify against when the username is unknown, so both paths take similar time."""
    return hash_password(secrets.token_urlsafe(18))


def policy_problems(password: str, username: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Use at most {MAX_LENGTH} characters.")
    if username and username.lower() in password.lower():
        problems.append("Do not include the username.")
    if len(set(password)) < 6:
        problems.append("Use a less repetitive password.")
    return problems

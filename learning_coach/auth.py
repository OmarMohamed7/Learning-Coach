import os

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def authenticate(username: str, password: str) -> dict | None:
    """Accept any non-empty username if the password matches AUTH_PASSWORD_HASH from the environment."""
    username = username.strip()
    password_hash = os.getenv("AUTH_PASSWORD_HASH", "")

    if not password_hash:
        return None  # not configured: nobody can log in

    password_ok = verify_password(password_hash, password)
    if username and password_ok:
        return {"username": username, "role": os.getenv("AUTH_ROLE", "user")}
    return None

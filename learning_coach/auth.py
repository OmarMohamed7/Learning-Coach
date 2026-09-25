import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import AsyncSessionLocal
from models import AppUser

_hasher = PasswordHasher()
# Verified against when the username doesn't exist, so response time doesn't reveal valid usernames.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 8


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def authenticate(username: str, password: str) -> AppUser | None:
    """Return the active user if the credentials are valid, else None."""
    username = normalize_username(username)
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(AppUser).where(AppUser.username == username))
        ).scalar_one_or_none()

        if user is None:
            verify_password(_DUMMY_HASH, password)
            return None
        if not verify_password(user.password_hash, password) or not user.is_active:
            return None

        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            await session.commit()
        return user


async def register_user(username: str, password: str) -> str | None:
    """Create an account. Returns an error message, or None on success."""
    username = normalize_username(username)
    if not USERNAME_RE.match(username):
        return "Username must be 3-32 characters: letters, numbers, '_', '.' or '-'."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."

    async with AsyncSessionLocal() as session:
        session.add(AppUser(username=username, password_hash=hash_password(password)))
        try:
            await session.commit()
        except IntegrityError:
            return "That username is already taken."
    return None

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

password_hasher = PasswordHasher()  # Argon2id, maintained library defaults.


def validate_password(value: str) -> str:
    if not 12 <= len(value) <= 128 or "\x00" in value:
        raise ValueError("Use a password of 12–128 characters without null characters")
    if len(set(value)) < 4 or value.casefold() in {"password1234", "123456789012", "qwerty123456"}:
        raise ValueError("Choose a less predictable password or a longer passphrase")
    return value


def hash_password(password: str) -> str:
    return password_hasher.hash(validate_password(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def random_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    # SHA-256 is appropriate for high-entropy random tokens, never for passwords.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

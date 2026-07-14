"""Email normalization and one-way password hashing for local credentials."""

import base64
import hashlib
import hmac
import re
import secrets
import unicodedata


class InvalidEmailError(ValueError):
    """Raised when an email cannot be used as a GOAL login identifier."""


class InvalidPasswordHashError(ValueError):
    """Raised when a persisted password hash is malformed or unsupported."""


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LENGTH = 32
_SALT_LENGTH = 16
_SCRYPT_MAX_MEMORY = 64 * 1024 * 1024


def normalize_email(value: str) -> str:
    """Return GOAL's case-insensitive, whitespace-free email identifier."""

    email = unicodedata.normalize("NFKC", value).strip().casefold()
    if not 3 <= len(email) <= 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise InvalidEmailError
    return email


class PasswordHasher:
    """Store passwords as versioned scrypt hashes with an independent random salt."""

    @staticmethod
    def hash(password: str) -> str:
        """Return a self-describing scrypt hash without retaining the password."""

        salt = secrets.token_bytes(_SALT_LENGTH)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_LENGTH,
            maxmem=_SCRYPT_MAX_MEMORY,
        )
        return "$".join(
            (
                "scrypt",
                "v1",
                str(_SCRYPT_N),
                str(_SCRYPT_R),
                str(_SCRYPT_P),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(derived).decode("ascii"),
            )
        )

    @staticmethod
    def verify(password: str, encoded: str) -> bool:
        """Verify one password against a versioned hash in constant time."""

        try:
            algorithm, version, n, r, p, salt_text, expected_text = encoded.split("$")
            if algorithm != "scrypt" or version != "v1":
                raise InvalidPasswordHashError
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
            if len(salt) != _SALT_LENGTH or len(expected) != _SCRYPT_LENGTH:
                raise InvalidPasswordHashError
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=_SCRYPT_LENGTH,
                maxmem=_SCRYPT_MAX_MEMORY,
            )
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise InvalidPasswordHashError from exc
        return hmac.compare_digest(derived, expected)

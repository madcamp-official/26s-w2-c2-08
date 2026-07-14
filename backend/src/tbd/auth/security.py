"""Purpose-separated hashing, PKCE, and OAuth secret encryption."""

import base64
import hashlib
import hmac
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class InvalidCiphertextError(Exception):
    """Raised when an OAuth transaction secret cannot be authenticated."""


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class AuthCrypto:
    """Create opaque browser tokens without storing their plaintext values."""

    _PKCE_AAD = b"goal/oauth/pkce/v1"

    def __init__(self, secret: str) -> None:
        secret_bytes = secret.encode("utf-8")
        self._hmac_key = hmac.digest(secret_bytes, b"goal/auth/hmac/v1", "sha256")
        self._encryption_key = hmac.digest(secret_bytes, b"goal/auth/aes/v1", "sha256")

    @staticmethod
    def opaque_token() -> str:
        """Return a high-entropy URL-safe browser token."""

        return secrets.token_urlsafe(32)

    def hash_token(self, purpose: str, value: str) -> bytes:
        """Return a purpose-separated HMAC for a browser or provider value."""

        message = purpose.encode("ascii") + b"\x00" + value.encode("utf-8")
        return hmac.digest(self._hmac_key, message, "sha256")

    @staticmethod
    def pkce_challenge(verifier: str) -> str:
        """Return the RFC 7636 S256 challenge for a verifier."""

        return _base64url(hashlib.sha256(verifier.encode("ascii")).digest())

    def encrypt_pkce_verifier(self, verifier: str) -> tuple[bytes, bytes]:
        """Encrypt a verifier for the short callback window."""

        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._encryption_key).encrypt(
            nonce,
            verifier.encode("ascii"),
            self._PKCE_AAD,
        )
        return ciphertext, nonce

    def decrypt_pkce_verifier(self, ciphertext: bytes, nonce: bytes) -> str:
        """Authenticate and decrypt a stored verifier."""

        try:
            plaintext = AESGCM(self._encryption_key).decrypt(
                nonce,
                ciphertext,
                self._PKCE_AAD,
            )
        except InvalidTag as exc:
            raise InvalidCiphertextError from exc
        return plaintext.decode("ascii")

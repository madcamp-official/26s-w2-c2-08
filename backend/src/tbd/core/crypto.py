"""Small cryptographic boundaries for protected application values."""

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class EncryptedPayload:
    """Ciphertext metadata persisted with one idempotency response."""

    ciphertext: bytes
    nonce: bytes
    key_version: int


class ResponseCipher(Protocol):
    """Encrypt and decrypt stored HTTP responses without leaking key details."""

    def encrypt(self, plaintext: bytes) -> EncryptedPayload: ...

    def decrypt(self, payload: EncryptedPayload) -> bytes: ...


class AesGcmResponseCipher:
    """AES-256-GCM response cipher with an explicit rotation version."""

    def __init__(self, key: bytes, *, key_version: int = 1) -> None:
        if len(key) != 32:
            raise ValueError("idempotency response encryption key must be exactly 32 bytes")
        if key_version < 1:
            raise ValueError("idempotency response encryption key version must be positive")
        self._cipher = AESGCM(key)
        self._key_version = key_version

    def encrypt(self, plaintext: bytes) -> EncryptedPayload:
        nonce = os.urandom(12)
        return EncryptedPayload(
            ciphertext=self._cipher.encrypt(nonce, plaintext, None),
            nonce=nonce,
            key_version=self._key_version,
        )

    def decrypt(self, payload: EncryptedPayload) -> bytes:
        if payload.key_version != self._key_version:
            raise ValueError("idempotency response encryption key version is unavailable")
        return self._cipher.decrypt(payload.nonce, payload.ciphertext, None)


class CourseJoinCodeCodec:
    """Encrypt Course join codes and derive a separate lookup-only HMAC."""

    def __init__(
        self,
        *,
        encryption_key: bytes,
        encryption_key_version: int,
        lookup_key: bytes,
        lookup_key_version: int,
    ) -> None:
        if len(encryption_key) != 32:
            raise ValueError("Course join-code encryption key must be exactly 32 bytes")
        if len(lookup_key) < 32:
            raise ValueError("Course join-code lookup key must be at least 32 bytes")
        if encryption_key_version < 1 or lookup_key_version < 1:
            raise ValueError("Course join-code key versions must be positive")
        self._cipher = AESGCM(encryption_key)
        self._encryption_key_version = encryption_key_version
        self._lookup_key = lookup_key
        self.lookup_key_version = lookup_key_version

    def lookup_hash(self, normalized_code: str) -> bytes:
        """Return a deterministic digest without making the raw code recoverable."""

        return hmac.new(
            self._lookup_key,
            normalized_code.encode("ascii"),
            hashlib.sha256,
        ).digest()

    def encrypt(self, normalized_code: str, *, course_id: str) -> EncryptedPayload:
        """Encrypt a normalized code while binding it to one Course ID."""

        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(
            nonce,
            normalized_code.encode("ascii"),
            course_id.encode("ascii"),
        )
        return EncryptedPayload(
            ciphertext=ciphertext,
            nonce=nonce,
            key_version=self._encryption_key_version,
        )

    def decrypt(self, payload: EncryptedPayload, *, course_id: str) -> str:
        """Decrypt a code only when its key version and Course binding match."""

        if payload.key_version != self._encryption_key_version:
            raise ValueError("Course join-code encryption key version is unavailable")
        plaintext = self._cipher.decrypt(
            payload.nonce,
            payload.ciphertext,
            course_id.encode("ascii"),
        )
        return plaintext.decode("ascii")

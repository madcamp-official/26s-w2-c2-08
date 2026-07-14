"""Small cryptographic boundary for encrypted idempotency response bodies."""

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

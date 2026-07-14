"""Unit tests for deterministic idempotency fingerprints and encrypted responses."""

import pytest

from tbd.core.crypto import AesGcmResponseCipher, EncryptedPayload
from tbd.core.request_hash import canonical_request_hash, idempotency_key_hash

pytestmark = pytest.mark.unit


def test_request_hash_uses_normalized_json_not_field_order() -> None:
    """Equivalent validated JSON requests share one deterministic request fingerprint."""

    left = canonical_request_hash(
        "post",
        "/api/v1/sessions/{session_id}/summaries",
        {"title": "café", "items": [1, {"enabled": True}]},
    )
    right = canonical_request_hash(
        "POST",
        "/api/v1/sessions/{session_id}/summaries",
        {"items": [1, {"enabled": True}], "title": "cafe\u0301"},
    )

    assert left == right
    assert len(left) == 32


def test_request_hash_changes_when_semantic_input_changes() -> None:
    """A key reuse conflict can distinguish two distinct validated bodies."""

    left = canonical_request_hash("POST", "/api/v1/jobs/{job_id}/retry", {"force": False})
    right = canonical_request_hash("POST", "/api/v1/jobs/{job_id}/retry", {"force": True})

    assert left != right
    assert idempotency_key_hash("key-a") != idempotency_key_hash("key-b")


def test_response_cipher_round_trips_and_rejects_unknown_key_version() -> None:
    """Persisted response ciphertext is unusable without the configured key version."""

    cipher = AesGcmResponseCipher(b"a" * 32, key_version=3)
    encrypted = cipher.encrypt(b'{"job":"safe"}')

    assert encrypted.nonce != b""
    assert cipher.decrypt(encrypted) == b'{"job":"safe"}'

    with pytest.raises(ValueError, match="key version"):
        cipher.decrypt(
            EncryptedPayload(
                ciphertext=encrypted.ciphertext,
                nonce=encrypted.nonce,
                key_version=2,
            )
        )


def test_response_cipher_requires_aes_256_key_material() -> None:
    """A short development key cannot silently weaken persisted response encryption."""

    with pytest.raises(ValueError, match="32 bytes"):
        AesGcmResponseCipher(b"short")

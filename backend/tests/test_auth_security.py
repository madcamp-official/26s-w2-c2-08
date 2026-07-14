"""Unit tests for authentication secrets, PKCE, and provider redirects."""

import pytest

from tbd.auth.security import AuthCrypto, InvalidCiphertextError

pytestmark = pytest.mark.unit


def test_pkce_uses_the_rfc_7636_s256_vector() -> None:
    """PKCE challenges must use SHA-256 and unpadded base64url encoding."""

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert AuthCrypto.pkce_challenge(verifier) == ("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")


def test_hashes_are_fixed_length_and_purpose_separated() -> None:
    """One plaintext cannot correlate across stored token purposes."""

    crypto = AuthCrypto("test-secret-that-is-longer-than-thirty-two-bytes")

    session_hash = crypto.hash_token("session", "same-value")
    state_hash = crypto.hash_token("oauth-state", "same-value")

    assert len(session_hash) == 32
    assert len(state_hash) == 32
    assert session_hash != state_hash


def test_pkce_verifier_ciphertext_rejects_tampering() -> None:
    """Stored verifiers are confidential and authenticated."""

    crypto = AuthCrypto("test-secret-that-is-longer-than-thirty-two-bytes")
    ciphertext, nonce = crypto.encrypt_pkce_verifier("verifier")

    assert crypto.decrypt_pkce_verifier(ciphertext, nonce) == "verifier"

    tampered = bytes([ciphertext[0] ^ 1, *ciphertext[1:]])
    with pytest.raises(InvalidCiphertextError):
        crypto.decrypt_pkce_verifier(tampered, nonce)

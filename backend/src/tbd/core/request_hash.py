"""Canonical request and idempotency-key hashes for duplicate-safe writes."""

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


def _normalize_json(value: Any) -> Any:
    """Normalize JSON-safe request data before producing a stable digest."""

    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized_items = (
            (unicodedata.normalize("NFC", str(key)), _normalize_json(item))
            for key, item in value.items()
        )
        return {key: item for key, item in sorted(normalized_items)}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [_normalize_json(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError("request hash input must contain JSON-compatible values")


def canonical_request_hash(
    method: str, route_key: str, body: Mapping[str, Any] | Sequence[Any]
) -> bytes:
    """Hash a normalized HTTP method, stable route key, and validated request body."""

    normalized_method = method.strip().upper()
    normalized_route = route_key.strip()
    if not normalized_method or not normalized_route:
        raise ValueError("method and route key must not be blank")
    payload = {
        "body": _normalize_json(body),
        "method": normalized_method,
        "route_key": normalized_route,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def idempotency_key_hash(key: str) -> bytes:
    """Hash an unlogged user-provided key after rejecting an empty value."""

    if not key or not key.strip():
        raise ValueError("Idempotency-Key must not be blank")
    return hashlib.sha256(key.encode("utf-8")).digest()

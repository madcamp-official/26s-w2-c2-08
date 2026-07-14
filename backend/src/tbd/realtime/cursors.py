"""Opaque, tamper-evident resume cursors for durable Outbox events."""

import base64
import hmac
from uuid import UUID


class RealtimeCursorCodec:
    """Encode one Outbox event ID without exposing a reusable raw database ID."""

    _PREFIX = b"goal/realtime/cursor/v1\x00"

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(self, event_id: UUID) -> str:
        raw_id = event_id.bytes
        signature = hmac.digest(self._key, raw_id, "sha256")[:16]
        return base64.urlsafe_b64encode(raw_id + signature).rstrip(b"=").decode("ascii")

    def decode(self, cursor: str) -> UUID | None:
        padding = "=" * (-len(cursor) % 4)
        try:
            raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            return None
        if len(raw) != 32:
            return None
        raw_id, signature = raw[:16], raw[16:]
        expected = hmac.digest(self._key, raw_id, "sha256")[:16]
        if not hmac.compare_digest(signature, expected):
            return None
        return UUID(bytes=raw_id)

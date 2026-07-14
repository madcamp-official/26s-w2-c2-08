"""Shared opaque cursors for Course-level archive collections."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from collections.abc import Mapping, Sequence
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class InvalidCourseArchiveCursorError(Exception):
    """A cursor was malformed, tampered with, or reused outside its archive scope."""


class CourseArchiveCursorCodec:
    """Sign one Course archive position together with its immutable query scope."""

    _PREFIX = b"goal/course-archives/cursor/v1\x00"
    _SIGNATURE_BYTES = 16

    def __init__(self, secret: str) -> None:
        self._key = hmac.digest(secret.encode("utf-8"), self._PREFIX, "sha256")

    def encode(
        self,
        *,
        course_id: UUID,
        resource: str,
        scope: Mapping[str, JsonValue],
        position: Sequence[JsonValue],
    ) -> str:
        raw = json.dumps(
            {
                "course_id": str(course_id),
                "position": list(position),
                "resource": resource,
                "scope": dict(scope),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.digest(self._key, raw, "sha256")[: self._SIGNATURE_BYTES]
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def decode(
        self,
        *,
        cursor: str,
        course_id: UUID,
        resource: str,
        scope: Mapping[str, JsonValue],
    ) -> list[JsonValue]:
        try:
            encoded = base64.b64decode(
                cursor + "=" * (-len(cursor) % 4),
                altchars=b"-_",
                validate=True,
            )
            canonical = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
            if not hmac.compare_digest(canonical, cursor):
                raise ValueError
            if len(encoded) <= self._SIGNATURE_BYTES:
                raise ValueError
            raw = encoded[: -self._SIGNATURE_BYTES]
            signature = encoded[-self._SIGNATURE_BYTES :]
            expected = hmac.digest(self._key, raw, "sha256")[: self._SIGNATURE_BYTES]
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
            if set(payload) != {"course_id", "position", "resource", "scope"}:
                raise ValueError
            if (
                payload["course_id"] != str(course_id)
                or payload["resource"] != resource
                or payload["scope"] != dict(scope)
                or not isinstance(payload["position"], list)
            ):
                raise ValueError
            return payload["position"]
        except (
            binascii.Error,
            json.JSONDecodeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise InvalidCourseArchiveCursorError from exc

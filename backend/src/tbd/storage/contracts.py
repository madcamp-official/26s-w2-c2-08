"""Private storage contract shared by future material and recording services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from re import Pattern
from re import compile as re_compile
from typing import Protocol, runtime_checkable
from uuid import uuid4

_IDENTIFIER_PATTERN: Pattern[str] = re_compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
_SHA256_PATTERN: Pattern[str] = re_compile(r"[0-9a-f]{64}")


class StorageNamespace(StrEnum):
    """Logical object visibility before and after a domain commit."""

    TEMPORARY = "temporary"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class StorageKey:
    """Server-generated logical object key that is never a client value."""

    namespace: StorageNamespace
    identifier: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.identifier):
            raise ValueError("storage key identifier has an unsafe format")

    @classmethod
    def new(cls, namespace: StorageNamespace) -> StorageKey:
        """Create an opaque key suitable for one temporary or final object."""

        return cls(namespace=namespace, identifier=uuid4().hex)

    @classmethod
    def parse(cls, value: str) -> StorageKey:
        """Read a persisted logical key without accepting paths or nested keys."""

        namespace_value, separator, identifier = value.partition("/")
        if not separator or "/" in identifier:
            raise ValueError("storage key must contain one namespace separator")
        try:
            namespace = StorageNamespace(namespace_value)
        except ValueError as exc:
            raise ValueError("storage key namespace is invalid") from exc
        return cls(namespace=namespace, identifier=identifier)

    @property
    def value(self) -> str:
        """Return the private persistence value for the key."""

        return f"{self.namespace.value}/{self.identifier}"


def sha256_bytes(value: bytes) -> str:
    """Return the lower-case SHA-256 hexadecimal digest for bytes."""

    return sha256(value).hexdigest()


def validate_sha256(value: str) -> str:
    """Reject malformed digests before they reach a storage provider."""

    normalized = value.lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError("SHA-256 must be a 64-character hexadecimal digest")
    return normalized


class StorageError(RuntimeError):
    """Base exception with a safe code and retryability classification."""

    code = "STORAGE_ERROR"
    retryable = False


class StorageNotFoundError(StorageError):
    """Raised when an expected object does not exist."""

    code = "STORAGE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("storage object was not found")


class StorageIntegrityError(StorageError):
    """Raised for malformed checksums or unsafe on-disk object state."""

    code = "STORAGE_INTEGRITY_ERROR"

    def __init__(self) -> None:
        super().__init__("storage object integrity validation failed")


class StorageOffsetMismatchError(StorageError):
    """Raised when resumable append does not start at the confirmed offset."""

    code = "STORAGE_OFFSET_MISMATCH"

    def __init__(self, expected_offset: int, actual_offset: int) -> None:
        self.expected_offset = expected_offset
        self.actual_offset = actual_offset
        super().__init__("storage append offset did not match")


class StorageRangeError(StorageError):
    """Raised for an invalid private byte range."""

    code = "STORAGE_RANGE_INVALID"

    def __init__(self, start: int, end: int, size: int) -> None:
        self.start = start
        self.end = end
        self.size = size
        super().__init__("storage byte range was invalid")


class StorageConflictError(StorageError):
    """Raised when a final logical key points at different content."""

    code = "STORAGE_KEY_CONFLICT"

    def __init__(self) -> None:
        super().__init__("storage key is already bound to different content")


class StorageUnavailableError(StorageError):
    """Raised for retryable adapter or provider failures."""

    code = "STORAGE_UNAVAILABLE"
    retryable = True

    def __init__(self) -> None:
        super().__init__("storage provider is temporarily unavailable")


@dataclass(frozen=True, slots=True)
class StorageObject:
    """Private metadata returned after a storage operation succeeds."""

    key: StorageKey
    byte_size: int
    sha256: str

    def __post_init__(self) -> None:
        if self.byte_size < 0:
            raise ValueError("storage object size must not be negative")
        object.__setattr__(self, "sha256", validate_sha256(self.sha256))


@dataclass(frozen=True, slots=True)
class StorageAppendResult:
    """Server-confirmed offset and checksum after one append operation."""

    confirmed_offset: int
    sha256: str

    def __post_init__(self) -> None:
        if self.confirmed_offset < 0:
            raise ValueError("confirmed offset must not be negative")
        object.__setattr__(self, "sha256", validate_sha256(self.sha256))


@dataclass(frozen=True, slots=True)
class StorageDeleteResult:
    """Result of an idempotent delete; missing objects are not failures."""

    removed: bool


@runtime_checkable
class Storage(Protocol):
    """Async provider-neutral contract; it has no HTTP or authorization concerns."""

    async def create_temporary(self, key: StorageKey) -> StorageObject:
        """Create or recover one empty temporary object."""

    async def append(
        self,
        key: StorageKey,
        data: bytes,
        *,
        expected_offset: int,
        checksum: str,
    ) -> StorageAppendResult:
        """Append checksum-validated bytes only at the expected offset."""

    async def promote(
        self,
        source: StorageKey,
        target: StorageKey,
        *,
        expected_sha256: str,
    ) -> StorageObject:
        """Atomically make a verified temporary object available as final."""

    async def stat(self, key: StorageKey) -> StorageObject:
        """Return private object metadata."""

    async def read_range(self, key: StorageKey, *, start: int, end: int) -> bytes:
        """Read the private half-open byte interval ``[start, end)``."""

    async def delete(self, key: StorageKey) -> StorageDeleteResult:
        """Delete an object; a missing object is a successful no-op."""

    def iter_keys(
        self,
        namespace: StorageNamespace | None = None,
    ) -> AsyncIterator[StorageKey]:
        """Yield private keys for reconciliation without exposing physical paths."""

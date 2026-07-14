"""Deterministic Storage adapters used by unit tests and future feature fakes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum

from tbd.storage.contracts import (
    Storage,
    StorageAppendResult,
    StorageConflictError,
    StorageDeleteResult,
    StorageIntegrityError,
    StorageKey,
    StorageNamespace,
    StorageNotFoundError,
    StorageObject,
    StorageOffsetMismatchError,
    StorageRangeError,
    StorageUnavailableError,
    sha256_bytes,
    validate_sha256,
)


class InMemoryStorage:
    """Small deterministic Storage implementation with no filesystem dependency."""

    def __init__(self) -> None:
        self._objects: dict[StorageKey, bytes] = {}

    async def create_temporary(self, key: StorageKey) -> StorageObject:
        """Create an empty temporary object or recover its current bytes."""

        if key.namespace is not StorageNamespace.TEMPORARY:
            raise StorageConflictError()
        self._objects.setdefault(key, b"")
        return self._metadata(key)

    async def append(
        self,
        key: StorageKey,
        data: bytes,
        *,
        expected_offset: int,
        checksum: str,
    ) -> StorageAppendResult:
        """Append one checksum-verified chunk at an exact offset."""

        if key.namespace is not StorageNamespace.TEMPORARY:
            raise StorageConflictError()
        checksum = validate_sha256(checksum)
        if sha256_bytes(data) != checksum:
            raise StorageIntegrityError()
        current = self._read(key)
        if expected_offset != len(current):
            raise StorageOffsetMismatchError(expected_offset, len(current))
        current += data
        self._objects[key] = current
        return StorageAppendResult(confirmed_offset=len(current), sha256=sha256_bytes(current))

    async def promote(
        self,
        source: StorageKey,
        target: StorageKey,
        *,
        expected_sha256: str,
    ) -> StorageObject:
        """Promote matching bytes and refuse a conflicting final key."""

        if source.namespace is not StorageNamespace.TEMPORARY:
            raise StorageConflictError()
        if target.namespace is not StorageNamespace.FINAL:
            raise StorageConflictError()
        expected_sha256 = validate_sha256(expected_sha256)
        source_value = self._read(source)
        if sha256_bytes(source_value) != expected_sha256:
            raise StorageIntegrityError()
        target_value = self._objects.get(target)
        if target_value is not None and sha256_bytes(target_value) != expected_sha256:
            raise StorageConflictError()
        self._objects[target] = source_value
        self._objects.pop(source, None)
        return self._metadata(target)

    async def stat(self, key: StorageKey) -> StorageObject:
        """Return metadata for a stored object."""

        return self._metadata(key)

    async def read_range(self, key: StorageKey, *, start: int, end: int) -> bytes:
        """Read one half-open byte range."""

        value = self._read(key)
        if start < 0 or end < start or end > len(value):
            raise StorageRangeError(start, end, len(value))
        return value[start:end]

    async def delete(self, key: StorageKey) -> StorageDeleteResult:
        """Remove a key without failing when it has already been removed."""

        removed = self._objects.pop(key, None) is not None
        return StorageDeleteResult(removed=removed)

    async def _iter_keys(self, namespace: StorageNamespace | None) -> AsyncIterator[StorageKey]:
        keys = sorted(self._objects, key=lambda key: key.value)
        for key in keys:
            if namespace is None or key.namespace is namespace:
                yield key

    def iter_keys(
        self,
        namespace: StorageNamespace | None = None,
    ) -> AsyncIterator[StorageKey]:
        """Yield currently stored keys in a deterministic order."""

        return self._iter_keys(namespace)

    def _read(self, key: StorageKey) -> bytes:
        try:
            return self._objects[key]
        except KeyError as exc:
            raise StorageNotFoundError() from exc

    def _metadata(self, key: StorageKey) -> StorageObject:
        value = self._read(key)
        return StorageObject(key=key, byte_size=len(value), sha256=sha256_bytes(value))


class StorageOperation(StrEnum):
    """Failure injection points shared by Storage adapter tests."""

    CREATE_TEMPORARY = "CREATE_TEMPORARY"
    APPEND = "APPEND"
    PROMOTE = "PROMOTE"
    STAT = "STAT"
    READ_RANGE = "READ_RANGE"
    DELETE = "DELETE"
    ITERATE = "ITERATE"


class FailureStorage:
    """Delegate Storage calls while injecting a chosen number of transient failures."""

    def __init__(self, delegate: Storage) -> None:
        self._delegate = delegate
        self._remaining_failures: dict[StorageOperation, int] = {}

    def fail_next(self, operation: StorageOperation, *, count: int = 1) -> None:
        """Schedule one or more retryable failures before delegation."""

        if count < 1:
            raise ValueError("failure count must be positive")
        self._remaining_failures[operation] = self._remaining_failures.get(operation, 0) + count

    async def create_temporary(self, key: StorageKey) -> StorageObject:
        self._raise_if_scheduled(StorageOperation.CREATE_TEMPORARY)
        return await self._delegate.create_temporary(key)

    async def append(
        self,
        key: StorageKey,
        data: bytes,
        *,
        expected_offset: int,
        checksum: str,
    ) -> StorageAppendResult:
        self._raise_if_scheduled(StorageOperation.APPEND)
        return await self._delegate.append(
            key,
            data,
            expected_offset=expected_offset,
            checksum=checksum,
        )

    async def promote(
        self,
        source: StorageKey,
        target: StorageKey,
        *,
        expected_sha256: str,
    ) -> StorageObject:
        self._raise_if_scheduled(StorageOperation.PROMOTE)
        return await self._delegate.promote(source, target, expected_sha256=expected_sha256)

    async def stat(self, key: StorageKey) -> StorageObject:
        self._raise_if_scheduled(StorageOperation.STAT)
        return await self._delegate.stat(key)

    async def read_range(self, key: StorageKey, *, start: int, end: int) -> bytes:
        self._raise_if_scheduled(StorageOperation.READ_RANGE)
        return await self._delegate.read_range(key, start=start, end=end)

    async def delete(self, key: StorageKey) -> StorageDeleteResult:
        self._raise_if_scheduled(StorageOperation.DELETE)
        return await self._delegate.delete(key)

    async def _iter_keys(self, namespace: StorageNamespace | None) -> AsyncIterator[StorageKey]:
        self._raise_if_scheduled(StorageOperation.ITERATE)
        async for key in self._delegate.iter_keys(namespace):
            yield key

    def iter_keys(
        self,
        namespace: StorageNamespace | None = None,
    ) -> AsyncIterator[StorageKey]:
        return self._iter_keys(namespace)

    def _raise_if_scheduled(self, operation: StorageOperation) -> None:
        remaining = self._remaining_failures.get(operation, 0)
        if remaining == 0:
            return
        self._remaining_failures[operation] = remaining - 1
        raise StorageUnavailableError()

"""Unit tests for provider-neutral private Storage behavior."""

import asyncio
import os
from pathlib import Path

import pytest

from tbd.storage import (
    DeletionDisposition,
    FailureStorage,
    FilesystemStorage,
    InMemoryStorage,
    StorageCompensation,
    StorageConflictError,
    StorageIntegrityError,
    StorageKey,
    StorageNamespace,
    StorageNotFoundError,
    StorageOffsetMismatchError,
    StorageOperation,
    StorageRangeError,
    StorageReconciler,
    StorageUnavailableError,
    classify_deletion_error,
    sha256_bytes,
)

pytestmark = pytest.mark.unit


def test_storage_key_is_opaque_and_rejects_path_like_identifiers() -> None:
    """Logical keys cannot contain paths supplied by callers or providers."""

    key = StorageKey.new(StorageNamespace.TEMPORARY)

    assert StorageKey.parse(key.value) == key

    for identifier in ("../outside", "/absolute", "nested/key", "", "space key"):
        with pytest.raises(ValueError):
            StorageKey(namespace=StorageNamespace.TEMPORARY, identifier=identifier)

    for value in ("temporary", "unknown/abc", "temporary/nested/key"):
        with pytest.raises(ValueError):
            StorageKey.parse(value)


def test_filesystem_storage_append_promote_range_and_idempotent_delete(tmp_path: Path) -> None:
    """A temporary object becomes final only after offset and digest validation."""

    async def exercise() -> None:
        storage = FilesystemStorage(tmp_path / "storage")
        temporary = StorageKey.new(StorageNamespace.TEMPORARY)
        final = StorageKey.new(StorageNamespace.FINAL)
        payload = b"hello storage"

        created = await storage.create_temporary(temporary)
        assert created.byte_size == 0
        appended = await storage.append(
            temporary,
            payload,
            expected_offset=0,
            checksum=sha256_bytes(payload),
        )
        assert appended.confirmed_offset == len(payload)
        promoted = await storage.promote(
            temporary,
            final,
            expected_sha256=sha256_bytes(payload),
        )

        assert promoted.byte_size == len(payload)
        assert await storage.read_range(final, start=6, end=13) == b"storage"
        with pytest.raises(StorageNotFoundError):
            await storage.stat(temporary)

        assert (await storage.delete(final)).removed
        assert not (await storage.delete(final)).removed

    asyncio.run(exercise())


def test_filesystem_storage_rejects_bad_checksum_offset_and_range(tmp_path: Path) -> None:
    """Invalid input cannot append bytes, promote content, or escape a range."""

    async def exercise() -> None:
        storage = FilesystemStorage(tmp_path / "storage")
        temporary = StorageKey.new(StorageNamespace.TEMPORARY)
        final = StorageKey.new(StorageNamespace.FINAL)
        payload = b"chunk"
        await storage.create_temporary(temporary)

        with pytest.raises(StorageIntegrityError):
            await storage.append(
                temporary,
                payload,
                expected_offset=0,
                checksum=sha256_bytes(b"different"),
            )
        assert (await storage.stat(temporary)).byte_size == 0

        with pytest.raises(StorageOffsetMismatchError):
            await storage.append(
                temporary,
                payload,
                expected_offset=1,
                checksum=sha256_bytes(payload),
            )

        await storage.append(
            temporary,
            payload,
            expected_offset=0,
            checksum=sha256_bytes(payload),
        )
        with pytest.raises(StorageIntegrityError):
            await storage.promote(
                temporary,
                final,
                expected_sha256=sha256_bytes(b"different"),
            )
        with pytest.raises(StorageRangeError):
            await storage.read_range(temporary, start=0, end=len(payload) + 1)

    asyncio.run(exercise())


def test_filesystem_storage_serializes_same_offset_appends(tmp_path: Path) -> None:
    """Two concurrent retries cannot both append at the same confirmed offset."""

    async def exercise() -> None:
        storage = FilesystemStorage(tmp_path / "storage")
        temporary = StorageKey.new(StorageNamespace.TEMPORARY)
        first = b"first"
        second = b"second"
        await storage.create_temporary(temporary)

        results = await asyncio.gather(
            storage.append(
                temporary,
                first,
                expected_offset=0,
                checksum=sha256_bytes(first),
            ),
            storage.append(
                temporary,
                second,
                expected_offset=0,
                checksum=sha256_bytes(second),
            ),
            return_exceptions=True,
        )

        assert sum(isinstance(result, StorageOffsetMismatchError) for result in results) == 1
        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert (await storage.stat(temporary)).byte_size in {len(first), len(second)}

    asyncio.run(exercise())


def test_filesystem_storage_never_follows_namespace_symlink(tmp_path: Path) -> None:
    """A malicious namespace symlink cannot redirect operations outside STORAGE_ROOT."""

    async def exercise() -> None:
        root = tmp_path / "storage"
        outside = tmp_path / "outside"
        outside.mkdir()
        root.mkdir()
        os.symlink(outside, root / StorageNamespace.TEMPORARY.value)
        storage = FilesystemStorage(root)

        with pytest.raises(StorageIntegrityError):
            await storage.create_temporary(StorageKey.new(StorageNamespace.TEMPORARY))

        assert not tuple(outside.iterdir())

    asyncio.run(exercise())


def test_promotion_is_idempotent_only_when_final_digest_matches(tmp_path: Path) -> None:
    """Retry can finish a same-content promotion but cannot overwrite final bytes."""

    async def exercise() -> None:
        storage = FilesystemStorage(tmp_path / "storage")
        first_temporary = StorageKey.new(StorageNamespace.TEMPORARY)
        matching_temporary = StorageKey.new(StorageNamespace.TEMPORARY)
        conflicting_temporary = StorageKey.new(StorageNamespace.TEMPORARY)
        final = StorageKey.new(StorageNamespace.FINAL)
        first_payload = b"same content"
        conflicting_payload = b"different content"

        for key, payload in (
            (first_temporary, first_payload),
            (matching_temporary, first_payload),
            (conflicting_temporary, conflicting_payload),
        ):
            await storage.create_temporary(key)
            await storage.append(
                key,
                payload,
                expected_offset=0,
                checksum=sha256_bytes(payload),
            )
        await storage.promote(
            first_temporary,
            final,
            expected_sha256=sha256_bytes(first_payload),
        )
        await storage.promote(
            matching_temporary,
            final,
            expected_sha256=sha256_bytes(first_payload),
        )
        with pytest.raises(StorageConflictError):
            await storage.promote(
                conflicting_temporary,
                final,
                expected_sha256=sha256_bytes(conflicting_payload),
            )
        assert await storage.read_range(final, start=0, end=len(first_payload)) == first_payload

    asyncio.run(exercise())


def test_compensation_deletes_staged_object_after_domain_failure() -> None:
    """A failing surrounding transaction does not leave a stage object behind."""

    async def exercise() -> None:
        storage = InMemoryStorage()
        key = StorageKey.new(StorageNamespace.TEMPORARY)

        with pytest.raises(RuntimeError, match="database failed"):
            async with StorageCompensation(storage) as compensation:
                await storage.create_temporary(key)
                compensation.track(key)
                raise RuntimeError("database failed")

        with pytest.raises(StorageNotFoundError):
            await storage.stat(key)

    asyncio.run(exercise())


def test_compensation_propagates_cleanup_failure_without_domain_failure() -> None:
    """A caller can route an uncleaned object to later retry handling."""

    async def exercise() -> None:
        delegate = InMemoryStorage()
        storage = FailureStorage(delegate)
        key = StorageKey.new(StorageNamespace.TEMPORARY)
        await storage.create_temporary(key)
        storage.fail_next(StorageOperation.DELETE)

        with pytest.raises(StorageUnavailableError):
            async with StorageCompensation(storage) as compensation:
                compensation.track(key)

        assert (await delegate.stat(key)).byte_size == 0

    asyncio.run(exercise())


def test_failure_adapter_and_orphan_reconciler_are_deterministic() -> None:
    """Cleanup workers can classify failures and obtain non-mutating orphan candidates."""

    async def exercise() -> None:
        storage = InMemoryStorage()
        referenced = StorageKey.new(StorageNamespace.FINAL)
        orphan = StorageKey.new(StorageNamespace.FINAL)
        for key, payload in ((referenced, b"keep"), (orphan, b"remove")):
            temporary = StorageKey.new(StorageNamespace.TEMPORARY)
            await storage.create_temporary(temporary)
            await storage.append(
                temporary,
                payload,
                expected_offset=0,
                checksum=sha256_bytes(payload),
            )
            await storage.promote(temporary, key, expected_sha256=sha256_bytes(payload))

        reconciler = StorageReconciler(storage)
        assert await reconciler.find_orphans([referenced]) == (orphan,)
        assert classify_deletion_error(None) is DeletionDisposition.SUCCEEDED
        assert (
            classify_deletion_error(StorageUnavailableError())
            is DeletionDisposition.RETRYABLE_FAILURE
        )
        assert (
            classify_deletion_error(StorageIntegrityError())
            is DeletionDisposition.PERMANENT_FAILURE
        )

    asyncio.run(exercise())

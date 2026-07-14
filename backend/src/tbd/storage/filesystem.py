"""Development filesystem implementation of the private Storage contract."""

from __future__ import annotations

import asyncio
import fcntl
import os
import stat
from collections.abc import AsyncIterator
from pathlib import Path

from tbd.storage.contracts import (
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


class FilesystemStorage:
    """Store private keys under a single root without accepting filesystem paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    async def create_temporary(self, key: StorageKey) -> StorageObject:
        """Create a resumable empty temporary object, preserving existing bytes."""

        return await asyncio.to_thread(self._create_temporary_sync, key)

    async def append(
        self,
        key: StorageKey,
        data: bytes,
        *,
        expected_offset: int,
        checksum: str,
    ) -> StorageAppendResult:
        """Append one validated chunk only when the current size is expected."""

        return await asyncio.to_thread(
            self._append_sync,
            key,
            data,
            expected_offset,
            checksum,
        )

    async def promote(
        self,
        source: StorageKey,
        target: StorageKey,
        *,
        expected_sha256: str,
    ) -> StorageObject:
        """Promote an intact temporary object without overwriting final content."""

        return await asyncio.to_thread(self._promote_sync, source, target, expected_sha256)

    async def stat(self, key: StorageKey) -> StorageObject:
        """Return metadata for a private regular file."""

        return await asyncio.to_thread(self._stat_sync, key)

    async def read_range(self, key: StorageKey, *, start: int, end: int) -> bytes:
        """Read a checked half-open range without exposing an open file handle."""

        return await asyncio.to_thread(self._read_range_sync, key, start, end)

    async def delete(self, key: StorageKey) -> StorageDeleteResult:
        """Remove a private regular file, treating absence as a no-op."""

        return await asyncio.to_thread(self._delete_sync, key)

    async def _collect_keys(
        self,
        namespace: StorageNamespace | None,
    ) -> tuple[StorageKey, ...]:
        return await asyncio.to_thread(self._collect_keys_sync, namespace)

    async def _iter_keys(
        self,
        namespace: StorageNamespace | None,
    ) -> AsyncIterator[StorageKey]:
        for key in await self._collect_keys(namespace):
            yield key

    def iter_keys(
        self,
        namespace: StorageNamespace | None = None,
    ) -> AsyncIterator[StorageKey]:
        """Yield keys from the logical namespace, never physical paths."""

        return self._iter_keys(namespace)

    def _create_temporary_sync(self, key: StorageKey) -> StorageObject:
        self._require_namespace(key, StorageNamespace.TEMPORARY)
        path = self._path_for(key, create_namespace=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self._stat_sync(key)
        except OSError as exc:
            raise StorageUnavailableError() from exc
        else:
            os.close(descriptor)
        return self._stat_sync(key)

    def _append_sync(
        self,
        key: StorageKey,
        data: bytes,
        expected_offset: int,
        checksum: str,
    ) -> StorageAppendResult:
        self._require_namespace(key, StorageNamespace.TEMPORARY)
        if expected_offset < 0:
            raise StorageOffsetMismatchError(expected_offset, 0)
        checksum = validate_sha256(checksum)
        if sha256_bytes(data) != checksum:
            raise StorageIntegrityError()

        path = self._path_for(key)
        self._require_regular(path)
        try:
            with path.open("r+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    handle.seek(0, os.SEEK_END)
                    actual_offset = handle.tell()
                    if actual_offset != expected_offset:
                        raise StorageOffsetMismatchError(expected_offset, actual_offset)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except StorageOffsetMismatchError:
            raise
        except FileNotFoundError as exc:
            raise StorageNotFoundError() from exc
        except OSError as exc:
            raise StorageUnavailableError() from exc

        object_metadata = self._stat_sync(key)
        return StorageAppendResult(
            confirmed_offset=object_metadata.byte_size,
            sha256=object_metadata.sha256,
        )

    def _promote_sync(
        self,
        source: StorageKey,
        target: StorageKey,
        expected_sha256: str,
    ) -> StorageObject:
        self._require_namespace(source, StorageNamespace.TEMPORARY)
        self._require_namespace(target, StorageNamespace.FINAL)
        expected_sha256 = validate_sha256(expected_sha256)
        source_metadata = self._stat_sync(source)
        if source_metadata.sha256 != expected_sha256:
            raise StorageIntegrityError()

        source_path = self._path_for(source)
        target_path = self._path_for(target, create_namespace=True)
        try:
            os.link(source_path, target_path, follow_symlinks=False)
        except FileExistsError:
            target_metadata = self._stat_sync(target)
            if target_metadata.sha256 != expected_sha256:
                raise StorageConflictError() from None
        except FileNotFoundError as exc:
            raise StorageNotFoundError() from exc
        except OSError as exc:
            raise StorageUnavailableError() from exc
        else:
            target_metadata = self._stat_sync(target)

        try:
            source_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StorageUnavailableError() from exc
        return target_metadata

    def _stat_sync(self, key: StorageKey) -> StorageObject:
        path = self._path_for(key)
        self._require_regular(path)
        try:
            with path.open("rb") as handle:
                digest = sha256_bytes(handle.read())
            size = path.stat().st_size
        except FileNotFoundError as exc:
            raise StorageNotFoundError() from exc
        except OSError as exc:
            raise StorageUnavailableError() from exc
        return StorageObject(key=key, byte_size=size, sha256=digest)

    def _read_range_sync(self, key: StorageKey, start: int, end: int) -> bytes:
        metadata = self._stat_sync(key)
        if start < 0 or end < start or end > metadata.byte_size:
            raise StorageRangeError(start, end, metadata.byte_size)
        if start == end:
            return b""
        path = self._path_for(key)
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                return handle.read(end - start)
        except FileNotFoundError as exc:
            raise StorageNotFoundError() from exc
        except OSError as exc:
            raise StorageUnavailableError() from exc

    def _delete_sync(self, key: StorageKey) -> StorageDeleteResult:
        path = self._path_for(key)
        try:
            file_status = path.lstat()
        except FileNotFoundError:
            return StorageDeleteResult(removed=False)
        except OSError as exc:
            raise StorageUnavailableError() from exc
        if not stat.S_ISREG(file_status.st_mode):
            raise StorageIntegrityError()
        try:
            path.unlink()
        except FileNotFoundError:
            return StorageDeleteResult(removed=False)
        except OSError as exc:
            raise StorageUnavailableError() from exc
        return StorageDeleteResult(removed=True)

    def _collect_keys_sync(self, namespace: StorageNamespace | None) -> tuple[StorageKey, ...]:
        namespaces = (namespace,) if namespace is not None else tuple(StorageNamespace)
        keys: list[StorageKey] = []
        for current_namespace in namespaces:
            directory = self._namespace_directory(current_namespace, create=False)
            if not directory.exists():
                continue
            try:
                children = sorted(directory.iterdir(), key=lambda path: path.name)
            except OSError as exc:
                raise StorageUnavailableError() from exc
            for child in children:
                try:
                    key = StorageKey(namespace=current_namespace, identifier=child.name)
                    self._require_regular(child)
                except ValueError:
                    raise StorageIntegrityError() from None
                keys.append(key)
        return tuple(keys)

    def _path_for(self, key: StorageKey, *, create_namespace: bool = False) -> Path:
        directory = self._namespace_directory(key.namespace, create=create_namespace)
        path = directory / key.identifier
        if path.parent.exists():
            try:
                path.parent.resolve(strict=True).relative_to(self._root)
            except (FileNotFoundError, ValueError) as exc:
                raise StorageIntegrityError() from exc
        return path

    def _namespace_directory(self, namespace: StorageNamespace, *, create: bool) -> Path:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            directory = self._root / namespace.value
            if create:
                directory.mkdir(exist_ok=True)
            if directory.exists():
                directory_status = directory.lstat()
                if not stat.S_ISDIR(directory_status.st_mode):
                    raise StorageIntegrityError()
                directory.resolve(strict=True).relative_to(self._root)
            return directory
        except StorageIntegrityError:
            raise
        except (FileNotFoundError, ValueError) as exc:
            raise StorageIntegrityError() from exc
        except OSError as exc:
            raise StorageUnavailableError() from exc

    @staticmethod
    def _require_namespace(key: StorageKey, namespace: StorageNamespace) -> None:
        if key.namespace is not namespace:
            raise StorageConflictError()

    @staticmethod
    def _require_regular(path: Path) -> None:
        try:
            file_status = path.lstat()
        except FileNotFoundError as exc:
            raise StorageNotFoundError() from exc
        except OSError as exc:
            raise StorageUnavailableError() from exc
        if not stat.S_ISREG(file_status.st_mode):
            raise StorageIntegrityError()

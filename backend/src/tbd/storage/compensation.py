"""Best-effort object cleanup when a surrounding domain transaction aborts."""

from __future__ import annotations

from collections.abc import Sequence

from tbd.storage.contracts import Storage, StorageError, StorageKey


class StorageCompensation:
    """Track newly created keys until the surrounding service commits its DB work."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._tracked_keys: list[StorageKey] = []
        self._committed = False

    async def __aenter__(self) -> StorageCompensation:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        if self._committed:
            return False
        cleanup_errors = await self.rollback()
        if exc is not None:
            return False
        if cleanup_errors:
            raise cleanup_errors[0]
        return False

    def track(self, key: StorageKey) -> None:
        """Register an object that must be deleted unless ``commit`` is called."""

        if self._committed:
            raise RuntimeError("cannot track storage after compensation commit")
        if key not in self._tracked_keys:
            self._tracked_keys.append(key)

    def release(self, key: StorageKey) -> None:
        """Stop compensating a key that has already been removed or transferred."""

        self._tracked_keys = [tracked for tracked in self._tracked_keys if tracked != key]

    def commit(self) -> None:
        """Keep tracked objects because the surrounding domain transaction committed."""

        self._committed = True
        self._tracked_keys.clear()

    async def rollback(self) -> Sequence[StorageError]:
        """Best-effort reverse-order deletion without hiding a domain exception."""

        failures: list[StorageError] = []
        for key in reversed(self._tracked_keys):
            try:
                await self._storage.delete(key)
            except StorageError as exc:
                failures.append(exc)
        self._tracked_keys.clear()
        return tuple(failures)

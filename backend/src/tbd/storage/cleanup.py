"""Deletion classification and non-mutating orphan discovery primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from tbd.storage.contracts import Storage, StorageError, StorageKey, StorageNamespace


class DeletionDisposition(StrEnum):
    """Classification a later lifecycle worker can persist and schedule."""

    SUCCEEDED = "SUCCEEDED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


def classify_deletion_error(error: StorageError | None) -> DeletionDisposition:
    """Map a safe adapter result to a future deletion worker decision."""

    if error is None:
        return DeletionDisposition.SUCCEEDED
    if error.retryable:
        return DeletionDisposition.RETRYABLE_FAILURE
    return DeletionDisposition.PERMANENT_FAILURE


@dataclass(frozen=True, slots=True)
class StorageReconciler:
    """Compare Storage inventory with keys supplied by the owning domain query."""

    storage: Storage

    async def find_orphans(
        self,
        referenced_keys: Iterable[StorageKey],
        *,
        namespace: StorageNamespace | None = None,
    ) -> tuple[StorageKey, ...]:
        """Return unreferenced keys without deleting, logging, or exposing paths."""

        referenced = set(referenced_keys)
        orphans: list[StorageKey] = []
        async for key in self.storage.iter_keys(namespace):
            if key not in referenced:
                orphans.append(key)
        return tuple(orphans)

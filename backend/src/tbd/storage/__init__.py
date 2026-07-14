"""Provider-neutral private object storage primitives."""

from tbd.storage.cleanup import DeletionDisposition, StorageReconciler, classify_deletion_error
from tbd.storage.compensation import StorageCompensation
from tbd.storage.contracts import (
    Storage,
    StorageAppendResult,
    StorageConflictError,
    StorageDeleteResult,
    StorageError,
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
from tbd.storage.filesystem import FilesystemStorage
from tbd.storage.testing import FailureStorage, InMemoryStorage, StorageOperation

__all__ = [
    "DeletionDisposition",
    "FailureStorage",
    "Storage",
    "StorageAppendResult",
    "StorageCompensation",
    "StorageConflictError",
    "StorageDeleteResult",
    "StorageError",
    "FilesystemStorage",
    "InMemoryStorage",
    "StorageIntegrityError",
    "StorageKey",
    "StorageNamespace",
    "StorageNotFoundError",
    "StorageObject",
    "StorageOffsetMismatchError",
    "StorageOperation",
    "StorageRangeError",
    "StorageReconciler",
    "StorageUnavailableError",
    "classify_deletion_error",
    "sha256_bytes",
    "validate_sha256",
]

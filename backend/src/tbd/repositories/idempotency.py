"""PostgreSQL persistence for idempotent HTTP mutation records."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.core.crypto import EncryptedPayload, ResponseCipher
from tbd.models.consistency import IdempotencyRecord

IdempotencyState = Literal["PROCESSING", "COMPLETED", "FAILED"]


@dataclass(frozen=True)
class IdempotencyRequest:
    """Stable request identity used for one durable mutation response."""

    user_id: UUID
    method: str
    route_key: str
    key_hash: bytes
    request_hash: bytes
    session_id: UUID | None = None
    purge_on_session_end: bool = False


@dataclass(frozen=True)
class AcquiredIdempotencyRecord:
    """Caller owns an active record and may perform the domain mutation."""

    record_id: UUID


@dataclass(frozen=True)
class ReplayIdempotencyRecord:
    """A terminal record supplies the exact stored HTTP response."""

    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True)
class ProcessingIdempotencyRecord:
    """Another request owns the in-flight domain mutation."""

    record_id: UUID


IdempotencyAcquireResult = (
    AcquiredIdempotencyRecord | ReplayIdempotencyRecord | ProcessingIdempotencyRecord
)


class IdempotencyKeyReusedError(Exception):
    """The same idempotency key was used for a semantically different request."""


class IdempotencyRepository:
    """Lock and persist one request scope without storing its raw key."""

    terminal_ttl = timedelta(hours=24)

    def __init__(self, cipher: ResponseCipher) -> None:
        self._cipher = cipher

    async def acquire(
        self,
        session: AsyncSession,
        request: IdempotencyRequest,
        *,
        now: datetime | None = None,
        processing_lease: timedelta,
    ) -> IdempotencyAcquireResult:
        """Acquire an active record, replay a terminal response, or observe a live owner."""

        timestamp = now or datetime.now(UTC)
        record = await self._lock_existing(session, request)
        inserted = False
        if record is None:
            record, inserted = await self._insert_or_lock_existing(
                session, request, timestamp, processing_lease
            )

        if record.request_hash != request.request_hash:
            raise IdempotencyKeyReusedError

        if inserted:
            return AcquiredIdempotencyRecord(record_id=record.id)

        if record.state in {"COMPLETED", "FAILED"}:
            if record.expires_at is not None and record.expires_at <= timestamp:
                await session.delete(record)
                await session.flush()
                return await self.acquire(
                    session,
                    request,
                    now=timestamp,
                    processing_lease=processing_lease,
                )
            return self._replay(record)

        if record.locked_until is not None and record.locked_until > timestamp:
            return ProcessingIdempotencyRecord(record_id=record.id)

        record.locked_until = timestamp + processing_lease
        await session.flush()
        return AcquiredIdempotencyRecord(record_id=record.id)

    async def complete(
        self,
        session: AsyncSession,
        *,
        record_id: UUID,
        status_code: int,
        body: dict[str, Any],
        failed: bool = False,
        now: datetime | None = None,
    ) -> None:
        """Store an encrypted terminal response in the same domain transaction."""

        timestamp = now or datetime.now(UTC)
        record = await session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.id == record_id).with_for_update()
        )
        if record is None:
            raise LookupError("idempotency record does not exist")
        if record.state != "PROCESSING":
            raise ValueError("idempotency record is already terminal")
        if record.created_at > timestamp:
            timestamp = record.created_at

        plaintext = json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encrypted = self._cipher.encrypt(plaintext)
        record.state = "FAILED" if failed else "COMPLETED"
        record.locked_until = None
        record.response_status = status_code
        record.response_body_ciphertext = encrypted.ciphertext
        record.response_body_nonce = encrypted.nonce
        record.response_key_version = encrypted.key_version
        record.completed_at = timestamp
        record.expires_at = timestamp + self.terminal_ttl
        await session.flush()

    async def mark_live_ai_purged(
        self,
        session: AsyncSession,
        *,
        records: list[IdempotencyRecord],
        now: datetime | None = None,
    ) -> None:
        """Replace stale personal-LIVE replay bodies without shortening their TTL.

        The original accepted resource is gone after ``LIVE → PROCESSING``.  A
        stored 202/201 would point clients at an intentionally deleted private
        resource, so only an already-terminal purge-scoped request is rewritten.
        In-flight rows remain owned by their request transaction and will fail its
        Session-state recheck instead of becoming a misleading replay.
        """

        timestamp = now or datetime.now(UTC)
        body = {
            "error": {
                "code": "LIVE_AI_RESULT_PURGED",
                "message": "수업 종료로 개인 AI 결과가 삭제되었습니다.",
                "details": None,
            }
        }
        plaintext = json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encrypted = self._cipher.encrypt(plaintext)
        for record in records:
            if record.state not in {"COMPLETED", "FAILED"}:
                continue
            record.state = "FAILED"
            record.locked_until = None
            record.response_status = 410
            record.response_body_ciphertext = encrypted.ciphertext
            record.response_body_nonce = encrypted.nonce
            record.response_key_version = encrypted.key_version
            # Retention is anchored at the accepted request's terminal time,
            # rather than extending the user's private-data retention window.
            if record.completed_at is None:
                record.completed_at = timestamp
            if record.expires_at is None:
                record.expires_at = record.completed_at + self.terminal_ttl
        await session.flush()

    async def _lock_existing(
        self,
        session: AsyncSession,
        request: IdempotencyRequest,
    ) -> IdempotencyRecord | None:
        return await session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == request.user_id,
                IdempotencyRecord.http_method == request.method,
                IdempotencyRecord.route_key == request.route_key,
                IdempotencyRecord.idempotency_key_hash == request.key_hash,
            )
            .with_for_update()
        )

    async def _insert_or_lock_existing(
        self,
        session: AsyncSession,
        request: IdempotencyRequest,
        now: datetime,
        processing_lease: timedelta,
    ) -> tuple[IdempotencyRecord, bool]:
        statement = (
            insert(IdempotencyRecord)
            .values(
                user_id=request.user_id,
                session_id=request.session_id,
                purge_on_session_end=request.purge_on_session_end,
                http_method=request.method,
                route_key=request.route_key,
                idempotency_key_hash=request.key_hash,
                request_hash=request.request_hash,
                locked_until=now + processing_lease,
            )
            .on_conflict_do_nothing(
                constraint="idempotency_records_request_uq",
            )
            .returning(IdempotencyRecord.id)
        )
        record_id = await session.scalar(statement)
        if record_id is not None:
            record = await session.scalar(
                select(IdempotencyRecord).where(IdempotencyRecord.id == record_id).with_for_update()
            )
            assert record is not None
            return record, True

        record = await self._lock_existing(session, request)
        assert record is not None
        return record, False

    def _replay(self, record: IdempotencyRecord) -> ReplayIdempotencyRecord:
        if (
            record.response_status is None
            or record.response_body_ciphertext is None
            or record.response_body_nonce is None
            or record.response_key_version is None
        ):
            raise ValueError("terminal idempotency record has no encrypted response")
        payload = EncryptedPayload(
            ciphertext=record.response_body_ciphertext,
            nonce=record.response_body_nonce,
            key_version=record.response_key_version,
        )
        body = json.loads(self._cipher.decrypt(payload))
        if not isinstance(body, dict):
            raise ValueError("idempotency response body must decode to an object")
        return ReplayIdempotencyRecord(status_code=record.response_status, body=body)

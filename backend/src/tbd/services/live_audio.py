"""Live PCM publisher ownership and durable stream progress."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto
from tbd.core.config import Settings
from tbd.jobs.kernel import JobKernel
from tbd.models.courses import CourseMember
from tbd.models.materials import (
    SessionRecording,
    TranscriptGap,
    TranscriptSegment,
    TranscriptVersion,
)
from tbd.models.sessions import LectureSession
from tbd.providers.stt import STTFinal
from tbd.realtime.audio import AudioFrame
from tbd.repositories.outbox import OutboxRepository
from tbd.services.knowledge import enqueue_knowledge_indexing

LIVE_AUDIO_LEASE = timedelta(seconds=45)


class LiveAudioSessionNotFoundError(Exception):
    """The requested Session does not exist."""


class LiveAudioAccessDeniedError(Exception):
    """The user is not the Course professor for this Session."""


class LiveAudioSessionClosingError(Exception):
    """New audio cannot be accepted outside the LIVE Session state."""


class AudioPublisherConflictError(Exception):
    """Another opaque client stream already owns the Session publisher claim."""


class AudioResumeRejectedError(Exception):
    """The persistent ACK watermark cannot safely resume the requested stream."""


class AudioServerStateLostError(Exception):
    """A prior accepted frame has no durable processing completion after reconnect."""


@dataclass(frozen=True)
class AudioFrameAcceptance:
    """The durable ACK watermark after one frame is accepted or deduplicated."""

    duplicate: bool
    sequence_gap: bool
    last_received_sequence: int
    last_processed_sequence: int


@dataclass(frozen=True)
class AudioPublisherClaim:
    """Safe start response values; the client stream ID itself is never returned."""

    recording_id: UUID
    stream_id: UUID
    publisher_status: str
    last_received_sequence: int
    last_processed_sequence: int


@dataclass(frozen=True)
class PersistedTranscriptFinal:
    """A final Segment that is safe to publish only after its transaction commits."""

    id: UUID
    session_id: UUID
    transcript_version_id: UUID
    sequence: int
    start_ms: int
    end_ms: int
    text: str
    created_at: datetime
    utterance_id: str


@dataclass(frozen=True)
class AudioStreamProgress:
    """Current durable watermarks for the explicit audio.stop acknowledgement."""

    last_received_sequence: int
    last_processed_sequence: int
    last_final_transcript_sequence: int


class LiveAudioService:
    """Serialize one Session publisher claim under the Session row lock."""

    def __init__(self, settings: Settings, outbox: OutboxRepository | None = None) -> None:
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())
        self._outbox = outbox or OutboxRepository()
        self._kernel = JobKernel(outbox=self._outbox)

    async def claim_publisher(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        client_stream_id: str,
        resume_from_sequence: int | None,
        now: datetime | None = None,
    ) -> AudioPublisherClaim:
        """Claim or reconnect the one permitted publisher without plaintext retention."""

        timestamp = now or datetime.now(UTC)
        lecture_session = await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )
        if lecture_session is None:
            raise LiveAudioSessionNotFoundError
        if lecture_session.status != "LIVE":
            raise LiveAudioSessionClosingError
        role = await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == lecture_session.course_id,
                CourseMember.user_id == user_id,
            )
        )
        if role != "PROFESSOR":
            raise LiveAudioAccessDeniedError

        stream_hash = self._crypto.hash_token("live-audio-publisher", client_stream_id)
        recording = await session.scalar(
            select(SessionRecording)
            .where(SessionRecording.session_id == session_id)
            .with_for_update()
        )
        if recording is None:
            if resume_from_sequence is not None:
                raise AudioResumeRejectedError
            recording = SessionRecording(
                id=uuid4(),
                session_id=session_id,
                publisher_user_id=user_id,
                publisher_client_stream_id_hash=stream_hash,
                status="CAPTURING",
                last_received_sequence=-1,
                last_processed_sequence=-1,
                last_captured_offset_ms=0,
                live_audio_lease_expires_at=timestamp + LIVE_AUDIO_LEASE,
                version=1,
            )
            session.add(recording)
            await session.flush()
            return AudioPublisherClaim(
                recording_id=recording.id,
                stream_id=recording.id,
                publisher_status="CLAIMED",
                last_received_sequence=recording.last_received_sequence,
                last_processed_sequence=recording.last_processed_sequence,
            )

        if recording.publisher_client_stream_id_hash != stream_hash:
            raise AudioPublisherConflictError
        if recording.status != "CAPTURING":
            raise LiveAudioSessionClosingError
        expected_resume_sequence = (
            None if recording.last_received_sequence < 0 else recording.last_received_sequence
        )
        if resume_from_sequence != expected_resume_sequence:
            raise AudioResumeRejectedError
        if recording.last_processed_sequence < recording.last_received_sequence:
            raise AudioServerStateLostError
        recording.live_audio_lease_expires_at = timestamp + LIVE_AUDIO_LEASE
        recording.version += 1
        await session.flush()
        return AudioPublisherClaim(
            recording_id=recording.id,
            stream_id=recording.id,
            publisher_status="RESUMED",
            last_received_sequence=recording.last_received_sequence,
            last_processed_sequence=recording.last_processed_sequence,
        )

    async def accept_frame(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        recording_id: UUID,
        frame: AudioFrame,
        now: datetime | None = None,
    ) -> AudioFrameAcceptance:
        """Persist the receive watermark before handing PCM to an external provider."""

        timestamp = now or datetime.now(UTC)
        lecture_session = await self._lock_live_or_draining_session(session, session_id)
        recording = await self._lock_recording(
            session, session_id=session_id, recording_id=recording_id
        )
        if lecture_session.status != "LIVE" or recording.status != "CAPTURING":
            raise LiveAudioSessionClosingError
        if frame.sequence <= recording.last_received_sequence:
            return AudioFrameAcceptance(
                duplicate=True,
                sequence_gap=False,
                last_received_sequence=recording.last_received_sequence,
                last_processed_sequence=recording.last_processed_sequence,
            )

        sequence_gap = (
            recording.last_received_sequence >= 0
            and frame.sequence > recording.last_received_sequence + 1
        )
        if sequence_gap:
            await self._append_live_gap(
                session,
                lecture_session=lecture_session,
                start_ms=recording.last_captured_offset_ms + 500,
                end_ms=frame.captured_offset_ms,
                reason="SEQUENCE_GAP",
            )
        recording.last_received_sequence = frame.sequence
        recording.last_captured_offset_ms = frame.captured_offset_ms
        recording.live_audio_lease_expires_at = timestamp + LIVE_AUDIO_LEASE
        await session.flush()
        return AudioFrameAcceptance(
            duplicate=False,
            sequence_gap=sequence_gap,
            last_received_sequence=recording.last_received_sequence,
            last_processed_sequence=recording.last_processed_sequence,
        )

    async def mark_processed(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        recording_id: UUID,
        sequence: int,
    ) -> AudioFrameAcceptance:
        """Advance only after a provider accepted the frame, never beyond received ACKs."""

        recording = await self._lock_recording(
            session, session_id=session_id, recording_id=recording_id
        )
        if sequence > recording.last_processed_sequence:
            recording.last_processed_sequence = min(sequence, recording.last_received_sequence)
            await session.flush()
        return AudioFrameAcceptance(
            duplicate=False,
            sequence_gap=False,
            last_received_sequence=recording.last_received_sequence,
            last_processed_sequence=recording.last_processed_sequence,
        )

    async def persist_final(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        recording_id: UUID,
        result: STTFinal,
    ) -> PersistedTranscriptFinal | None:
        """Insert a final Segment and its public Outbox event in one short transaction."""

        lecture_session = await self._lock_live_or_draining_session(session, session_id)
        recording = await self._lock_recording(
            session, session_id=session_id, recording_id=recording_id
        )
        if recording.status != "CAPTURING":
            if lecture_session.status == "PROCESSING":
                await self._append_live_gap(
                    session,
                    lecture_session=lecture_session,
                    start_ms=result.start_ms,
                    end_ms=result.end_ms,
                    reason="BACKPRESSURE_DROP",
                    is_final=True,
                )
            return None
        live_version = await self._lock_live_version(session, lecture_session.id)
        if live_version.status != "FINALIZING":
            return None
        existing = await session.scalar(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.transcript_version_id == live_version.id,
                TranscriptSegment.utterance_id == result.utterance_id,
            )
            .with_for_update()
        )
        if existing is not None:
            return self._project_final(existing)

        live_version.last_sequence += 1
        segment = TranscriptSegment(
            id=uuid4(),
            session_id=lecture_session.id,
            transcript_version_id=live_version.id,
            sequence=live_version.last_sequence,
            utterance_id=result.utterance_id,
            start_ms=result.start_ms,
            end_ms=result.end_ms,
            text=result.text.strip(),
        )
        session.add(segment)
        await session.flush()
        await session.refresh(segment)
        projection = self._project_final(segment)
        await self._outbox.enqueue(
            session,
            session_id=lecture_session.id,
            partition_key=f"session:{lecture_session.id}",
            event_type="transcript.final",
            resource_version=None,
            payload={
                "utterance_id": projection.utterance_id,
                "segment": self._final_event_segment(projection),
            },
        )
        await enqueue_knowledge_indexing(
            session,
            session_id=lecture_session.id,
            kernel=self._kernel,
        )
        return projection

    async def get_progress(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        recording_id: UUID,
    ) -> AudioStreamProgress:
        """Read the current ACK and durable final watermark without exposing PCM state."""

        recording = await self._lock_recording(
            session, session_id=session_id, recording_id=recording_id
        )
        live_version = await self._lock_live_version(session, session_id)
        last_final = await session.scalar(
            select(func.max(TranscriptSegment.sequence)).where(
                TranscriptSegment.transcript_version_id == live_version.id
            )
        )
        return AudioStreamProgress(
            last_received_sequence=recording.last_received_sequence,
            last_processed_sequence=recording.last_processed_sequence,
            last_final_transcript_sequence=last_final if last_final is not None else -1,
        )

    async def record_resume_rejection(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        recording_id: UUID | None = None,
        reason: str = "SEQUENCE_GAP",
    ) -> None:
        """Keep an observable Gap when a client cannot resume the persistent watermark."""

        lecture_session = await self._lock_live_or_draining_session(session, session_id)
        recording_statement = select(SessionRecording).where(
            SessionRecording.session_id == session_id
        )
        if recording_id is not None:
            recording_statement = recording_statement.where(SessionRecording.id == recording_id)
        recording = await session.scalar(recording_statement.with_for_update())
        if recording is None:
            return
        await self._append_live_gap(
            session,
            lecture_session=lecture_session,
            start_ms=recording.last_captured_offset_ms,
            end_ms=recording.last_captured_offset_ms,
            reason=reason,
        )

    async def _lock_live_or_draining_session(
        self, session: AsyncSession, session_id: UUID
    ) -> LectureSession:
        lecture_session = await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )
        if lecture_session is None:
            raise LiveAudioSessionNotFoundError
        if lecture_session.status not in {"LIVE", "PROCESSING"}:
            raise LiveAudioSessionClosingError
        return lecture_session

    async def _lock_recording(
        self, session: AsyncSession, *, session_id: UUID, recording_id: UUID
    ) -> SessionRecording:
        recording = await session.scalar(
            select(SessionRecording)
            .where(
                SessionRecording.id == recording_id,
                SessionRecording.session_id == session_id,
            )
            .with_for_update()
        )
        if recording is None:
            raise LiveAudioSessionClosingError
        return recording

    async def _lock_live_version(
        self, session: AsyncSession, session_id: UUID
    ) -> TranscriptVersion:
        version = await session.scalar(
            select(TranscriptVersion)
            .where(
                TranscriptVersion.session_id == session_id,
                TranscriptVersion.source == "LIVE",
            )
            .with_for_update()
        )
        if version is None:
            raise LiveAudioSessionClosingError
        return version

    async def _append_live_gap(
        self,
        session: AsyncSession,
        *,
        lecture_session: LectureSession,
        start_ms: int,
        end_ms: int,
        reason: str,
        is_final: bool = False,
    ) -> None:
        version = await self._lock_live_version(session, lecture_session.id)
        session.add(
            TranscriptGap(
                id=uuid4(),
                session_id=lecture_session.id,
                transcript_version_id=version.id,
                start_ms=min(start_ms, end_ms),
                end_ms=max(start_ms, end_ms),
                is_final=is_final,
                reason=reason,
                details={},
            )
        )
        await session.flush()

    @staticmethod
    def _project_final(segment: TranscriptSegment) -> PersistedTranscriptFinal:
        assert segment.created_at is not None
        assert segment.utterance_id is not None
        return PersistedTranscriptFinal(
            id=segment.id,
            session_id=segment.session_id,
            transcript_version_id=segment.transcript_version_id,
            sequence=segment.sequence,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            text=segment.text,
            created_at=segment.created_at,
            utterance_id=segment.utterance_id,
        )

    @staticmethod
    def _final_event_segment(segment: PersistedTranscriptFinal) -> dict[str, object]:
        return {
            "id": str(segment.id),
            "session_id": str(segment.session_id),
            "transcript_version_id": str(segment.transcript_version_id),
            "item_type": "SEGMENT",
            "sequence": segment.sequence,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "recording_start_ms": None,
            "recording_end_ms": None,
            "text": segment.text,
            "created_at": segment.created_at.isoformat(),
        }

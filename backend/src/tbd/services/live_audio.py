"""Live PCM publisher ownership and durable stream progress."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.auth.security import AuthCrypto
from tbd.core.config import Settings
from tbd.models.courses import CourseMember
from tbd.models.materials import SessionRecording
from tbd.models.sessions import LectureSession

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


@dataclass(frozen=True)
class AudioPublisherClaim:
    """Safe start response values; the client stream ID itself is never returned."""

    recording_id: UUID
    stream_id: UUID
    publisher_status: str
    last_received_sequence: int
    last_processed_sequence: int


class LiveAudioService:
    """Serialize one Session publisher claim under the Session row lock."""

    def __init__(self, settings: Settings) -> None:
        self._crypto = AuthCrypto(settings.auth_secret_key.get_secret_value())

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
        if resume_from_sequence != recording.last_received_sequence:
            raise AudioResumeRejectedError
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

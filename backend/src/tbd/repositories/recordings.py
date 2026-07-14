"""Persistence queries for the Session Recording aggregate and upload manifest."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.models.courses import CourseMember
from tbd.models.materials import RecordingUpload, SessionRecording, TranscriptVersion
from tbd.models.sessions import LectureSession


class RecordingRepository:
    """Centralize Recording lock order: Session, Recording, then Upload."""

    async def get_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.scalar(select(LectureSession).where(LectureSession.id == session_id))

    async def lock_session(self, session: AsyncSession, session_id: UUID) -> LectureSession | None:
        return await session.scalar(
            select(LectureSession).where(LectureSession.id == session_id).with_for_update()
        )

    async def member_role(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
    ) -> str | None:
        return await session.scalar(
            select(CourseMember.role).where(
                CourseMember.course_id == course_id,
                CourseMember.user_id == user_id,
            )
        )

    async def get_recording(
        self, session: AsyncSession, recording_id: UUID
    ) -> SessionRecording | None:
        return await session.scalar(
            select(SessionRecording).where(SessionRecording.id == recording_id)
        )

    async def get_recording_for_session(
        self, session: AsyncSession, *, session_id: UUID
    ) -> SessionRecording | None:
        return await session.scalar(
            select(SessionRecording).where(SessionRecording.session_id == session_id)
        )

    async def get_recording_for_member(
        self,
        session: AsyncSession,
        *,
        recording_id: UUID,
        user_id: UUID,
    ) -> SessionRecording | None:
        return await session.scalar(
            select(SessionRecording)
            .join(LectureSession, LectureSession.id == SessionRecording.session_id)
            .join(CourseMember, CourseMember.course_id == LectureSession.course_id)
            .where(
                SessionRecording.id == recording_id,
                SessionRecording.deleted_at.is_(None),
                CourseMember.user_id == user_id,
            )
        )

    async def lock_recording_for_session(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
    ) -> SessionRecording | None:
        return await session.scalar(
            select(SessionRecording)
            .where(SessionRecording.session_id == session_id)
            .with_for_update()
        )

    async def get_upload(self, session: AsyncSession, upload_id: UUID) -> RecordingUpload | None:
        return await session.scalar(select(RecordingUpload).where(RecordingUpload.id == upload_id))

    async def lock_upload(
        self,
        session: AsyncSession,
        *,
        upload_id: UUID,
    ) -> RecordingUpload | None:
        return await session.scalar(
            select(RecordingUpload).where(RecordingUpload.id == upload_id).with_for_update()
        )

    async def lock_active_upload(
        self,
        session: AsyncSession,
        *,
        recording_id: UUID,
    ) -> RecordingUpload | None:
        return await session.scalar(
            select(RecordingUpload)
            .where(
                RecordingUpload.recording_id == recording_id,
                RecordingUpload.status == "ACTIVE",
            )
            .with_for_update()
        )

    async def next_transcript_version(self, session: AsyncSession, *, session_id: UUID) -> int:
        current = await session.scalar(
            select(func.max(TranscriptVersion.version)).where(
                TranscriptVersion.session_id == session_id
            )
        )
        return int(current or 0) + 1

    async def referenced_storage_values(
        self, session: AsyncSession, *, now: datetime
    ) -> tuple[str, ...]:
        """Return only live domain references for non-destructive reconciliation."""

        final_keys = list(
            await session.scalars(
                select(SessionRecording.storage_key).where(
                    SessionRecording.status == "UPLOADED",
                    SessionRecording.storage_key.is_not(None),
                )
            )
        )
        temporary_keys = list(
            await session.scalars(
                select(RecordingUpload.temporary_storage_key).where(
                    RecordingUpload.status == "ACTIVE",
                    RecordingUpload.expires_at > now,
                )
            )
        )
        return tuple(key for key in (*final_keys, *temporary_keys) if key is not None)

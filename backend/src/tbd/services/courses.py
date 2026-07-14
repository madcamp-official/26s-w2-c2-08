"""Course creation, joining, role, and join-code rotation policies."""

import re
import secrets
import string
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tbd.core.crypto import CourseJoinCodeCodec, EncryptedPayload
from tbd.models.courses import Course, CourseMember
from tbd.models.enums import CourseMemberRole
from tbd.repositories.courses import CourseRepository, CourseView

JOIN_CODE_PATTERN = re.compile(r"^[A-Z]{6}$", re.ASCII)
JOIN_CODE_ALPHABET = string.ascii_uppercase
JOIN_CODE_GENERATION_ATTEMPTS = 12


class CourseNotFoundError(Exception):
    """A Course or join code cannot be safely exposed to this requester."""


class CourseAccessDeniedError(Exception):
    """The user is not a member of an existing Course."""


class CourseRoleRequiredError(Exception):
    """The requested mutation requires the immutable Course owner."""


class MembershipConflictError(Exception):
    """A Course professor tried to join their own Course as a student."""


class JoinCodeGenerationError(Exception):
    """A unique join code could not be generated within the bounded retry policy."""


@dataclass(frozen=True)
class JoinCourseResult:
    view: CourseView
    created: bool


class CourseService:
    """Apply Course aggregate invariants inside a caller-owned transaction."""

    def __init__(
        self,
        codec: CourseJoinCodeCodec,
        repository: CourseRepository | None = None,
    ) -> None:
        self.codec = codec
        self.repository = repository or CourseRepository()

    @staticmethod
    def normalize_join_code(value: str) -> str:
        normalized = value.strip().upper()
        if JOIN_CODE_PATTERN.fullmatch(normalized) is None:
            raise CourseNotFoundError
        return normalized

    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        title: str,
        semester: str,
    ) -> tuple[CourseView, str]:
        normalized_title = title.strip()
        normalized_semester = semester.strip()
        if not normalized_title or not normalized_semester:
            raise ValueError("Course title and semester must not be blank")

        for _ in range(JOIN_CODE_GENERATION_ATTEMPTS):
            join_code = self._generate_join_code()
            lookup_hash = self.codec.lookup_hash(join_code)
            if await self.repository.lookup_hash_exists(session, lookup_hash):
                continue

            course_id = uuid4()
            encrypted = self.codec.encrypt(join_code, course_id=str(course_id))
            course = Course(
                id=course_id,
                title=normalized_title,
                semester=normalized_semester,
                created_by_user_id=user_id,
                join_code_lookup_hash=lookup_hash,
                join_code_lookup_key_version=self.codec.lookup_key_version,
                join_code_ciphertext=encrypted.ciphertext,
                join_code_nonce=encrypted.nonce,
                join_code_key_version=encrypted.key_version,
            )
            membership = CourseMember(
                course_id=course_id,
                user_id=user_id,
                role=CourseMemberRole.PROFESSOR,
            )
            try:
                async with session.begin_nested():
                    session.add_all((course, membership))
                    await session.flush()
            except IntegrityError as exc:
                constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
                if getattr(constraint_name, "constraint_name", None) == (
                    "courses_join_code_lookup_hash_uq"
                ):
                    continue
                raise

            return (
                CourseView(course=course, role=CourseMemberRole.PROFESSOR, current_session=None),
                join_code,
            )
        raise JoinCodeGenerationError

    async def join(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        raw_join_code: str,
    ) -> JoinCourseResult:
        normalized = self.normalize_join_code(raw_join_code)
        course = await self.repository.lock_by_join_code_hash(
            session,
            self.codec.lookup_hash(normalized),
        )
        if course is None:
            raise CourseNotFoundError

        membership = await self.repository.get_membership(
            session,
            course_id=course.id,
            user_id=user_id,
        )
        if membership is not None:
            if membership.role == CourseMemberRole.PROFESSOR:
                raise MembershipConflictError
            view = await self.repository.get_view_for_user(
                session,
                course_id=course.id,
                user_id=user_id,
            )
            assert view is not None
            return JoinCourseResult(view=view, created=False)

        session.add(
            CourseMember(
                course_id=course.id,
                user_id=user_id,
                role=CourseMemberRole.STUDENT,
            )
        )
        await session.flush()
        view = await self.repository.get_view_for_user(
            session,
            course_id=course.id,
            user_id=user_id,
        )
        assert view is not None
        return JoinCourseResult(view=view, created=True)

    async def get_for_member(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
    ) -> CourseView:
        view = await self.repository.get_view_for_user(
            session,
            course_id=course_id,
            user_id=user_id,
        )
        if view is not None:
            return view
        if await self.repository.course_exists(session, course_id):
            raise CourseAccessDeniedError
        raise CourseNotFoundError

    async def rotate_join_code(
        self,
        session: AsyncSession,
        *,
        course_id: UUID,
        user_id: UUID,
    ) -> tuple[CourseView, str]:
        course = await self.repository.lock_course(session, course_id)
        if course is None:
            raise CourseNotFoundError
        membership = await self.repository.get_membership(
            session,
            course_id=course_id,
            user_id=user_id,
        )
        if (
            membership is None
            or membership.role != CourseMemberRole.PROFESSOR
            or course.created_by_user_id != user_id
        ):
            raise CourseRoleRequiredError

        for _ in range(JOIN_CODE_GENERATION_ATTEMPTS):
            join_code = self._generate_join_code()
            lookup_hash = self.codec.lookup_hash(join_code)
            if await self.repository.lookup_hash_exists(session, lookup_hash):
                continue
            encrypted = self.codec.encrypt(join_code, course_id=str(course.id))
            self._replace_join_code(course, lookup_hash, encrypted)
            await session.flush()
            view = await self.repository.get_view_for_user(
                session,
                course_id=course.id,
                user_id=user_id,
            )
            assert view is not None
            return view, join_code
        raise JoinCodeGenerationError

    def reveal_join_code(self, course: Course) -> str:
        return self.codec.decrypt(
            EncryptedPayload(
                ciphertext=course.join_code_ciphertext,
                nonce=course.join_code_nonce,
                key_version=course.join_code_key_version,
            ),
            course_id=str(course.id),
        )

    @staticmethod
    def _generate_join_code() -> str:
        return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(6))

    def _replace_join_code(
        self,
        course: Course,
        lookup_hash: bytes,
        encrypted: EncryptedPayload,
    ) -> None:
        course.join_code_lookup_hash = lookup_hash
        course.join_code_lookup_key_version = self.codec.lookup_key_version
        course.join_code_ciphertext = encrypted.ciphertext
        course.join_code_nonce = encrypted.nonce
        course.join_code_key_version = encrypted.key_version
        course.version += 1

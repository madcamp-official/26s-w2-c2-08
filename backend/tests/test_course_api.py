"""Integration coverage for Course membership, join codes, and concurrency."""

import asyncio
import base64
import re
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.courses import Course, CourseMember
from tbd.services.courses import CourseNotFoundError, CourseService

pytestmark = pytest.mark.integration
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        auth_allowed_origins="http://localhost:5173",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )


async def _seed_users(database_url: str, count: int) -> list[UUID]:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            ids = []
            for index in range(count):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"course-user-{index}-{uuid4().hex[:8]}",
                        "email": f"course-user-{index}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                ids.append(user_id)
            return ids
    finally:
        await database.dispose()


def test_course_api_enforces_roles_hides_codes_and_rotates_atomically(
    migrated_database_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One account can hold Course roles safely without exposing student join codes."""

    owner_id, student_id, outsider_id, late_student_id = asyncio.run(
        _seed_users(migrated_database_url, 4)
    )
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": owner_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    with TestClient(app) as client:
        missing_origin = client.post(
            "/api/v1/courses",
            json={"title": "알고리즘", "semester": "2026 여름학기"},
        )
        assert missing_origin.status_code == 403
        assert missing_origin.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"

        create_headers = {
            **TRUSTED_ORIGIN,
            "Idempotency-Key": "create-course-integration-001",
        }
        first = client.post(
            "/api/v1/courses",
            headers=create_headers,
            json={"title": " 알고리즘 ", "semester": " 2026 여름학기 "},
        )
        replay = client.post(
            "/api/v1/courses",
            headers=create_headers,
            json={"title": "알고리즘", "semester": "2026 여름학기"},
        )
        assert first.status_code == 201
        assert replay.status_code == 201
        assert replay.json() == first.json()
        course_id = first.json()["id"]
        old_code = first.json()["join_code"]
        assert re.fullmatch(r"[A-Z]{6}", old_code)
        assert first.json()["role"] == "PROFESSOR"
        assert first.json()["current_session"] is None

        current_user["id"] = student_id
        joined = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": f"  {old_code.lower()}  "},
        )
        joined_again = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": old_code},
        )
        assert joined.status_code == 201
        assert joined_again.status_code == 200
        assert joined.json()["role"] == "STUDENT"
        assert "join_code" not in joined.json()

        student_detail = client.get(f"/api/v1/courses/{course_id}")
        student_list = client.get("/api/v1/courses", params={"role": "STUDENT"})
        assert student_detail.status_code == 200
        assert "join_code" not in student_detail.json()
        assert len(student_list.json()["items"]) == 1
        assert "join_code" not in student_list.json()["items"][0]

        student_rotate = client.post(
            f"/api/v1/courses/{course_id}/join-code/rotate",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "student-rotate-denied"},
        )
        assert student_rotate.status_code == 403
        assert student_rotate.json()["error"]["code"] == "ROLE_REQUIRED"

        current_user["id"] = outsider_id
        outsider_detail = client.get(f"/api/v1/courses/{course_id}")
        assert outsider_detail.status_code == 403
        assert outsider_detail.json()["error"]["code"] == "COURSE_ACCESS_DENIED"

        current_user["id"] = owner_id
        owner_conflict = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": old_code},
        )
        assert owner_conflict.status_code == 409
        assert owner_conflict.json()["error"]["code"] == "MEMBERSHIP_CONFLICT"

        rotate_headers = {
            **TRUSTED_ORIGIN,
            "Idempotency-Key": "rotate-course-integration-001",
        }
        rotated = client.post(
            f"/api/v1/courses/{course_id}/join-code/rotate",
            headers=rotate_headers,
        )
        rotate_replay = client.post(
            f"/api/v1/courses/{course_id}/join-code/rotate",
            headers=rotate_headers,
        )
        assert rotated.status_code == 200
        assert rotate_replay.json() == rotated.json()
        new_code = rotated.json()["join_code"]
        assert new_code != old_code

        owner_list = client.get("/api/v1/courses", params={"role": "PROFESSOR"})
        assert owner_list.status_code == 200
        assert owner_list.json()["items"][0]["join_code"] == new_code

        current_user["id"] = late_student_id
        old_code_rejected = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": old_code},
        )
        new_code_accepted = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": new_code},
        )
        assert old_code_rejected.status_code == 404
        assert new_code_accepted.status_code == 201

    assert old_code not in caplog.text
    assert new_code not in caplog.text


async def _exercise_concurrent_membership_and_rotation(database_url: str) -> None:
    owner_id, student_id = await _seed_users(database_url, 2)
    settings = _settings(database_url)
    codec = settings.course_join_code_codec
    assert codec is not None
    database = create_database(settings)
    service = CourseService(codec)
    try:
        async with database.session_factory() as session:
            async with transaction(session):
                view, initial_code = await service.create(
                    session,
                    user_id=owner_id,
                    title="동시성 Course",
                    semester="2026 여름학기",
                )
                course_id = view.course.id

        async def join_once() -> bool:
            async with database.session_factory() as session:
                async with transaction(session):
                    result = await CourseService(codec).join(
                        session,
                        user_id=student_id,
                        raw_join_code=initial_code,
                    )
                    return result.created

        joined = await asyncio.gather(join_once(), join_once())
        assert sorted(joined) == [False, True]

        async def rotate_once() -> str:
            async with database.session_factory() as session:
                async with transaction(session):
                    _, code = await CourseService(codec).rotate_join_code(
                        session,
                        course_id=course_id,
                        user_id=owner_id,
                    )
                    return code

        rotated_codes = await asyncio.gather(rotate_once(), rotate_once())
        assert rotated_codes[0] != rotated_codes[1]

        async with database.session_factory() as session:
            membership_count = await session.scalar(
                select(func.count())
                .select_from(CourseMember)
                .where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id == student_id,
                    CourseMember.role == "STUDENT",
                )
            )
            course = await session.get(Course, course_id)
            assert course is not None
            current_code = CourseService(codec).reveal_join_code(course)
        assert membership_count == 1
        assert current_code in rotated_codes
        assert current_code != initial_code

        for stale_code in {initial_code, *rotated_codes} - {current_code}:
            async with database.session_factory() as session:
                async with transaction(session):
                    with pytest.raises(CourseNotFoundError):
                        await CourseService(codec).join(
                            session,
                            user_id=uuid4(),
                            raw_join_code=stale_code,
                        )
    finally:
        await database.dispose()


def test_concurrent_join_and_rotation_keep_one_membership_and_one_current_code(
    migrated_database_url: str,
) -> None:
    """Concurrent requests serialize without duplicate membership or two valid codes."""

    asyncio.run(_exercise_concurrent_membership_and_rotation(migrated_database_url))

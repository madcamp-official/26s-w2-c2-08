"""Integration coverage for the PDF Material upload and lifecycle boundary."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database
from tbd.services.materials import MaterialProcessingWorker
from tbd.storage import FailureStorage, InMemoryStorage, StorageOperation

pytestmark = pytest.mark.integration
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
        storage_root=tmp_path / "uploads",
        auth_allowed_origins="http://localhost:5173",
        idempotency_response_encryption_key=base64.b64encode(b"i" * 32).decode(),
        course_join_code_encryption_key=base64.b64encode(b"e" * 32).decode(),
        course_join_code_lookup_key=base64.b64encode(b"h" * 32).decode(),
    )


async def _seed_users(database_url: str, tmp_path: Path, count: int) -> list[UUID]:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            user_ids: list[UUID] = []
            for index in range(count):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"material-user-{index}-{uuid4().hex[:8]}",
                        "email": f"material-{index}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                user_ids.append(user_id)
            return user_ids
    finally:
        await database.dispose()


def _pdf_bytes() -> bytes:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "GOAL material test")
        return document.tobytes()
    finally:
        document.close()


async def _seed_completed_archive_rows(
    database_url: str,
    tmp_path: Path,
    *,
    course_id: UUID,
    owner_id: UUID,
) -> tuple[list[UUID], list[UUID]]:
    database = create_database(_settings(database_url, tmp_path))
    now = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    newer_session_id = uuid4()
    older_session_id = uuid4()
    material_ids = [uuid4() for _ in range(4)]
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO lecture_sessions (
                        id, course_id, created_by_user_id, title, lecture_date, status,
                        version, started_at, ended_at, completed_at, created_at, updated_at
                    ) VALUES (
                        :id, :course_id, :owner_id, :title, :lecture_date, 'COMPLETED',
                        1, :started_at, :ended_at, :completed_at, :created_at, :updated_at
                    )
                    """
                ),
                [
                    {
                        "id": newer_session_id,
                        "course_id": course_id,
                        "owner_id": owner_id,
                        "title": "완료 class 최신",
                        "lecture_date": (now - timedelta(days=1)).date(),
                        "started_at": now - timedelta(days=1),
                        "ended_at": now - timedelta(days=1) + timedelta(hours=1),
                        "completed_at": now - timedelta(days=1) + timedelta(hours=2),
                        "created_at": now - timedelta(days=2),
                        "updated_at": now - timedelta(days=1) + timedelta(hours=2),
                    },
                    {
                        "id": older_session_id,
                        "course_id": course_id,
                        "owner_id": owner_id,
                        "title": "완료 class 이전",
                        "lecture_date": (now - timedelta(days=2)).date(),
                        "started_at": now - timedelta(days=2),
                        "ended_at": now - timedelta(days=2) + timedelta(hours=1),
                        "completed_at": now - timedelta(days=2) + timedelta(hours=2),
                        "created_at": now - timedelta(days=3),
                        "updated_at": now - timedelta(days=2) + timedelta(hours=2),
                    },
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO lecture_materials (
                        id, session_id, uploaded_by_user_id, original_filename,
                        display_name, mime_type, byte_size, storage_key, page_count,
                        processing_status, version, detached_at, created_at, updated_at
                    ) VALUES (
                        :id, :session_id, :owner_id, :filename, :display_name,
                        'application/pdf', 42, :storage_key, NULL, :status, 1,
                        :detached_at, :created_at, :updated_at
                    )
                    """
                ),
                [
                    {
                        "id": material_ids[0],
                        "session_id": newer_session_id,
                        "owner_id": owner_id,
                        "filename": "newer-a.pdf",
                        "display_name": "newer-a.pdf",
                        "storage_key": f"final/{material_ids[0].hex}",
                        "status": "UPLOADED",
                        "detached_at": None,
                        "created_at": now - timedelta(days=1, hours=-1),
                        "updated_at": now - timedelta(days=1, hours=-1),
                    },
                    {
                        "id": material_ids[1],
                        "session_id": newer_session_id,
                        "owner_id": owner_id,
                        "filename": "newer-failed.pdf",
                        "display_name": "newer-failed.pdf",
                        "storage_key": f"final/{material_ids[1].hex}",
                        "status": "FAILED",
                        "detached_at": None,
                        "created_at": now - timedelta(days=1, hours=-2),
                        "updated_at": now - timedelta(days=1, hours=-2),
                    },
                    {
                        "id": material_ids[2],
                        "session_id": older_session_id,
                        "owner_id": owner_id,
                        "filename": "older.pdf",
                        "display_name": "older.pdf",
                        "storage_key": f"final/{material_ids[2].hex}",
                        "status": "PROCESSING",
                        "detached_at": None,
                        "created_at": now - timedelta(days=2, hours=-1),
                        "updated_at": now - timedelta(days=2, hours=-1),
                    },
                    {
                        "id": material_ids[3],
                        "session_id": older_session_id,
                        "owner_id": owner_id,
                        "filename": "detached.pdf",
                        "display_name": "detached.pdf",
                        "storage_key": f"final/{material_ids[3].hex}",
                        "status": "UPLOADED",
                        "detached_at": now,
                        "created_at": now - timedelta(days=2, hours=-2),
                        "updated_at": now,
                    },
                ],
            )
        return [newer_session_id, older_session_id], material_ids
    finally:
        await database.dispose()


async def _mark_course_deleted(
    database_url: str,
    tmp_path: Path,
    *,
    course_id: UUID,
) -> None:
    database = create_database(_settings(database_url, tmp_path))
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("UPDATE courses SET deleted_at = now() WHERE id = :course_id"),
                {"course_id": course_id},
            )
    finally:
        await database.dispose()


async def _complete_archive_session(
    database_url: str,
    tmp_path: Path,
    *,
    session_id: UUID,
) -> None:
    database = create_database(_settings(database_url, tmp_path))
    completed_at = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE lecture_sessions
                    SET status = 'COMPLETED', started_at = :started_at,
                        ended_at = :completed_at, completed_at = :completed_at,
                        version = version + 1, updated_at = :completed_at
                    WHERE id = :session_id
                    """
                ),
                {
                    "session_id": session_id,
                    "started_at": completed_at - timedelta(hours=1),
                    "completed_at": completed_at,
                },
            )
    finally:
        await database.dispose()


def test_course_material_archive_is_scoped_sorted_and_downloadable(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id, outsider_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 2))
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    storage = InMemoryStorage()
    app = create_app(settings=settings, database=database, storage=storage)
    current_user = {"id": owner_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    pdf = _pdf_bytes()

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-archive-course"},
            json={"title": "Course 자료 모음", "semester": "2026 여름학기"},
        )
        assert course.status_code == 201
        course_id = UUID(course.json()["id"])
        completed_session_ids, material_ids = asyncio.run(
            _seed_completed_archive_rows(
                migrated_database_url,
                tmp_path,
                course_id=course_id,
                owner_id=owner_id,
            )
        )
        active_session = client.post(
            f"/api/v1/courses/{course_id}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"title": "현재 class", "lecture_date": "2026-07-15"},
        )
        assert active_session.status_code == 201
        active_session_id = active_session.json()["id"]
        active_material_ids: list[str] = []
        for index, filename in enumerate(("active-a.pdf", "active-b.pdf"), start=1):
            upload = client.post(
                f"/api/v1/sessions/{active_session_id}/materials",
                headers={
                    **TRUSTED_ORIGIN,
                    "Idempotency-Key": f"material-archive-upload-{index}",
                },
                files={"file": (filename, pdf, "application/pdf")},
            )
            assert upload.status_code == 202
            active_material_ids.append(upload.json()["material"]["id"])

        first = client.get(f"/api/v1/courses/{course_id}/materials", params={"limit": 2})
        assert first.status_code == 200
        assert [item["material"]["id"] for item in first.json()["items"]] == active_material_ids
        assert {item["session"]["id"] for item in first.json()["items"]} == {active_session_id}
        for item in first.json()["items"]:
            assert set(item) == {"session", "material", "content_url", "download_url"}
            assert "storage_key" not in item["material"]
            assert "uploaded_by_user_id" not in item["material"]
            assert item["content_url"] == (f"/api/v1/materials/{item['material']['id']}/content")
            assert item["download_url"] == (
                f"/api/v1/materials/{item['material']['id']}/content?disposition=attachment"
            )
        cursor = first.json()["next_cursor"]
        assert isinstance(cursor, str)

        # The issued cursor freezes the active class group. Completing that
        # class between pages must not repeat its already returned Materials.
        asyncio.run(
            _complete_archive_session(
                migrated_database_url,
                tmp_path,
                session_id=UUID(active_session_id),
            )
        )
        second = client.get(
            f"/api/v1/courses/{course_id}/materials",
            params={"limit": 2, "cursor": cursor},
        )
        assert second.status_code == 200
        assert [item["material"]["id"] for item in second.json()["items"]] == [
            str(material_ids[0]),
            str(material_ids[1]),
        ]
        assert {item["session"]["id"] for item in second.json()["items"]} == {
            str(completed_session_ids[0])
        }
        failed = second.json()["items"][1]
        assert failed["material"]["processing_status"] == "FAILED"
        assert failed["content_url"] is None
        assert failed["download_url"] is None
        failed_content = client.get(f"/api/v1/materials/{material_ids[1]}/content")
        assert failed_content.status_code == 404
        assert failed_content.json()["error"]["code"] == "MATERIAL_NOT_FOUND"
        second_cursor = second.json()["next_cursor"]
        assert isinstance(second_cursor, str)

        third = client.get(
            f"/api/v1/courses/{course_id}/materials",
            params={"limit": 2, "cursor": second_cursor},
        )
        assert third.status_code == 200
        assert [item["material"]["id"] for item in third.json()["items"]] == [str(material_ids[2])]
        assert third.json()["next_cursor"] is None
        assert str(material_ids[3]) not in {
            item["material"]["id"]
            for page in (first.json(), second.json(), third.json())
            for item in page["items"]
        }

        inline = client.get(f"/api/v1/materials/{active_material_ids[0]}/content")
        download = client.get(
            f"/api/v1/materials/{active_material_ids[0]}/content",
            params={"disposition": "attachment"},
        )
        assert inline.status_code == 200
        assert inline.headers["content-disposition"] == ("inline; filename*=UTF-8''active-a.pdf")
        assert download.status_code == 200
        assert download.headers["content-disposition"] == (
            "attachment; filename*=UTF-8''active-a.pdf"
        )
        assert download.content == inline.content == pdf
        invalid_disposition = client.get(
            f"/api/v1/materials/{active_material_ids[0]}/content",
            params={"disposition": "preview"},
        )
        assert invalid_disposition.status_code == 422
        assert invalid_disposition.json()["error"]["code"] == "VALIDATION_ERROR"

        replacement = "A" if cursor[-1] != "A" else "B"
        tampered = client.get(
            f"/api/v1/courses/{course_id}/materials",
            params={"cursor": f"{cursor[:-1]}{replacement}"},
        )
        assert tampered.status_code == 400
        assert tampered.json()["error"]["code"] == "INVALID_CURSOR"

        other_course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "other-material-archive-course"},
            json={"title": "다른 Course", "semester": "2026 여름학기"},
        )
        assert other_course.status_code == 201
        other_course_id = UUID(other_course.json()["id"])
        wrong_scope = client.get(
            f"/api/v1/courses/{other_course_id}/materials",
            params={"cursor": cursor},
        )
        assert wrong_scope.status_code == 400
        assert wrong_scope.json()["error"]["code"] == "INVALID_CURSOR"

        current_user["id"] = outsider_id
        forbidden = client.get(f"/api/v1/courses/{course_id}/materials")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "COURSE_ACCESS_DENIED"

        current_user["id"] = owner_id
        asyncio.run(
            _mark_course_deleted(
                migrated_database_url,
                tmp_path,
                course_id=course_id,
            )
        )
        deleted = client.get(f"/api/v1/courses/{course_id}/materials")
        deleted_content = client.get(f"/api/v1/materials/{active_material_ids[0]}/content")
        missing = client.get(f"/api/v1/courses/{uuid4()}/materials")
        assert deleted.status_code == 404
        assert deleted_content.status_code == 404
        assert deleted_content.json()["error"]["code"] == "MATERIAL_NOT_FOUND"
        assert missing.status_code == 404

    asyncio.run(database.dispose())


def test_material_upload_processing_read_and_detach_are_role_scoped(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id, student_id, outsider_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 3))
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    storage = InMemoryStorage()
    app = create_app(settings=settings, database=database, storage=storage)
    current_user = {"id": owner_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    pdf = _pdf_bytes()
    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-course-create"},
            json={"title": "자료 처리", "semester": "2026 여름학기"},
        )
        assert course.status_code == 201
        course_id = course.json()["id"]
        session = client.post(
            f"/api/v1/courses/{course_id}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"title": "PDF 자료", "lecture_date": "2026-07-14"},
        )
        assert session.status_code == 201
        session_id = session.json()["id"]

        first_upload = client.post(
            f"/api/v1/sessions/{session_id}/materials",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-upload-001"},
            files={"file": ("lecture.pdf", pdf, "application/pdf")},
        )
        replay_upload = client.post(
            f"/api/v1/sessions/{session_id}/materials",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-upload-001"},
            files={"file": ("lecture.pdf", pdf, "application/pdf")},
        )
        assert first_upload.status_code == 202
        assert replay_upload.status_code == 202
        assert replay_upload.json() == first_upload.json()
        accepted = first_upload.json()
        material_id = accepted["material"]["id"]
        assert accepted["material"]["processing_status"] == "UPLOADED"
        assert accepted["material"]["page_count"] is None
        assert accepted["job"]["job_type"] == "MATERIAL_PROCESSING"
        assert accepted["job"]["visibility"] == "SHARED"
        assert accepted["job"]["blocks_session_completion"] is False
        assert "storage_key" not in accepted["material"]

        current_user["id"] = student_id
        join = client.post(
            "/api/v1/courses/join",
            headers=TRUSTED_ORIGIN,
            json={"join_code": course.json()["join_code"]},
        )
        assert join.status_code == 201
        listed = client.get(f"/api/v1/sessions/{session_id}/materials")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["display_name"] == "lecture.pdf"
        readable_while_queued = client.get(f"/api/v1/materials/{material_id}/content")
        assert readable_while_queued.status_code == 200
        assert readable_while_queued.headers["content-type"].startswith("application/pdf")
        assert (
            client.post(
                f"/api/v1/sessions/{session_id}/materials",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "student-material-upload"},
                files={"file": ("student.pdf", pdf, "application/pdf")},
            ).status_code
            == 403
        )

    worker = MaterialProcessingWorker(database.session_factory, storage)
    assert asyncio.run(worker.run_once()) is True

    with TestClient(app) as client:
        current_user["id"] = owner_id
        processed = client.get(f"/api/v1/materials/{material_id}")
        assert processed.status_code == 200
        assert processed.json()["processing_status"] == "READY"
        assert processed.json()["page_count"] == 1

        current_user["id"] = outsider_id
        assert client.get(f"/api/v1/materials/{material_id}").status_code == 404

        current_user["id"] = owner_id
        detached = client.delete(
            f"/api/v1/materials/{material_id}",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-detach-001"},
        )
        detached_replay = client.delete(
            f"/api/v1/materials/{material_id}",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-detach-001"},
        )
        assert detached.status_code == 204
        assert detached_replay.status_code == 204
        assert client.get(f"/api/v1/materials/{material_id}").status_code == 404
        assert client.get(f"/api/v1/materials/{material_id}/content").status_code == 404
        assert client.get(f"/api/v1/sessions/{session_id}/materials").json()["items"] == []

    asyncio.run(database.dispose())


def test_material_rejects_non_pdf_and_preserves_other_materials(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 1))[0]
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    app = create_app(settings=settings, database=database, storage=InMemoryStorage())
    app.dependency_overrides[get_current_user_id] = lambda: owner_id

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "invalid-material-course"},
            json={"title": "자료 검증", "semester": "2026 여름학기"},
        )
        session = client.post(
            f"/api/v1/courses/{course.json()['id']}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"lecture_date": "2026-07-14"},
        )
        rejected = client.post(
            f"/api/v1/sessions/{session.json()['id']}/materials",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "invalid-material-file"},
            files={"file": ("not-a-pdf.pdf", b"not actually a PDF", "application/pdf")},
        )
        assert rejected.status_code == 415
        assert rejected.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
        assert (
            client.get(f"/api/v1/sessions/{session.json()['id']}/materials").json()["items"] == []
        )

    asyncio.run(database.dispose())


def test_material_assigns_stable_duplicate_name_suffixes(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 1))[0]
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    app = create_app(settings=settings, database=database, storage=InMemoryStorage())
    app.dependency_overrides[get_current_user_id] = lambda: owner_id
    pdf = _pdf_bytes()

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-names-course"},
            json={"title": "이름 충돌", "semester": "2026 여름학기"},
        )
        lecture_session = client.post(
            f"/api/v1/courses/{course.json()['id']}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"lecture_date": "2026-07-14"},
        )
        first = client.post(
            f"/api/v1/sessions/{lecture_session.json()['id']}/materials",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-name-001"},
            files={"file": ("lecture.pdf", pdf, "application/pdf")},
        )
        second = client.post(
            f"/api/v1/sessions/{lecture_session.json()['id']}/materials",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-name-002"},
            files={"file": ("lecture.pdf", pdf, "application/pdf")},
        )

        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["material"]["display_name"] == "lecture.pdf"
        assert second.json()["material"]["display_name"] == "lecture (1).pdf"

    asyncio.run(database.dispose())


def test_material_storage_failure_compensates_before_db_attachment(
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    owner_id = asyncio.run(_seed_users(migrated_database_url, tmp_path, 1))[0]
    settings = _settings(migrated_database_url, tmp_path)
    database = create_database(settings)
    delegate = InMemoryStorage()
    storage = FailureStorage(delegate)
    storage.fail_next(StorageOperation.PROMOTE)
    app = create_app(settings=settings, database=database, storage=storage)
    app.dependency_overrides[get_current_user_id] = lambda: owner_id

    with TestClient(app) as client:
        course = client.post(
            "/api/v1/courses",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-storage-course"},
            json={"title": "파일 보상", "semester": "2026 여름학기"},
        )
        lecture_session = client.post(
            f"/api/v1/courses/{course.json()['id']}/sessions",
            headers=TRUSTED_ORIGIN,
            json={"lecture_date": "2026-07-14"},
        )
        upload = client.post(
            f"/api/v1/sessions/{lecture_session.json()['id']}/materials",
            headers={**TRUSTED_ORIGIN, "Idempotency-Key": "material-storage-001"},
            files={"file": ("lecture.pdf", _pdf_bytes(), "application/pdf")},
        )

        assert upload.status_code == 503
        assert upload.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
        assert (
            client.get(f"/api/v1/sessions/{lecture_session.json()['id']}/materials").json()["items"]
            == []
        )

    async def assert_compensated() -> None:
        assert [key async for key in delegate.iter_keys()] == []

    asyncio.run(assert_compensated())
    asyncio.run(database.dispose())

"""Integration coverage for the PDF Material upload and lifecycle boundary."""

import asyncio
import base64
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

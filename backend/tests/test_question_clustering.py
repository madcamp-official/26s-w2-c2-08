"""Integration coverage for fenced LIVE Question clustering generations."""

import asyncio
import base64
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tbd.api.dependencies import get_current_user_id
from tbd.app import create_app
from tbd.core.config import AppEnvironment, Settings
from tbd.db import create_database, transaction
from tbd.models.enums import AIJobStatus
from tbd.models.questions import AIJob, QuestionClusteringState
from tbd.providers.ai.clustering import ClusteringInput
from tbd.providers.ai.fake import FakeQuestionClusteringProvider
from tbd.services.clustering import QuestionClusteringWorker

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


async def _seed_users(database_url: str) -> tuple[UUID, UUID]:
    database = create_database(_settings(database_url))
    try:
        async with database.engine.begin() as connection:
            values: list[UUID] = []
            for label in ("professor", "student"):
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (display_name, primary_email) "
                        "VALUES (:name, :email) RETURNING id"
                    ),
                    {
                        "name": f"cluster-{label}-{uuid4().hex[:8]}",
                        "email": f"cluster-{label}-{uuid4().hex[:8]}@example.test",
                    },
                )
                assert isinstance(user_id, UUID)
                values.append(user_id)
            return values[0], values[1]
    finally:
        await database.dispose()


def test_live_clustering_coalesces_and_exposes_canonical_clusters(
    migrated_database_url: str,
) -> None:
    """New Questions wait for the next immutable generation without moving old ones."""

    professor_id, student_id = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "cluster-course"},
                json={"title": "클러스터 수업", "semester": "2026 여름학기"},
            )
            assert course.status_code == 201
            course_id, join_code = course.json()["id"], course.json()["join_code"]
            created = client.post(
                f"/api/v1/courses/{course_id}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"lecture_date": "2026-07-14"},
            )
            assert created.status_code == 201
            session_id = UUID(created.json()["id"])
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN
                ).status_code
                == 200
            )
            current_user["id"] = student_id
            assert (
                client.post(
                    "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
                ).status_code
                == 201
            )
            for content in ("네트워크 지연은 왜 생기나요?", "데이터베이스 인덱스가 뭔가요?"):
                assert (
                    client.post(
                        f"/api/v1/sessions/{session_id}/questions",
                        headers=TRUSTED_ORIGIN,
                        json={"content": content},
                    ).status_code
                    == 201
                )

            worker = QuestionClusteringWorker(
                database.session_factory, FakeQuestionClusteringProvider()
            )
            claimed = asyncio.run(worker._claim(datetime.now(UTC)))
            assert claimed is not None
            assert len(claimed.inputs) == 1
            # The first job has captured sequence 1.  These later questions must
            # never leak into its provider input or overwrite its generation.
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/questions",
                    headers=TRUSTED_ORIGIN,
                    json={"content": "네트워크 패킷은 무엇인가요?"},
                ).status_code
                == 201
            )
            suggestions = asyncio.run(FakeQuestionClusteringProvider().cluster(claimed.inputs))
            asyncio.run(worker._succeed(claimed, suggestions, datetime.now(UTC)))

            first_clusters = client.get(f"/api/v1/sessions/{session_id}/question-clusters")
            assert first_clusters.status_code == 200
            assert first_clusters.json()["generation"] == 1
            assert first_clusters.json()["clustering_state"]["applied_through_sequence"] == 1
            assert first_clusters.json()["clustering_state"]["active_job_id"] is not None
            first_ids = {item["id"] for item in first_clusters.json()["items"]}

            assert asyncio.run(worker.run_once()) is True
            second_clusters = client.get(f"/api/v1/sessions/{session_id}/question-clusters")
            assert second_clusters.status_code == 200
            assert second_clusters.json()["generation"] == 2
            assert second_clusters.json()["clustering_state"]["applied_through_sequence"] == 3
            assert first_ids.issubset({item["id"] for item in second_clusters.json()["items"]})
            first_cluster = second_clusters.json()["items"][0]
            members = client.get(first_cluster["members_url"])
            assert members.status_code == 200
            assert all(
                item["source_kind"] == "STUDENT_QUESTION" for item in members.json()["items"]
            )
    finally:
        asyncio.run(database.dispose())


class _FailOnceProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.fake = FakeQuestionClusteringProvider()

    async def cluster(self, inputs: tuple[ClusteringInput, ...]):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary provider failure")
        return await self.fake.cluster(inputs)


def test_live_clustering_retries_same_job_and_supersedes_stale_result(
    migrated_database_url: str,
) -> None:
    """Retry increments an attempt; a late fenced worker cannot publish a generation."""

    professor_id, student_id = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "cluster-retry-course"},
                json={"title": "재시도 수업", "semester": "2026 여름학기"},
            )
            course_id, join_code = course.json()["id"], course.json()["join_code"]
            created = client.post(
                f"/api/v1/courses/{course_id}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"lecture_date": "2026-07-14"},
            )
            session_id = UUID(created.json()["id"])
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN
                ).status_code
                == 200
            )
            current_user["id"] = student_id
            assert (
                client.post(
                    "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
                ).status_code
                == 201
            )
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/questions",
                    headers=TRUSTED_ORIGIN,
                    json={"content": "재시도 대상 질문"},
                ).status_code
                == 201
            )

            provider = _FailOnceProvider()
            worker = QuestionClusteringWorker(database.session_factory, provider)
            assert asyncio.run(worker.run_once()) is True

            async def job_by_id(job_id: UUID) -> AIJob:
                async with database.session_factory() as session:
                    job = await session.get(AIJob, job_id)
                    assert job is not None
                    return job

            async def active_job_id() -> UUID:
                async with database.session_factory() as session:
                    state = await session.get(QuestionClusteringState, session_id)
                    assert state is not None and state.last_job_id is not None
                    return state.last_job_id

            job_id = asyncio.run(active_job_id())
            failed = asyncio.run(job_by_id(job_id))
            assert failed.status == AIJobStatus.FAILED
            assert failed.attempt == 1
            assert asyncio.run(worker.run_once()) is True
            retried = asyncio.run(job_by_id(job_id))
            assert retried.status == AIJobStatus.SUCCEEDED
            assert retried.attempt == 2

            # A worker that claimed an old revision is fenced before it can
            # publish a later generation.
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/questions",
                    headers=TRUSTED_ORIGIN,
                    json={"content": "늦은 결과 테스트"},
                ).status_code
                == 201
            )
            claimed = asyncio.run(worker._claim(datetime.now(UTC)))
            assert claimed is not None

            async def advance_revision() -> None:
                async with database.session_factory() as session:
                    async with transaction(session):
                        state = await session.get(
                            QuestionClusteringState, session_id, with_for_update=True
                        )
                        assert state is not None
                        state.current_revision += 1

            asyncio.run(advance_revision())
            suggestions = asyncio.run(FakeQuestionClusteringProvider().cluster(claimed.inputs))
            asyncio.run(worker._succeed(claimed, suggestions, datetime.now(UTC)))
            stale = asyncio.run(job_by_id(claimed.job_id))
            assert stale.status == AIJobStatus.SUPERSEDED
    finally:
        asyncio.run(database.dispose())


def test_session_end_freezes_and_publishes_a_final_cluster_generation(
    migrated_database_url: str,
) -> None:
    """The final worker can only use the persisted end-time Question watermark."""

    professor_id, student_id = asyncio.run(_seed_users(migrated_database_url))
    settings = _settings(migrated_database_url)
    database = create_database(settings)
    app = create_app(settings=settings, database=database)
    current_user = {"id": professor_id}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    try:
        with TestClient(app) as client:
            course = client.post(
                "/api/v1/courses",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "final-cluster-course"},
                json={"title": "최종 클러스터 수업", "semester": "2026 여름학기"},
            )
            assert course.status_code == 201
            course_id, join_code = course.json()["id"], course.json()["join_code"]
            created = client.post(
                f"/api/v1/courses/{course_id}/sessions",
                headers=TRUSTED_ORIGIN,
                json={"lecture_date": "2026-07-14"},
            )
            session_id = UUID(created.json()["id"])
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/start", headers=TRUSTED_ORIGIN
                ).status_code
                == 200
            )
            current_user["id"] = student_id
            assert (
                client.post(
                    "/api/v1/courses/join", headers=TRUSTED_ORIGIN, json={"join_code": join_code}
                ).status_code
                == 201
            )
            assert (
                client.post(
                    f"/api/v1/sessions/{session_id}/questions",
                    headers=TRUSTED_ORIGIN,
                    json={"content": "최종 분류에도 남아야 하는 질문인가요?"},
                ).status_code
                == 201
            )

            current_user["id"] = professor_id
            ended = client.post(
                f"/api/v1/sessions/{session_id}/end",
                headers={**TRUSTED_ORIGIN, "Idempotency-Key": "final-cluster-end"},
            )
            assert ended.status_code == 202
            assert {job["job_type"] for job in ended.json()["jobs"]} == {
                "SESSION_POSTPROCESSING",
                "QUESTION_CLUSTERING",
            }

            worker = QuestionClusteringWorker(
                database.session_factory, FakeQuestionClusteringProvider()
            )
            assert asyncio.run(worker.run_once()) is True

            final_clusters = client.get(
                f"/api/v1/sessions/{session_id}/question-clusters?scope=FINAL"
            )
            assert final_clusters.status_code == 200
            assert final_clusters.json()["generation"] == 1
            assert all(item["is_final"] for item in final_clusters.json()["items"])
            assert final_clusters.json()["items"][0]["member_count"] == 1
    finally:
        asyncio.run(database.dispose())

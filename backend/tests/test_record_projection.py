"""Unit coverage for PROCESSING record projections used by the production UI."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tbd.models.knowledge import LectureSummary
from tbd.models.materials import TranscriptSegment, TranscriptVersion
from tbd.models.questions import AIJob, QuestionClusteringState
from tbd.models.sessions import LectureSession
from tbd.providers.ai.fake import FakeQuestionClusteringProvider
from tbd.services.answers import AnswerService
from tbd.services.clustering import QuestionClusteringWorker
from tbd.services.job_results import AIJobResultService, JobResultIntegrityError
from tbd.services.personal_ai import PersonalAIService
from tbd.services.questions import QuestionService

pytestmark = pytest.mark.unit


class _LiveFallbackSummarySessionStub:
    def __init__(
        self,
        *,
        coordinator: AIJob,
        canonical: TranscriptVersion,
        summary: LectureSummary,
        summary_job: AIJob,
    ) -> None:
        self.scalar_results = iter((coordinator, None, summary))
        self.canonical = canonical
        self.summary_job = summary_job

    async def scalar(self, _query: object) -> object | None:
        return next(self.scalar_results)

    async def get(self, model: object, identity: object) -> object | None:
        if model is TranscriptVersion and identity == self.canonical.id:
            return self.canonical
        if model is AIJob and identity == self.summary_job.id:
            return self.summary_job
        return None


def test_final_summary_projection_uses_finalized_canonical_live_fallback() -> None:
    """A missing HQ upload must not hide a summary generated from canonical LIVE."""

    session_id = uuid4()
    version_id = uuid4()
    segment_id = uuid4()
    job_id = uuid4()
    lecture_session = LectureSession(
        id=session_id,
        course_id=uuid4(),
        created_by_user_id=uuid4(),
        title="프랑스에서 살아남기",
        lecture_date=datetime.now(UTC).date(),
        status="COMPLETED",
        canonical_transcript_version_id=version_id,
        version=1,
    )
    canonical = TranscriptVersion(
        id=version_id,
        session_id=session_id,
        version=1,
        source="LIVE",
        status="FINALIZED",
        last_sequence=1,
    )
    coordinator = AIJob(
        id=uuid4(),
        session_id=session_id,
        job_type="SESSION_POSTPROCESSING",
        visibility="SHARED",
        status="SUCCEEDED",
        attempt=1,
        version=1,
        blocks_session_completion=True,
        retryable=False,
    )
    summary_job = AIJob(
        id=job_id,
        session_id=session_id,
        job_type="FINAL_SUMMARY",
        visibility="SHARED",
        status="SUCCEEDED",
        attempt=1,
        version=1,
        input_transcript_version_id=version_id,
        blocks_session_completion=True,
        retryable=False,
    )
    summary = LectureSummary(
        id=uuid4(),
        session_id=session_id,
        created_by_job_id=job_id,
        created_by_job_attempt=1,
        summary_type="FINAL",
        visibility="COURSE_MEMBERS",
        content="정상적으로 생성된 요약",
        source_transcript_version_id=version_id,
        source_start_segment_id=segment_id,
        source_end_segment_id=segment_id,
        model_name="fake",
        prompt_version="final-summary-v2",
    )
    stub = _LiveFallbackSummarySessionStub(
        coordinator=coordinator,
        canonical=canonical,
        summary=summary,
        summary_job=summary_job,
    )

    summaries, status, reason = asyncio.run(
        PersonalAIService()._final_summary_state(  # type: ignore[arg-type]
            stub, lecture_session
        )
    )

    assert summaries == [summary]
    assert status == "AVAILABLE"
    assert reason is None


def test_final_clustering_projection_keeps_the_persisted_job_mode() -> None:
    job_id = uuid4()
    session_id = uuid4()
    state = QuestionClusteringState(
        session_id=session_id,
        requested_sequence=3,
        applied_sequence=3,
        current_revision=2,
        current_generation=2,
        final_generation=None,
        last_job_id=job_id,
        last_job_attempt=1,
        last_job_status="RUNNING",
    )
    job = AIJob(
        id=job_id,
        session_id=session_id,
        job_type="QUESTION_CLUSTERING",
        status="RUNNING",
        attempt=1,
        version=1,
        clustering_mode="FINAL",
    )

    projected = QuestionService.project_clustering_state(state, active=job, last=job)

    assert projected.last_job is not None
    assert projected.last_job.mode == "FINAL"


class _ClusteringEventSessionStub:
    def __init__(self, job: AIJob) -> None:
        self.job = job

    async def get(self, model: object, identity: object) -> object | None:
        assert model is AIJob
        assert identity == self.job.id
        return self.job


class _OutboxStub:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    async def enqueue(self, _session: object, **values: object) -> None:
        payload = values["payload"]
        assert isinstance(payload, dict)
        self.payload = payload


def test_final_clustering_terminal_event_keeps_the_persisted_job_mode() -> None:
    job_id = uuid4()
    session_id = uuid4()
    state = QuestionClusteringState(
        session_id=session_id,
        requested_sequence=3,
        applied_sequence=3,
        current_revision=3,
        current_generation=3,
        final_generation=3,
        last_job_id=job_id,
        last_job_attempt=1,
        last_job_status="SUCCEEDED",
    )
    job = AIJob(
        id=job_id,
        session_id=session_id,
        job_type="QUESTION_CLUSTERING",
        status="SUCCEEDED",
        attempt=1,
        version=2,
        clustering_mode="FINAL",
    )
    outbox = _OutboxStub()
    worker = QuestionClusteringWorker(
        None,  # type: ignore[arg-type]
        FakeQuestionClusteringProvider(),
        outbox=outbox,  # type: ignore[arg-type]
    )

    asyncio.run(
        worker._emit_state(  # type: ignore[arg-type]
            _ClusteringEventSessionStub(job), state, active=None
        )
    )

    assert outbox.payload is not None
    clustering_state = outbox.payload["clustering_state"]
    assert isinstance(clustering_state, dict)
    last_job = clustering_state["last_job"]
    assert isinstance(last_job, dict)
    assert last_job["mode"] == "FINAL"


class _AnswerRepositoryStub:
    async def canonical_mapping(self, *_args: object, **_kwargs: object) -> None:
        return None


class _ProjectionSessionStub:
    def __init__(
        self,
        *,
        lecture_session: object,
        organization: object,
        segments: dict,
        organization_job: object | None = None,
    ) -> None:
        self.lecture_session = lecture_session
        self.organization = organization
        self.organization_job = organization_job
        self.segments = segments
        self.scalar_results = iter((organization, organization_job))

    async def scalar(self, _statement: object) -> object | None:
        return next(self.scalar_results)

    async def get(self, model: object, identity: object) -> object | None:
        if model is LectureSession:
            return self.lecture_session
        if model is AIJob:
            if self.organization_job is not None and identity == self.organization_job.id:
                return self.organization_job
            return None
        if model is TranscriptSegment:
            return self.segments.get(identity)
        return None


def test_answer_projection_includes_the_immutable_organization_result() -> None:
    now = datetime.now(UTC)
    session_id = uuid4()
    answer_id = uuid4()
    original_start_id = uuid4()
    original_end_id = uuid4()
    organization_start_id = uuid4()
    organization_end_id = uuid4()
    transcript_version_id = uuid4()
    job_id = uuid4()
    answer = SimpleNamespace(
        id=answer_id,
        session_id=session_id,
        version=2,
        status="COMPLETED",
        target_question_id=uuid4(),
        target_representative_question_id=None,
        target_text_snapshot="왜 음수 간선을 사용할 수 없나요?",
        text_content=None,
        source_transcript_version_id=transcript_version_id,
        capture_started_after_sequence=0,
        start_segment_id=original_start_id,
        end_segment_id=original_end_id,
        started_at=now,
        completed_at=now,
        updated_at=now,
    )
    organization = SimpleNamespace(
        answer_id=answer_id,
        content="음수 간선에서는 벨만-포드 알고리즘을 검토합니다.",
        source_transcript_version_id=transcript_version_id,
        source_start_segment_id=organization_start_id,
        source_end_segment_id=organization_end_id,
        created_by_job_id=job_id,
        created_by_job_attempt=1,
        model_name=None,
        prompt_version="answer-v1",
        created_at=now,
    )
    segments = {
        original_start_id: SimpleNamespace(sequence=1),
        original_end_id: SimpleNamespace(sequence=2),
        organization_start_id: SimpleNamespace(sequence=3),
        organization_end_id: SimpleNamespace(sequence=4),
    }
    session = _ProjectionSessionStub(
        lecture_session=SimpleNamespace(
            canonical_transcript_version_id=transcript_version_id,
            status="PROCESSING",
        ),
        organization=organization,
        organization_job=SimpleNamespace(
            id=job_id,
            job_type="ANSWER_ORGANIZATION",
            target_answer_id=answer_id,
            status="SUCCEEDED",
            attempt=1,
            retryable=False,
        ),
        segments=segments,
    )
    service = AnswerService(
        auth_secret="projection-test-secret",
        repository=_AnswerRepositoryStub(),  # type: ignore[arg-type]
    )

    projected = asyncio.run(service.project(session, answer))  # type: ignore[arg-type]

    assert projected.organization_state.status == "SUCCEEDED"
    assert projected.organization_state.organization is not None
    assert projected.organization_state.organization.content == organization.content
    assert projected.organization_state.organization.start_sequence == 3
    assert projected.organization_state.organization.end_sequence == 4


@pytest.mark.parametrize(
    ("job_status", "job_attempt"),
    [(None, None), ("RUNNING", 1), ("SUCCEEDED", 2)],
)
def test_answer_projection_rejects_an_inconsistent_organization_ledger(
    job_status: str | None, job_attempt: int | None
) -> None:
    now = datetime.now(UTC)
    session_id = uuid4()
    answer_id = uuid4()
    transcript_version_id = uuid4()
    job_id = uuid4()
    answer = SimpleNamespace(
        id=answer_id,
        session_id=session_id,
        version=2,
        status="COMPLETED",
        target_question_id=uuid4(),
        target_representative_question_id=None,
        target_text_snapshot="왜 최단 경로가 보장되나요?",
        text_content=None,
        source_transcript_version_id=transcript_version_id,
        capture_started_after_sequence=0,
        start_segment_id=None,
        end_segment_id=None,
        started_at=now,
        completed_at=now,
        updated_at=now,
    )
    organization = SimpleNamespace(
        answer_id=answer_id,
        content="확정 Transcript 범위로 답변을 정리했습니다.",
        source_transcript_version_id=transcript_version_id,
        source_start_segment_id=uuid4(),
        source_end_segment_id=uuid4(),
        created_by_job_id=job_id,
        created_by_job_attempt=1,
        model_name=None,
        prompt_version="answer-v1",
        created_at=now,
    )
    organization_job = (
        SimpleNamespace(
            id=job_id,
            job_type="ANSWER_ORGANIZATION",
            target_answer_id=answer_id,
            status=job_status,
            attempt=job_attempt,
            retryable=False,
        )
        if job_status is not None and job_attempt is not None
        else None
    )
    session = _ProjectionSessionStub(
        lecture_session=SimpleNamespace(
            canonical_transcript_version_id=transcript_version_id,
            status="PROCESSING",
        ),
        organization=organization,
        organization_job=organization_job,
        segments={},
    )
    service = AnswerService(
        auth_secret="projection-test-secret",
        repository=_AnswerRepositoryStub(),  # type: ignore[arg-type]
    )

    projected = asyncio.run(service.project(session, answer))  # type: ignore[arg-type]

    assert projected.organization_state.status == "DATA_INTEGRITY_ERROR"
    assert projected.organization_state.job_id == (
        organization_job.id if organization_job is not None else None
    )
    assert projected.organization_state.organization is None


def test_answer_projection_never_marks_an_active_organization_job_retryable() -> None:
    now = datetime.now(UTC)
    session_id = uuid4()
    transcript_version_id = uuid4()
    job_id = uuid4()
    answer = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        version=2,
        status="COMPLETED",
        target_question_id=uuid4(),
        target_representative_question_id=None,
        target_text_snapshot="왜 우선순위 큐를 사용하나요?",
        text_content=None,
        source_transcript_version_id=transcript_version_id,
        capture_started_after_sequence=0,
        start_segment_id=None,
        end_segment_id=None,
        started_at=now,
        completed_at=now,
        updated_at=now,
    )
    session = _ProjectionSessionStub(
        lecture_session=SimpleNamespace(
            canonical_transcript_version_id=transcript_version_id,
            status="PROCESSING",
        ),
        organization=None,
        organization_job=SimpleNamespace(
            id=job_id,
            status="RUNNING",
            attempt=1,
            retryable=True,
        ),
        segments={},
    )
    service = AnswerService(
        auth_secret="projection-test-secret",
        repository=_AnswerRepositoryStub(),  # type: ignore[arg-type]
    )

    projected = asyncio.run(service.project(session, answer))  # type: ignore[arg-type]

    assert projected.organization_state.status == "RUNNING"
    assert projected.organization_state.retryable is False
    assert projected.organization_state.organization is None


class _JobResultSessionStub:
    def __init__(self, *, scalar_result: object = None, state: object = None) -> None:
        self.scalar_result = scalar_result
        self.state = state

    async def scalar(self, _statement: object) -> object | None:
        return self.scalar_result

    async def get(self, model: object, _identity: object) -> object | None:
        assert model is QuestionClusteringState
        return self.state


@pytest.mark.parametrize(
    ("job_type", "resource_type"),
    [
        ("RECORDING_TRANSCRIPTION", "TRANSCRIPT_VERSION"),
        ("FINAL_SUMMARY", "SUMMARY"),
        ("CHAT_RESPONSE", "CHAT_MESSAGE"),
        ("ANSWER_ORGANIZATION", "ANSWER"),
    ],
)
def test_successful_shared_job_projects_its_durable_result(
    job_type: str, resource_type: str
) -> None:
    job_id = uuid4()
    session_id = uuid4()
    result_id = uuid4()
    ledger = (
        SimpleNamespace(answer_id=result_id)
        if job_type == "ANSWER_ORGANIZATION"
        else SimpleNamespace(id=result_id)
    )
    job = SimpleNamespace(
        id=job_id,
        session_id=session_id,
        job_type=job_type,
        status="SUCCEEDED",
        attempt=2,
        clustering_mode=None,
    )

    projection = asyncio.run(
        AIJobResultService().project(  # type: ignore[arg-type]
            _JobResultSessionStub(scalar_result=ledger),  # type: ignore[arg-type]
            job,  # type: ignore[arg-type]
        )
    )

    assert projection.unavailable_reason is None
    assert projection.result is not None
    assert projection.result.resource_type == resource_type
    assert projection.result.resource_id == str(result_id)


@pytest.mark.parametrize(
    "job_type",
    [
        "LIVE_SUMMARY",
        "FINAL_SUMMARY",
        "CHAT_RESPONSE",
        "RECORDING_TRANSCRIPTION",
        "ANSWER_ORGANIZATION",
    ],
)
def test_successful_job_never_hides_a_missing_required_result(job_type: str) -> None:
    job = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        job_type=job_type,
        status="SUCCEEDED",
        attempt=1,
        clustering_mode=None,
    )

    with pytest.raises(JobResultIntegrityError):
        asyncio.run(
            AIJobResultService().project(  # type: ignore[arg-type]
                _JobResultSessionStub(scalar_result=None),  # type: ignore[arg-type]
                job,  # type: ignore[arg-type]
            )
        )


def test_clustering_job_result_only_points_to_its_current_generation() -> None:
    job_id = uuid4()
    session_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        session_id=session_id,
        job_type="QUESTION_CLUSTERING",
        status="SUCCEEDED",
        attempt=1,
        clustering_mode="FINAL",
    )
    state = SimpleNamespace(current_generation=4, final_generation=4)

    current = asyncio.run(
        AIJobResultService().project(  # type: ignore[arg-type]
            _JobResultSessionStub(
                scalar_result=SimpleNamespace(
                    created_by_job_id=job_id,
                    created_by_job_attempt=1,
                ),
                state=state,
            ),  # type: ignore[arg-type]
            job,  # type: ignore[arg-type]
        )
    )
    superseded = asyncio.run(
        AIJobResultService().project(  # type: ignore[arg-type]
            _JobResultSessionStub(
                scalar_result=SimpleNamespace(
                    created_by_job_id=uuid4(),
                    created_by_job_attempt=1,
                ),
                state=state,
            ),  # type: ignore[arg-type]
            job,  # type: ignore[arg-type]
        )
    )

    assert current.result is not None
    assert current.result.resource_type == "QUESTION_CLUSTER_GENERATION"
    assert current.result.resource_id == "4"
    assert current.result.resource_url is not None
    assert current.result.resource_url.endswith("scope=FINAL")
    assert superseded.result is None
    assert superseded.unavailable_reason == "SUPERSEDED"

    with pytest.raises(JobResultIntegrityError):
        asyncio.run(
            AIJobResultService().project(  # type: ignore[arg-type]
                _JobResultSessionStub(scalar_result=None, state=state),  # type: ignore[arg-type]
                job,  # type: ignore[arg-type]
            )
        )

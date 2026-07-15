import type { components } from '../../src/api/generated/schema'

export const visualUser = {
  id: '00000000-0000-0000-0000-000000000001',
  display_name: '김도현',
  email: 'dohyun@example.test',
  avatar_url: null,
} satisfies components['schemas']['User']

export const professorCourse = {
  id: '10000000-0000-0000-0000-000000000001',
  title: '데이터 구조와 알고리즘',
  semester: '2026 여름학기',
  role: 'PROFESSOR',
  join_code: 'GOALAB',
  current_session: {
    id: '30000000-0000-0000-0000-000000000001',
    title: '그래프 탐색과 최단 경로',
    lecture_date: '2026-07-15',
    status: 'LIVE',
    started_at: '2026-07-15T06:00:00Z',
  },
  created_at: '2026-07-14T00:00:00Z',
} satisfies components['schemas']['Course']

export const professorDraftCourse = {
  id: '10000000-0000-0000-0000-000000000004',
  title: '알고리즘 설계 실습',
  semester: '2026 여름학기',
  role: 'PROFESSOR',
  join_code: 'READY4',
  current_session: null,
  created_at: '2026-07-15T00:00:00Z',
} satisfies components['schemas']['Course']

export const studentCourse = {
  id: '20000000-0000-0000-0000-000000000001',
  title: '운영체제',
  semester: '2026 여름학기',
  role: 'STUDENT',
  current_session: null,
  created_at: '2026-07-13T00:00:00Z',
} satisfies components['schemas']['Course']

export const studentWorkspaceCourse = {
  ...studentCourse,
  current_session: {
    id: '30000000-0000-0000-0000-000000000002',
    title: '프로세스 동기화와 교착 상태',
    lecture_date: '2026-07-16',
    status: 'READY',
    started_at: null,
  },
} satisfies components['schemas']['Course']

export const studentLiveCourse = {
  id: '20000000-0000-0000-0000-000000000005',
  title: '컴퓨터 네트워크',
  semester: '2026 여름학기',
  role: 'STUDENT',
  current_session: {
    id: '30000000-0000-0000-0000-000000000005',
    title: '혼잡 제어와 흐름 제어',
    lecture_date: '2026-07-15',
    status: 'LIVE',
    started_at: '2026-07-15T06:00:00Z',
  },
  created_at: '2026-07-10T00:00:00Z',
} satisfies components['schemas']['Course']

export const completedSession = {
  id: '30000000-0000-0000-0000-000000000010',
  course_id: professorCourse.id,
  title: '동적 계획법과 최적 부분 구조',
  lecture_date: '2026-07-14',
  status: 'COMPLETED',
  version: 3,
  canonical_transcript_version_id: '60000000-0000-0000-0000-000000000010',
  started_at: '2026-07-14T05:00:00Z',
  ended_at: '2026-07-14T06:10:00Z',
  completed_at: '2026-07-14T06:16:00Z',
  created_at: '2026-07-14T04:55:00Z',
  updated_at: '2026-07-14T06:16:00Z',
} satisfies components['schemas']['LectureSession']

export const readySession = {
  id: '30000000-0000-0000-0000-000000000004',
  course_id: professorDraftCourse.id,
  title: '그래프 탐색과 최단 경로',
  lecture_date: '2026-07-16',
  status: 'READY',
  version: 1,
  canonical_transcript_version_id: null,
  started_at: null,
  ended_at: null,
  completed_at: null,
  created_at: '2026-07-15T06:00:00Z',
  updated_at: '2026-07-15T06:00:00Z',
} satisfies components['schemas']['LectureSession']

export const liveProfessorSession = {
  id: professorCourse.current_session.id,
  course_id: professorCourse.id,
  title: professorCourse.current_session.title,
  lecture_date: professorCourse.current_session.lecture_date,
  status: 'LIVE',
  version: 2,
  canonical_transcript_version_id: '60000000-0000-0000-0000-000000000001',
  started_at: professorCourse.current_session.started_at,
  ended_at: null,
  completed_at: null,
  created_at: '2026-07-15T05:55:00Z',
  updated_at: '2026-07-15T06:34:00Z',
} satisfies components['schemas']['LectureSession']

export const liveStudentSession = {
  id: studentLiveCourse.current_session.id,
  course_id: studentLiveCourse.id,
  title: studentLiveCourse.current_session.title,
  lecture_date: studentLiveCourse.current_session.lecture_date,
  status: 'LIVE',
  version: 3,
  canonical_transcript_version_id: '60000000-0000-0000-0000-000000000005',
  started_at: studentLiveCourse.current_session.started_at,
  ended_at: null,
  completed_at: null,
  created_at: '2026-07-15T05:55:00Z',
  updated_at: '2026-07-15T06:34:00Z',
} satisfies components['schemas']['LectureSession']

export const professorProcessingCourse = {
  id: '10000000-0000-0000-0000-000000000007',
  title: '알고리즘 심화',
  semester: '2026 여름학기',
  role: 'PROFESSOR',
  join_code: 'PROC07',
  current_session: {
    id: '30000000-0000-0000-0000-000000000007',
    title: '그래프 탐색과 최단 경로',
    lecture_date: '2026-07-15',
    status: 'PROCESSING',
    started_at: '2026-07-15T06:00:00Z',
  },
  created_at: '2026-07-10T00:00:00Z',
} satisfies components['schemas']['Course']

export const studentProcessingCourse = {
  id: '20000000-0000-0000-0000-000000000008',
  title: '컴퓨터 구조',
  semester: '2026 여름학기',
  role: 'STUDENT',
  current_session: {
    id: '30000000-0000-0000-0000-000000000008',
    title: '캐시 일관성과 메모리 계층',
    lecture_date: '2026-07-15',
    status: 'PROCESSING',
    started_at: '2026-07-15T04:00:00Z',
  },
  created_at: '2026-07-10T00:00:00Z',
} satisfies components['schemas']['Course']

export const processingProfessorSession = {
  id: professorProcessingCourse.current_session.id,
  course_id: professorProcessingCourse.id,
  title: professorProcessingCourse.current_session.title,
  lecture_date: professorProcessingCourse.current_session.lecture_date,
  status: 'PROCESSING',
  version: 3,
  canonical_transcript_version_id: '60000000-0000-0000-0000-000000000017',
  started_at: professorProcessingCourse.current_session.started_at,
  ended_at: '2026-07-15T06:52:00Z',
  completed_at: null,
  created_at: '2026-07-15T05:55:00Z',
  updated_at: '2026-07-15T06:54:00Z',
} satisfies components['schemas']['LectureSession']

export const processingStudentSession = {
  id: studentProcessingCourse.current_session.id,
  course_id: studentProcessingCourse.id,
  title: studentProcessingCourse.current_session.title,
  lecture_date: studentProcessingCourse.current_session.lecture_date,
  status: 'PROCESSING',
  version: 4,
  canonical_transcript_version_id: '60000000-0000-0000-0000-000000000018',
  started_at: studentProcessingCourse.current_session.started_at,
  ended_at: '2026-07-15T04:48:00Z',
  completed_at: null,
  created_at: '2026-07-15T03:55:00Z',
  updated_at: '2026-07-15T04:50:00Z',
} satisfies components['schemas']['LectureSession']

function processingTime(
  session: typeof processingProfessorSession | typeof processingStudentSession,
  offsetMinutes: number,
) {
  return new Date(
    Date.parse(session.ended_at) + offsetMinutes * 60_000,
  ).toISOString()
}

function processingIds(
  session: typeof processingProfessorSession | typeof processingStudentSession,
) {
  const student = session.id === processingStudentSession.id
  return {
    answerId: '71000000-0000-0000-0000-000000000001',
    liveVersionId: student
      ? '60000000-0000-0000-0000-000000000008'
      : '60000000-0000-0000-0000-000000000007',
    recordingId: student
      ? '80000000-0000-0000-0000-000000000008'
      : '80000000-0000-0000-0000-000000000007',
  }
}

export function processingRecord(
  session: typeof processingProfessorSession | typeof processingStudentSession,
) {
  const { recordingId } = processingIds(session)
  const canonicalVersionId = session.canonical_transcript_version_id
  const currentVersion = {
    id: canonicalVersionId,
    session_id: session.id,
    source: 'RECORDING',
    status: 'FINALIZED',
    version: 2,
    last_sequence: 4,
    is_canonical: true,
    recording_id: recordingId,
    created_by_job_id: '90000000-0000-0000-0000-000000000071',
    created_by_job_attempt: 1,
    finalized_at: processingTime(session, 2),
    failed_at: null,
    created_at: processingTime(session, 1),
    updated_at: processingTime(session, 2),
  } satisfies components['schemas']['TranscriptVersion']
  const clusteringState = {
    pending: false,
    requested_through_sequence: 3,
    applied_through_sequence: 3,
    current_revision: 2,
    current_generation: 2,
    final_generation: null,
    active_job_id: '90000000-0000-0000-0000-000000000072',
    retry_job_id: null,
    last_job: {
      id: '90000000-0000-0000-0000-000000000072',
      attempt: 1,
      status: 'RUNNING',
      mode: 'FINAL',
    },
  } satisfies components['schemas']['QuestionClusteringState']
  return {
    session,
    recording: {
      id: recordingId,
      session_id: session.id,
      status: 'UPLOADED',
      version: 2,
      content_type: 'audio/webm',
      byte_size: 86_420_000,
      duration_ms:
        Date.parse(session.ended_at) - Date.parse(session.started_at),
      playback_url: `/api/v1/recordings/${recordingId}/playback`,
      created_at: session.started_at,
      updated_at: processingTime(session, 1),
    },
    recording_url: `/api/v1/sessions/${session.id}/recording`,
    materials: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/materials`,
    },
    transcript: {
      state: {
        session_id: session.id,
        status: 'FINALIZED' as const,
        current_version: currentVersion,
        canonical_version_id: canonicalVersionId,
        canonical_version: currentVersion,
        updated_at: processingTime(session, 2),
      },
      selected_version_id: canonicalVersionId,
      segment_count: 4,
      gap_count: 0,
      timeline_url: `/api/v1/sessions/${session.id}/transcript?transcript_version_id=${canonicalVersionId}`,
      versions_url: `/api/v1/sessions/${session.id}/transcript/versions`,
    },
    summary: {
      state: { status: 'PENDING', reason: null },
      summary_url: null,
      summaries_url: `/api/v1/sessions/${session.id}/summaries?summary_type=FINAL`,
    },
    questions: {
      total_count: 3,
      list_url: `/api/v1/sessions/${session.id}/questions?sort=RECENT`,
    },
    question_clusters: {
      state: clusteringState,
      current: {
        total_count: 2,
        list_url: `/api/v1/sessions/${session.id}/question-clusters?scope=CURRENT`,
      },
      final: {
        total_count: 0,
        list_url: `/api/v1/sessions/${session.id}/question-clusters?scope=FINAL`,
      },
    },
    answers: {
      total_count: 1,
      list_url: `/api/v1/sessions/${session.id}/answers`,
    },
    jobs: {
      total_count: 5,
      list_url: `/api/v1/sessions/${session.id}/jobs`,
    },
  }
}

export function processingTimeline(
  session: typeof processingProfessorSession | typeof processingStudentSession,
) {
  const record = processingRecord(session)
  const state = record.transcript.state
  const selectedVersion = state.canonical_version
  return {
    transcript: state,
    selected_version: selectedVersion,
    segments: [
      '다익스트라 알고리즘의 탐색 순서를 정리합니다.',
      '우선순위 큐가 갱신되는 조건을 다시 확인합니다.',
      '음수 가중치가 있는 경우의 한계를 비교합니다.',
      '마지막 예제와 질문을 확정 기록으로 연결합니다.',
    ].map((text, index) => ({
      id: `62000000-0000-0000-0000-${String(index + 1).padStart(12, '0')}`,
      session_id: session.id,
      transcript_version_id: selectedVersion.id,
      item_type: 'SEGMENT' as const,
      sequence: index + 1,
      start_ms: index * 45_000,
      end_ms: index * 45_000 + 38_000,
      recording_start_ms: index * 45_000,
      recording_end_ms: index * 45_000 + 38_000,
      text,
      created_at: processingTime(session, 2),
    })),
    gaps: [],
    next_cursor: null,
  } satisfies components['schemas']['TranscriptTimelinePage']
}

const processingAnswerQuestion =
  '음수 가중치가 하나라도 있으면 다익스트라를 사용할 수 없나요?'

export function processingQuestions(
  session: typeof processingProfessorSession | typeof processingStudentSession,
) {
  return [
    {
      id: '70000000-0000-0000-0000-000000000001',
      session_id: session.id,
      content: processingAnswerQuestion,
      status: 'ANSWERED',
      version: 3,
      clustering_sequence: 1,
      reaction_count: 14,
      reacted_by_me: false,
      cluster_id: null,
      created_at: processingTime(session, -32),
      updated_at: processingTime(session, -14),
    },
    {
      id: '70000000-0000-0000-0000-000000000002',
      session_id: session.id,
      content: '우선순위 큐에서 같은 거리의 정점은 어떤 순서로 꺼내나요?',
      status: 'OPEN',
      version: 1,
      clustering_sequence: 2,
      reaction_count: 9,
      reacted_by_me: true,
      cluster_id: null,
      created_at: processingTime(session, -28),
      updated_at: processingTime(session, -28),
    },
    {
      id: '70000000-0000-0000-0000-000000000003',
      session_id: session.id,
      content: '시간 복잡도에서 V와 E는 각각 무엇을 의미하나요?',
      status: 'OPEN',
      version: 1,
      clustering_sequence: 3,
      reaction_count: 6,
      reacted_by_me: false,
      cluster_id: null,
      created_at: processingTime(session, -24),
      updated_at: processingTime(session, -24),
    },
  ] satisfies components['schemas']['Question'][]
}

export function processingAnswer(
  session: typeof processingProfessorSession | typeof processingStudentSession,
) {
  const { answerId, liveVersionId } = processingIds(session)
  return {
    id: answerId,
    session_id: session.id,
    answer_type: 'VOICE',
    status: 'COMPLETED',
    version: 2,
    target: {
      type: 'STUDENT_QUESTION',
      question_id: '70000000-0000-0000-0000-000000000001',
    },
    target_text_snapshot: processingAnswerQuestion,
    text_content: null,
    source_transcript_version_id: liveVersionId,
    canonical_transcript_mapping: {
      target_transcript_version_id: session.canonical_transcript_version_id,
      status: 'SUCCEEDED',
      start_segment_id: '62000000-0000-0000-0000-000000000003',
      end_segment_id: '62000000-0000-0000-0000-000000000004',
      updated_at: processingTime(session, 3),
    },
    organization_state: {
      status: 'RUNNING',
      job_id: '90000000-0000-0000-0000-000000000073',
      attempt: 1,
      retryable: false,
      organization: null,
    },
    capture_started_after_sequence: 2,
    start_sequence: 3,
    end_sequence: 4,
    started_at: processingTime(session, -18),
    completed_at: processingTime(session, -14),
    updated_at: processingTime(session, 4),
  } satisfies components['schemas']['Answer']
}

export function processingJobs(
  session: typeof processingProfessorSession | typeof processingStudentSession,
) {
  const sessionId = session.id
  const { answerId, recordingId } = processingIds(session)
  const job = (
    id: string,
    jobType: components['schemas']['AIJobType'],
    status: components['schemas']['AIJobStatus'],
    clustering: components['schemas']['QuestionClusteringJobContext'] | null,
    target: components['schemas']['AIJobResourceLink'],
    createdOffset: number,
    startedOffset: number | null,
    finishedOffset: number | null,
  ) =>
    ({
      id,
      session_id: sessionId,
      job_type: jobType,
      visibility: 'SHARED',
      status,
      attempt: 1,
      version: finishedOffset !== null ? 3 : startedOffset !== null ? 2 : 1,
      progress: null,
      retryable: status === 'FAILED',
      blocks_session_completion: true,
      clustering,
      error: null,
      target,
      result:
        status === 'SUCCEEDED' && jobType === 'RECORDING_TRANSCRIPTION'
          ? {
              resource_type: 'TRANSCRIPT_VERSION',
              resource_id: session.canonical_transcript_version_id,
              resource_url: `/api/v1/sessions/${sessionId}/transcript?transcript_version_id=${session.canonical_transcript_version_id}`,
            }
          : null,
      result_unavailable_reason: null,
      created_at: processingTime(session, createdOffset),
      updated_at: processingTime(
        session,
        finishedOffset ?? startedOffset ?? createdOffset,
      ),
      started_at:
        startedOffset === null ? null : processingTime(session, startedOffset),
      finished_at:
        finishedOffset === null
          ? null
          : processingTime(session, finishedOffset),
    }) satisfies components['schemas']['AIJob']
  return [
    job(
      '90000000-0000-0000-0000-000000000075',
      'FINAL_SUMMARY',
      'PENDING',
      null,
      {
        resource_type: 'SESSION',
        resource_id: sessionId,
        resource_url: `/api/v1/sessions/${sessionId}`,
      },
      3,
      null,
      null,
    ),
    job(
      '90000000-0000-0000-0000-000000000073',
      'ANSWER_ORGANIZATION',
      'RUNNING',
      null,
      {
        resource_type: 'ANSWER',
        resource_id: answerId,
        resource_url: `/api/v1/answers/${answerId}`,
      },
      3,
      3,
      null,
    ),
    job(
      '90000000-0000-0000-0000-000000000074',
      'SESSION_POSTPROCESSING',
      'SUCCEEDED',
      null,
      {
        resource_type: 'SESSION',
        resource_id: sessionId,
        resource_url: `/api/v1/sessions/${sessionId}`,
      },
      0,
      2,
      3,
    ),
    job(
      '90000000-0000-0000-0000-000000000071',
      'RECORDING_TRANSCRIPTION',
      'SUCCEEDED',
      null,
      {
        resource_type: 'RECORDING',
        resource_id: recordingId,
        resource_url: `/api/v1/recordings/${recordingId}/playback`,
      },
      1,
      1,
      2,
    ),
    job(
      '90000000-0000-0000-0000-000000000072',
      'QUESTION_CLUSTERING',
      'RUNNING',
      {
        mode: 'FINAL',
        input_through_sequence: 3,
        base_revision: 2,
        final_answered_through_at: session.ended_at,
      },
      {
        resource_type: 'SESSION',
        resource_id: sessionId,
        resource_url: `/api/v1/sessions/${sessionId}`,
      },
      0,
      0,
      null,
    ),
  ]
}

export function liveTimeline(sessionId: string, versionId: string) {
  const version = {
    id: versionId,
    session_id: sessionId,
    source: 'LIVE',
    status: 'FINALIZING',
    version: 1,
    last_sequence: 4,
    is_canonical: true,
    recording_id: null,
    created_by_job_id: null,
    created_by_job_attempt: null,
    finalized_at: null,
    failed_at: null,
    created_at: '2026-07-15T06:00:00Z',
    updated_at: '2026-07-15T06:34:00Z',
  } satisfies components['schemas']['TranscriptVersion']
  const copy = [
    '다익스트라 알고리즘은 현재 거리가 가장 짧은 정점을 먼저 확정합니다.',
    '우선순위 큐를 사용하면 간선 완화 과정을 더 효율적으로 처리할 수 있습니다.',
    '음수 가중치가 있으면 이미 확정한 최단 거리 가정이 깨질 수 있습니다.',
    '다음으로 벨만-포드 알고리즘과의 차이를 예제로 비교하겠습니다.',
  ]
  const segments = copy.map((text, index) => ({
    id: `61000000-0000-0000-0000-${String(index + 1).padStart(12, '0')}`,
    session_id: sessionId,
    transcript_version_id: versionId,
    item_type: 'SEGMENT' as const,
    sequence: index + 1,
    start_ms: index * 42_000,
    end_ms: index * 42_000 + 35_000,
    recording_start_ms: null,
    recording_end_ms: null,
    text,
    created_at: `2026-07-15T06:${String(index * 2).padStart(2, '0')}:00Z`,
  })) satisfies components['schemas']['TranscriptSegment'][]

  return {
    transcript: {
      session_id: sessionId,
      status: 'FINALIZING',
      current_version: version,
      canonical_version_id: versionId,
      canonical_version: version,
      updated_at: '2026-07-15T06:34:00Z',
    },
    selected_version: version,
    segments,
    gaps: [],
    next_cursor: null,
  } satisfies components['schemas']['TranscriptTimelinePage']
}

export function liveQuestions(sessionId: string) {
  return [
    {
      id: '70000000-0000-0000-0000-000000000001',
      session_id: sessionId,
      content: '음수 가중치가 하나라도 있으면 다익스트라를 사용할 수 없나요?',
      status: 'OPEN',
      version: 1,
      clustering_sequence: 1,
      reaction_count: 14,
      reacted_by_me: false,
      cluster_id: null,
      created_at: '2026-07-15T06:20:00Z',
      updated_at: '2026-07-15T06:20:00Z',
    },
    {
      id: '70000000-0000-0000-0000-000000000002',
      session_id: sessionId,
      content: '우선순위 큐에서 같은 거리의 정점은 어떤 순서로 꺼내나요?',
      status: 'SELECTED',
      version: 2,
      clustering_sequence: 2,
      reaction_count: 9,
      reacted_by_me: true,
      cluster_id: null,
      created_at: '2026-07-15T06:24:00Z',
      updated_at: '2026-07-15T06:29:00Z',
    },
    {
      id: '70000000-0000-0000-0000-000000000003',
      session_id: sessionId,
      content: '시간 복잡도에서 V와 E는 각각 무엇을 의미하나요?',
      status: 'ANSWERED',
      version: 3,
      clustering_sequence: 3,
      reaction_count: 6,
      reacted_by_me: false,
      cluster_id: null,
      created_at: '2026-07-15T06:28:00Z',
      updated_at: '2026-07-15T06:32:00Z',
    },
  ] satisfies components['schemas']['Question'][]
}

export const readyMaterial = {
  id: '40000000-0000-0000-0000-000000000004',
  session_id: readySession.id,
  display_name: '그래프-탐색-핵심정리.pdf',
  mime_type: 'application/pdf',
  byte_size: 2_480_320,
  page_count: 18,
  processing_status: 'READY',
  created_at: '2026-07-15T06:02:00Z',
} satisfies components['schemas']['LectureMaterial']

export const failedMaterial = {
  id: '40000000-0000-0000-0000-000000000005',
  session_id: readySession.id,
  display_name: '추가-연습문제.pdf',
  mime_type: 'application/pdf',
  byte_size: 930_120,
  page_count: null,
  processing_status: 'FAILED',
  created_at: '2026-07-15T06:03:00Z',
} satisfies components['schemas']['LectureMaterial']

export const failedMaterialJob = {
  id: '50000000-0000-0000-0000-000000000004',
  session_id: readySession.id,
  job_type: 'MATERIAL_PROCESSING',
  visibility: 'SHARED',
  status: 'FAILED',
  attempt: 1,
  version: 2,
  progress: null,
  retryable: true,
  blocks_session_completion: false,
  clustering: null,
  error: {
    code: 'MATERIAL_PROCESSING_FAILED',
    message: '강의자료 처리에 실패했습니다.',
    retryable: true,
  },
  target: {
    resource_type: 'MATERIAL',
    resource_id: failedMaterial.id,
    resource_url: null,
  },
  result: null,
  result_unavailable_reason: null,
  created_at: '2026-07-15T06:03:00Z',
  updated_at: '2026-07-15T06:04:00Z',
  started_at: '2026-07-15T06:03:10Z',
  finished_at: '2026-07-15T06:04:00Z',
} satisfies components['schemas']['AIJob']

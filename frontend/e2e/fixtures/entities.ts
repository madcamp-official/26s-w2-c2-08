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

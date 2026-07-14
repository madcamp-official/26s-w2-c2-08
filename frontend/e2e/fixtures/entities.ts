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

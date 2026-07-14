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

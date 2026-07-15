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
  current_session: null,
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

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { appRoutes } from '../../app/router'
import { ToastProvider } from '../../components/feedback/ToastProvider'
import { createQueryClient } from '../../lib/query/query-client'
import { server } from '../../test/server'
import { courseKeys } from './queries'

const user = {
  id: '00000000-0000-0000-0000-000000000001',
  display_name: '김도현',
  email: 'dohyun@example.test',
  avatar_url: null,
}

const professorCourse = {
  id: '10000000-0000-0000-0000-000000000001',
  title: '알고리즘',
  semester: '2026 여름학기',
  role: 'PROFESSOR' as const,
  join_code: 'ABCXYZ',
  current_session: null,
  created_at: '2026-07-14T00:00:00Z',
}

const studentCourse = {
  id: '20000000-0000-0000-0000-000000000001',
  title: '운영체제',
  semester: '2026 여름학기',
  role: 'STUDENT' as const,
  current_session: null,
  created_at: '2026-07-13T00:00:00Z',
}

const liveSessionSummary = {
  id: '30000000-0000-0000-0000-000000000099',
  title: '그래프 탐색과 최단 경로',
  lecture_date: '2026-07-15',
  status: 'LIVE' as const,
  started_at: '2026-07-15T06:00:00Z',
}

const readySession = {
  id: '30000000-0000-0000-0000-000000000001',
  course_id: professorCourse.id,
  title: '알고리즘 · 2026.07.14 15:00',
  lecture_date: '2026-07-14',
  status: 'READY' as const,
  version: 1,
  canonical_transcript_version_id: null,
  started_at: null,
  ended_at: null,
  completed_at: null,
  created_at: '2026-07-14T06:00:00Z',
  updated_at: '2026-07-14T06:00:00Z',
}

function renderAt(
  path: string,
  queryClient: QueryClient = createQueryClient(),
) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return router
}

function authenticate() {
  server.use(http.get('*/api/v1/me', () => HttpResponse.json(user)))
}

function liveSessionFor(courseId: string) {
  return {
    ...readySession,
    course_id: courseId,
    title: '그래프 탐색과 최단 경로',
    status: 'LIVE' as const,
    version: 2,
    started_at: '2026-07-15T06:00:00Z',
    updated_at: '2026-07-15T06:00:00Z',
  }
}

function processingSessionFor(courseId: string, suffix: string) {
  return {
    ...readySession,
    id: `30000000-0000-0000-0000-${suffix}`,
    course_id: courseId,
    title:
      courseId === professorCourse.id
        ? '그래프 기록 정리'
        : '운영체제 기록 정리',
    status: 'PROCESSING' as const,
    version: 3,
    started_at: '2026-07-15T06:00:00Z',
    ended_at: '2026-07-15T06:52:00Z',
    updated_at: '2026-07-15T06:54:00Z',
  }
}

function processingRecordFor(session: ReturnType<typeof processingSessionFor>) {
  return {
    session,
    recording: null,
    recording_url: `/api/v1/sessions/${session.id}/recording`,
    materials: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/materials`,
    },
    transcript: {
      state: null,
      selected_version_id: null,
      segment_count: 0,
      gap_count: 0,
      timeline_url: `/api/v1/sessions/${session.id}/transcript`,
      versions_url: `/api/v1/sessions/${session.id}/transcript/versions`,
    },
    summary: {
      state: { status: 'PENDING', reason: null },
      summary_url: null,
      summaries_url: `/api/v1/sessions/${session.id}/summaries?summary_type=FINAL`,
    },
    questions: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/questions?sort=RECENT`,
    },
    question_clusters: {
      state: {
        pending: false,
        requested_through_sequence: 0,
        applied_through_sequence: 0,
        current_revision: 0,
        current_generation: null,
        final_generation: null,
        active_job_id: null,
        retry_job_id: null,
        last_job: null,
      },
      current: {
        total_count: 0,
        list_url: `/api/v1/sessions/${session.id}/question-clusters?scope=CURRENT`,
      },
      final: {
        total_count: 0,
        list_url: `/api/v1/sessions/${session.id}/question-clusters?scope=FINAL`,
      },
    },
    answers: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/answers`,
    },
    jobs: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/jobs`,
    },
  }
}

function completedSessionFor(courseId: string, suffix: string) {
  return {
    ...readySession,
    id: `30000000-0000-0000-0000-${suffix}`,
    course_id: courseId,
    title:
      courseId === professorCourse.id
        ? '동적 계획법과 최적 부분 구조'
        : '가상 메모리와 페이지 교체',
    lecture_date: '2026-07-14',
    status: 'COMPLETED' as const,
    version: 4,
    started_at: '2026-07-14T05:00:00Z',
    ended_at: '2026-07-14T06:10:00Z',
    completed_at: '2026-07-14T06:16:00Z',
    updated_at: '2026-07-14T06:16:00Z',
  }
}

function completedRecordFor(session: ReturnType<typeof completedSessionFor>) {
  return {
    session,
    recording: null,
    recording_url: `/api/v1/sessions/${session.id}/recording`,
    materials: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/materials`,
    },
    transcript: {
      state: {
        session_id: session.id,
        status: 'EMPTY',
        current_version: null,
        canonical_version_id: null,
        canonical_version: null,
        updated_at: session.completed_at,
      },
      selected_version_id: null,
      segment_count: 0,
      gap_count: 0,
      timeline_url: `/api/v1/sessions/${session.id}/transcript`,
      versions_url: `/api/v1/sessions/${session.id}/transcript/versions`,
    },
    summary: {
      state: {
        status: 'NOT_APPLICABLE',
        reason: {
          code: 'NO_FINAL_TRANSCRIPT',
          message: '요약할 확정 강의 내용이 없습니다.',
        },
      },
      summary_url: null,
      summaries_url: `/api/v1/sessions/${session.id}/summaries?summary_type=FINAL`,
    },
    questions: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/questions?sort=RECENT`,
    },
    question_clusters: {
      state: {
        pending: false,
        requested_through_sequence: 0,
        applied_through_sequence: 0,
        current_revision: 0,
        current_generation: null,
        final_generation: null,
        active_job_id: null,
        retry_job_id: null,
        last_job: null,
      },
      current: {
        total_count: 0,
        list_url: `/api/v1/sessions/${session.id}/question-clusters?scope=CURRENT`,
      },
      final: {
        total_count: 0,
        list_url: `/api/v1/sessions/${session.id}/question-clusters?scope=FINAL`,
      },
    },
    answers: {
      total_count: 0,
      list_url: `/api/v1/sessions/${session.id}/answers`,
    },
    jobs: {
      total_count: 1,
      list_url: `/api/v1/sessions/${session.id}/jobs`,
    },
  }
}

function installLiveRouteHandlers(
  course: typeof professorCourse | typeof studentCourse,
  session: ReturnType<typeof liveSessionFor>,
  onProfessorOnlyRequest?: () => void,
) {
  const version = {
    id: '70000000-0000-0000-0000-000000000001',
    session_id: session.id,
    source: 'LIVE',
    status: 'LIVE',
    version: 1,
    last_sequence: 0,
    is_canonical: true,
    recording_id: null,
    created_by_job_id: null,
    created_by_job_attempt: null,
    finalized_at: null,
    failed_at: null,
    created_at: '2026-07-15T06:00:00Z',
    updated_at: '2026-07-15T06:00:00Z',
  }
  server.use(
    http.get('*/api/v1/sessions/:sessionId', () => HttpResponse.json(session)),
    http.get('*/api/v1/courses/:courseId', () => HttpResponse.json(course)),
    http.get('*/api/v1/sessions/:sessionId/transcript', () =>
      HttpResponse.json({
        transcript: {
          session_id: session.id,
          status: 'LIVE',
          current_version: version,
          canonical_version_id: version.id,
          canonical_version: version,
          updated_at: '2026-07-15T06:00:00Z',
        },
        selected_version: version,
        segments: [],
        gaps: [],
        next_cursor: null,
      }),
    ),
    http.get('*/api/v1/sessions/:sessionId/questions', () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get('*/api/v1/sessions/:sessionId/question-clusters', () =>
      HttpResponse.json({
        scope: 'CURRENT',
        generation: null,
        clustering_state: {
          pending: false,
          requested_through_sequence: 0,
          applied_through_sequence: 0,
          current_revision: 0,
          current_generation: null,
          final_generation: null,
          active_job_id: null,
          retry_job_id: null,
          last_job: null,
        },
        items: [],
        next_cursor: null,
      }),
    ),
    http.get('*/api/v1/sessions/:sessionId/chats', () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get('*/api/v1/sessions/:sessionId/answers', () => {
      onProfessorOnlyRequest?.()
      return HttpResponse.json({ items: [], next_cursor: null })
    }),
    http.get('*/api/v1/sessions/:sessionId/materials', () => {
      onProfessorOnlyRequest?.()
      return HttpResponse.json({ items: [], next_cursor: null })
    }),
    http.get('*/api/v1/sessions/:sessionId/jobs', () => {
      onProfessorOnlyRequest?.()
      return HttpResponse.json({ items: [], next_cursor: null })
    }),
  )
}

describe('Course role flows', () => {
  it('shows independent professor and student Course lists on the dashboard', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role')
        return HttpResponse.json({
          items:
            role === 'PROFESSOR'
              ? [
                  {
                    ...professorCourse,
                    current_session: liveSessionSummary,
                  },
                ]
              : [{ ...studentCourse, join_code: 'SHOULD_NOT_RENDER' }],
          next_cursor: null,
        })
      }),
    )
    renderAt('/')

    expect(
      await screen.findByRole('heading', { name: '내가 관리 중인 Course' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '내가 참여 중인 Course' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('ABCXYZ')).toBeInTheDocument()
    expect(screen.getAllByText('알고리즘')).not.toHaveLength(0)
    expect(screen.getByText('운영체제')).toBeInTheDocument()
    expect(screen.queryByText('SHOULD_NOT_RENDER')).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '그래프 탐색과 최단 경로' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '실시간 class 들어가기' }),
    ).toHaveAttribute('href', `/sessions/${liveSessionSummary.id}`)
    expect(screen.getAllByText('진행 중')).not.toHaveLength(0)
  })

  it('keeps each dashboard empty state connected to its production flow', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt('/')

    expect(
      await screen.findByRole('heading', {
        name: '아직 만든 Course가 없습니다',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '아직 참여한 Course가 없습니다' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '첫 Course 만들기' }),
    ).toHaveAttribute('href', '/courses/new')
    expect(
      screen.getByRole('link', { name: '참여 코드 입력하기' }),
    ).toHaveAttribute('href', '/courses/join')
  })

  it('keeps a successful dashboard role visible while retrying the failed role', async () => {
    authenticate()
    let professorRequests = 0
    server.use(
      http.get('*/api/v1/courses', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role')
        if (role === 'STUDENT') {
          return HttpResponse.json({
            items: [studentCourse],
            next_cursor: null,
          })
        }

        professorRequests += 1
        if (professorRequests <= 2) {
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: '잠시 후 다시 시도해 주세요.',
                request_id: 'req_professor_courses',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return HttpResponse.json({
          items: [professorCourse],
          next_cursor: null,
        })
      }),
    )
    renderAt('/')

    expect(await screen.findByText('운영체제')).toBeInTheDocument()
    expect(
      await screen.findByText(
        '내가 관리 중인 Course를 불러오지 못했습니다',
        undefined,
        { timeout: 3_000 },
      ),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '이 목록 다시 시도' }))

    expect(await screen.findByText('ABCXYZ')).toBeInTheDocument()
    expect(screen.getByText('운영체제')).toBeInTheDocument()
    expect(professorRequests).toBe(3)
  })

  it('loads the next dashboard Course page with the documented cursor', async () => {
    authenticate()
    const secondProfessorCourse = {
      ...professorCourse,
      id: '10000000-0000-0000-0000-000000000002',
      title: '컴퓨터 네트워크',
      join_code: 'NETWRK',
    }
    server.use(
      http.get('*/api/v1/courses', ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('role') === 'STUDENT') {
          return HttpResponse.json({ items: [], next_cursor: null })
        }
        if (url.searchParams.get('cursor') === 'next-professor-page') {
          return HttpResponse.json({
            items: [secondProfessorCourse],
            next_cursor: null,
          })
        }
        return HttpResponse.json({
          items: [professorCourse],
          next_cursor: 'next-professor-page',
        })
      }),
    )
    renderAt('/')

    fireEvent.click(
      await screen.findByRole('button', { name: 'Course 더 보기' }),
    )

    expect(await screen.findByText('컴퓨터 네트워크')).toBeInTheDocument()
    expect(screen.getByText('NETWRK')).toBeInTheDocument()
  })

  it('hides cached Course data when a dashboard list reports an expired session', async () => {
    let expired = false
    server.use(
      http.get('*/api/v1/me', () =>
        expired
          ? HttpResponse.json(
              {
                error: {
                  code: 'AUTHENTICATION_REQUIRED',
                  message: '로그인이 필요합니다.',
                  request_id: 'req_expired_me',
                  details: null,
                },
              },
              { status: 401 },
            )
          : HttpResponse.json(user),
      ),
      http.get('*/api/v1/courses', () => {
        expired = true
        return HttpResponse.json(
          {
            error: {
              code: 'AUTHENTICATION_REQUIRED',
              message: '로그인이 필요합니다.',
              request_id: 'req_expired_courses',
              details: null,
            },
          },
          { status: 401 },
        )
      }),
    )
    renderAt('/')

    expect(
      await screen.findByRole('heading', {
        name: '강의의 흐름을 놓치지 않도록',
      }),
    ).toBeInTheDocument()
    expect(screen.queryByText('ABCXYZ')).not.toBeInTheDocument()
    expect(
      await screen.findByRole('link', { name: '로그인하고 시작하기' }),
    ).toHaveAttribute('href', '/login?return_to=/')
  })

  it('does not render professor controls anywhere in a student Course DOM', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json({ ...studentCourse, join_code: 'SECRET' }),
      ),
    )
    renderAt(`/courses/${studentCourse.id}`)

    expect(
      await screen.findByRole('heading', { name: '학생 학습 공간' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('SECRET')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '코드 복사' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '새 코드로 교체' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Course 삭제' }),
    ).not.toBeInTheDocument()
  })

  it('renders join-code controls only for a professor Course', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
    )
    renderAt(`/courses/${professorCourse.id}`)

    expect(
      await screen.findByRole('heading', { name: '학생 참여 코드' }),
    ).toBeInTheDocument()
    expect(screen.getByText('ABCXYZ')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '새 코드로 교체' }),
    ).toBeInTheDocument()
  })

  it('keeps one idempotency key while retrying a join-code rotation', async () => {
    authenticate()
    const keys: string[] = []
    let attempts = 0
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.post(
        '*/api/v1/courses/:courseId/join-code/rotate',
        ({ request }) => {
          keys.push(request.headers.get('Idempotency-Key') ?? '')
          attempts += 1
          if (attempts === 1) {
            return HttpResponse.json(
              {
                error: {
                  code: 'DEPENDENCY_UNAVAILABLE',
                  message: '잠시 후 다시 시도해 주세요.',
                  request_id: 'req_rotate_retry',
                  details: null,
                },
              },
              { status: 503 },
            )
          }
          return HttpResponse.json({ ...professorCourse, join_code: 'NEWCOD' })
        },
      ),
    )
    renderAt(`/courses/${professorCourse.id}`)

    fireEvent.click(
      await screen.findByRole('button', { name: '새 코드로 교체' }),
    )
    const dialog = screen.getByRole('dialog', {
      name: '참여 코드를 새로 만들까요?',
    })
    fireEvent.click(
      within(dialog).getByRole('button', { name: '새 코드로 교체' }),
    )
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      '기존 코드는 유지되었습니다',
    )
    expect(screen.getByText('ABCXYZ')).toBeInTheDocument()

    fireEvent.click(
      within(dialog).getByRole('button', { name: '새 코드로 교체' }),
    )
    expect(await screen.findByText('NEWCOD')).toBeInTheDocument()
    expect(keys).toHaveLength(2)
    expect(keys[0]).not.toBe('')
    expect(keys[1]).toBe(keys[0])
  })

  it('uses the Course role and status matrix for the active class action', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', ({ params }) => {
        const student = params.courseId === studentCourse.id
        return HttpResponse.json({
          ...(student ? studentCourse : professorCourse),
          current_session: {
            id: readySession.id,
            title: readySession.title,
            lecture_date: readySession.lecture_date,
            status: 'READY',
            started_at: null,
          },
        })
      }),
    )

    const router = renderAt(`/courses/${professorCourse.id}`)
    expect(
      await screen.findByRole('link', { name: 'class 준비 계속하기' }),
    ).toHaveAttribute('href', `/sessions/${readySession.id}`)

    await router.navigate(`/courses/${studentCourse.id}`)
    expect(
      await screen.findByText(
        '별도 동작 없이 기다려 주세요. 시작되면 입장 동작이 열립니다.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'class 준비 계속하기' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'class 보기' }),
    ).not.toBeInTheDocument()
  })

  it('opens only the student-safe action for a PROCESSING class', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json({
          ...studentCourse,
          join_code: 'NEVER_RENDER',
          current_session: {
            id: readySession.id,
            title: '운영체제 기록 정리',
            lecture_date: '2026-07-14',
            status: 'PROCESSING',
            started_at: '2026-07-14T06:00:00Z',
          },
        }),
      ),
    )
    renderAt(`/courses/${studentCourse.id}`)

    expect(
      await screen.findByRole('link', { name: '정리 상태 보기' }),
    ).toHaveAttribute('href', `/sessions/${readySession.id}`)
    expect(screen.queryByText('NEVER_RENDER')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Course 삭제' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '새 코드로 교체' }),
    ).not.toBeInTheDocument()
  })

  it('renders PROCESSING from the shared production route with Course role-safe controls', async () => {
    authenticate()
    const professorSession = processingSessionFor(
      professorCourse.id,
      '000000000071',
    )
    const studentSession = processingSessionFor(
      studentCourse.id,
      '000000000072',
    )
    server.use(
      http.get('*/api/v1/sessions/:sessionId', ({ params }) =>
        HttpResponse.json(
          params.sessionId === studentSession.id
            ? studentSession
            : professorSession,
        ),
      ),
      http.get('*/api/v1/courses/:courseId', ({ params }) =>
        HttpResponse.json(
          params.courseId === studentCourse.id
            ? studentCourse
            : professorCourse,
        ),
      ),
      http.get('*/api/v1/sessions/:sessionId/record', ({ params }) =>
        HttpResponse.json(
          processingRecordFor(
            params.sessionId === studentSession.id
              ? studentSession
              : professorSession,
          ),
        ),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/questions', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/question-clusters', ({ params }) =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state: processingRecordFor(
            params.sessionId === studentSession.id
              ? studentSession
              : professorSession,
          ).question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    const router = renderAt(`/sessions/${professorSession.id}`)
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: professorSession.title,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(
      screen.getByRole('textbox', { name: 'class 제목' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('수업 후처리 작업')).toBeInTheDocument()
    expect(
      screen.queryByText('미답변 학생 질문에 텍스트 답변'),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('복습 AI')).not.toBeInTheDocument()

    await router.navigate(`/sessions/${studentSession.id}`)
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: studentSession.title,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(
      screen.queryByRole('textbox', { name: 'class 제목' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Professor control')).not.toBeInTheDocument()
  })

  it('renders the completed professor production view with owner-only controls', async () => {
    authenticate()
    const completedSession = completedSessionFor(
      professorCourse.id,
      '000000000081',
    )
    const failedTranscriptJob = {
      id: '90000000-0000-0000-0000-000000000081',
      session_id: completedSession.id,
      job_type: 'RECORDING_TRANSCRIPTION',
      visibility: 'SHARED',
      status: 'FAILED',
      attempt: 1,
      version: 2,
      progress: null,
      retryable: true,
      blocks_session_completion: true,
      clustering: null,
      error: {
        code: 'PROVIDER_UNAVAILABLE',
        message: '고품질 Transcript를 만들지 못했습니다.',
      },
      target: {
        resource_type: 'SESSION',
        resource_id: completedSession.id,
        resource_url: `/api/v1/sessions/${completedSession.id}`,
      },
      result: null,
      result_unavailable_reason: null,
      created_at: '2026-07-14T06:10:00Z',
      updated_at: '2026-07-14T06:16:00Z',
      started_at: '2026-07-14T06:10:00Z',
      finished_at: '2026-07-14T06:16:00Z',
    }
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(completedSession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/record', () =>
        HttpResponse.json(completedRecordFor(completedSession)),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/questions', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/question-clusters', () =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state:
            completedRecordFor(completedSession).question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', ({ request }) =>
        HttpResponse.json({
          items: new URL(request.url).searchParams.has('job_type')
            ? []
            : [failedTranscriptJob],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderAt(`/sessions/${completedSession.id}`)

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: completedSession.title,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByText('복습할 수업 기록이 준비되었습니다')).toBeVisible()
    expect(screen.getByRole('textbox', { name: 'class 제목' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'class 삭제' })).toBeVisible()
    expect(await screen.findByLabelText('PDF 파일 선택')).toBeInTheDocument()
    expect(await screen.findByLabelText('보충 답변 내용')).toBeInTheDocument()
    expect(
      await screen.findByRole('button', {
        name: '고품질 Transcript 다시 시도',
      }),
    ).toBeVisible()
    expect(
      screen.getByRole('heading', { level: 2, name: '복습 AI' }),
    ).toBeVisible()
  })

  it('renders the completed student production view without owner controls', async () => {
    authenticate()
    const completedSession = completedSessionFor(
      studentCourse.id,
      '000000000082',
    )
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(completedSession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(studentCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/record', () =>
        HttpResponse.json(completedRecordFor(completedSession)),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/questions', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/question-clusters', () =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state:
            completedRecordFor(completedSession).question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderAt(`/sessions/${completedSession.id}`)

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: completedSession.title,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByText('복습할 수업 기록이 준비되었습니다')).toBeVisible()
    await screen.findByRole('heading', { level: 2, name: '강의자료' })
    expect(screen.queryByText('Professor control')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('textbox', { name: 'class 제목' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'class 삭제' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByLabelText('PDF 파일 선택')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('보충 답변 내용')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /다시 시도$/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: '복습 AI' }),
    ).toBeVisible()
  })

  it('clears cached Course data and preserves return_to after session expiry', async () => {
    let meRequests = 0
    server.use(
      http.get('*/api/v1/me', () => {
        meRequests += 1
        return meRequests === 1
          ? HttpResponse.json(user)
          : HttpResponse.json(
              {
                error: {
                  code: 'AUTHENTICATION_REQUIRED',
                  message: '로그인이 필요합니다.',
                  request_id: 'req_course_expired_me',
                  details: null,
                },
              },
              { status: 401 },
            )
      }),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(
          {
            error: {
              code: 'AUTHENTICATION_REQUIRED',
              message: '로그인이 필요합니다.',
              request_id: 'req_course_expired',
              details: null,
            },
          },
          { status: 401 },
        ),
      ),
    )
    const router = renderAt(`/courses/${professorCourse.id}`)

    expect(
      await screen.findByRole('heading', {
        name: '강의의 흐름으로 다시 들어오세요.',
      }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.search).toBe(
      `?return_to=%2Fcourses%2F${professorCourse.id}`,
    )
    expect(screen.queryByText('ABCXYZ')).not.toBeInTheDocument()
  })

  it('deletes a completed-only professor Course after confirmation', async () => {
    authenticate()
    let deleted = false
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.delete('*/api/v1/courses/:courseId', ({ request }) => {
        deleted = request.headers.has('Idempotency-Key')
        return new HttpResponse(null, { status: 204 })
      }),
      http.get('*/api/v1/courses', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    const router = renderAt(`/courses/${professorCourse.id}`)

    fireEvent.click(await screen.findByRole('button', { name: 'Course 삭제' }))
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Course 삭제',
      }),
    )

    await waitFor(() => expect(deleted).toBe(true))
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
  })

  it('creates a professor Course and joins another Course as a student', async () => {
    authenticate()
    server.use(
      http.post('*/api/v1/courses', () =>
        HttpResponse.json(professorCourse, { status: 201 }),
      ),
      http.post('*/api/v1/courses/join', () =>
        HttpResponse.json(studentCourse, { status: 201 }),
      ),
    )

    const createRouter = renderAt('/courses/new')
    fireEvent.change(await screen.findByLabelText('과목명'), {
      target: { value: '알고리즘' },
    })
    fireEvent.change(screen.getByLabelText('학기'), {
      target: { value: '2026 여름학기' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))
    expect(
      await screen.findByRole('heading', {
        name: '알고리즘 Course를 만들었습니다',
      }),
    ).toBeInTheDocument()

    await createRouter.navigate('/courses/join')
    fireEvent.change(await screen.findByLabelText('참여 코드'), {
      target: { value: 'abcxyz' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))
    await waitFor(() =>
      expect(
        screen.getByText('학생 역할로 참여합니다.', { exact: false }),
      ).toBeInTheDocument(),
    )
  })

  it('creates a READY class from the professor Course flow', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.post('*/api/v1/courses/:courseId/sessions', () =>
        HttpResponse.json(readySession, { status: 201 }),
      ),
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
    )
    renderAt(`/courses/${professorCourse.id}/sessions/new`)

    const createHeading = await screen.findByRole('heading', {
      name: '오늘의 class 준비',
    })
    expect(createHeading).toHaveAttribute('id', 'session-create-title')
    fireEvent.change(screen.getByLabelText('class 제목 (선택)'), {
      target: { value: '그래프 탐색' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'class 만들기' }))

    expect(
      await screen.findByRole('heading', { name: readySession.title }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '수업 시작' }),
    ).toBeInTheDocument()
  })

  it('focuses the required lecture date before sending a create request', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
    )
    renderAt(`/courses/${professorCourse.id}/sessions/new`)

    const lectureDate = await screen.findByLabelText(/^수업 날짜/)
    fireEvent.change(lectureDate, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'class 만들기' }))

    expect(lectureDate).toHaveFocus()
    expect(screen.getByText('수업 날짜를 선택해 주세요.')).toBeInTheDocument()
  })

  it('omits a blank title and keeps one idempotency key across create retries', async () => {
    authenticate()
    const keys: string[] = []
    const bodies: Array<Record<string, unknown>> = []
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.post('*/api/v1/courses/:courseId/sessions', async ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        bodies.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '잠시 후 다시 시도해 주세요.',
              request_id: 'req_create_retry',
              details: null,
            },
          },
          { status: 503 },
        )
      }),
    )
    renderAt(`/courses/${professorCourse.id}/sessions/new`)

    fireEvent.click(await screen.findByRole('button', { name: 'class 만들기' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'class 만들기' }))

    await waitFor(() => expect(keys).toHaveLength(2))
    expect(keys[0]).not.toBe('')
    expect(keys[1]).toBe(keys[0])
    expect(bodies[0]).not.toHaveProperty('title')
    expect(bodies[1]).toEqual(bodies[0])
  })

  it('clears create input and request identity when the route changes Courses', async () => {
    authenticate()
    const nextCourse = {
      ...professorCourse,
      id: '10000000-0000-0000-0000-000000000002',
      title: '컴퓨터 구조',
      join_code: 'NEXT01',
    }
    const requests: Array<{
      body: Record<string, unknown>
      courseId: string
      key: string
    }> = []
    server.use(
      http.get('*/api/v1/courses/:courseId', ({ params }) =>
        HttpResponse.json(
          params.courseId === nextCourse.id ? nextCourse : professorCourse,
        ),
      ),
      http.post(
        '*/api/v1/courses/:courseId/sessions',
        async ({ params, request }) => {
          requests.push({
            body: (await request.json()) as Record<string, unknown>,
            courseId: String(params.courseId),
            key: request.headers.get('Idempotency-Key') ?? '',
          })
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: '잠시 후 다시 시도해 주세요.',
                request_id: 'req_create_course_change',
                details: null,
              },
            },
            { status: 503 },
          )
        },
      ),
    )
    const router = renderAt(`/courses/${professorCourse.id}/sessions/new`)

    fireEvent.change(await screen.findByLabelText('class 제목 (선택)'), {
      target: { value: '이전 Course 입력' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'class 만들기' }))
    await screen.findByRole('alert')

    await router.navigate(`/courses/${nextCourse.id}/sessions/new`)

    expect(
      await screen.findByText(
        '컴퓨터 구조에 READY class를 만들고 선택적으로 PDF를 준비합니다.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('class 제목 (선택)')).toHaveValue('')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'class 만들기' }))

    await waitFor(() => expect(requests).toHaveLength(2))
    expect(requests[0].courseId).toBe(professorCourse.id)
    expect(requests[1].courseId).toBe(nextCourse.id)
    expect(requests[1].body).not.toHaveProperty('title')
    expect(requests[1].key).not.toBe(requests[0].key)
  })

  it('does not let a late create response replace a newly opened Course route', async () => {
    authenticate()
    const nextCourse = {
      ...professorCourse,
      id: '10000000-0000-0000-0000-000000000002',
      title: '컴퓨터 구조',
    }
    const queryClient = createQueryClient()
    let releaseCreate: (() => void) | undefined
    let responseReturned = false
    server.use(
      http.get('*/api/v1/courses/:courseId', ({ params }) =>
        HttpResponse.json(
          params.courseId === nextCourse.id ? nextCourse : professorCourse,
        ),
      ),
      http.post('*/api/v1/courses/:courseId/sessions', async () => {
        await new Promise<void>((resolve) => {
          releaseCreate = resolve
        })
        responseReturned = true
        return HttpResponse.json(readySession, { status: 201 })
      }),
    )
    const router = renderAt(
      `/courses/${professorCourse.id}/sessions/new`,
      queryClient,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'class 만들기' }))
    await waitFor(() => expect(releaseCreate).toBeDefined())
    expect(queryClient.isMutating()).toBe(1)

    await router.navigate(`/courses/${nextCourse.id}/sessions/new`)
    expect(
      await screen.findByText(
        '컴퓨터 구조에 READY class를 만들고 선택적으로 PDF를 준비합니다.',
      ),
    ).toBeInTheDocument()

    releaseCreate?.()
    await waitFor(() => expect(responseReturned).toBe(true))
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
    expect(router.state.location.pathname).toBe(
      `/courses/${nextCourse.id}/sessions/new`,
    )
    expect(screen.getByLabelText('class 제목 (선택)')).toHaveValue('')
  })

  it('allows a READY class with no PDF to start', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    const start = await screen.findByRole('button', { name: '수업 시작' })
    await waitFor(() => expect(start).toBeEnabled())
    expect(screen.getByText('연결된 강의자료가 없습니다')).toBeInTheDocument()
  })

  it('syncs an untouched READY title but preserves an edited title', async () => {
    authenticate()
    const queryClient = createQueryClient()
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt(`/sessions/${readySession.id}`, queryClient)

    const title = await screen.findByLabelText('class 제목')
    act(() => {
      queryClient.setQueryData(courseKeys.session(readySession.id), {
        ...readySession,
        title: '다른 탭에서 바꾼 제목',
        version: 2,
      })
    })

    await waitFor(() => expect(title).toHaveValue('다른 탭에서 바꾼 제목'))
    expect(screen.getByRole('button', { name: '제목 저장' })).toBeDisabled()

    fireEvent.change(title, { target: { value: '내가 편집 중인 제목' } })
    act(() => {
      queryClient.setQueryData(courseKeys.session(readySession.id), {
        ...readySession,
        title: '두 번째 외부 제목',
        version: 3,
      })
    })

    expect(title).toHaveValue('내가 편집 중인 제목')
    expect(screen.getByRole('button', { name: '제목 저장' })).toBeEnabled()
  })

  it('keeps cached READY controls and input visible when status polling fails', async () => {
    authenticate()
    let sessionRequests = 0
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () => {
        sessionRequests += 1
        if (sessionRequests === 1) return HttpResponse.json(readySession)
        return HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '잠시 후 다시 시도해 주세요.',
              request_id: 'req_ready_polling',
              details: null,
            },
          },
          { status: 503 },
        )
      }),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    const title = await screen.findByLabelText('class 제목')
    fireEvent.change(title, { target: { value: '저장 전 제목' } })
    expect(screen.getByRole('button', { name: '수업 시작' })).toBeEnabled()

    expect(
      await screen.findByText(
        '최신 class 상태를 확인하지 못했습니다',
        {
          exact: true,
        },
        { timeout: 9_000 },
      ),
    ).toBeInTheDocument()
    expect(title).toHaveValue('저장 전 제목')
    expect(screen.getByRole('button', { name: '수업 시작' })).toBeEnabled()
    expect(sessionRequests).toBeGreaterThanOrEqual(3)
  }, 10_000)

  it('keeps the READY delete dialog visible while deletion is pending', async () => {
    authenticate()
    let releaseDelete: (() => void) | undefined
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.delete('*/api/v1/sessions/:sessionId', async () => {
        await new Promise<void>((resolve) => {
          releaseDelete = resolve
        })
        return HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '잠시 후 다시 시도해 주세요.',
              request_id: 'req_ready_delete_pending',
              details: null,
            },
          },
          { status: 503 },
        )
      }),
    )
    renderAt(`/sessions/${readySession.id}`)

    fireEvent.click(await screen.findByRole('button', { name: 'class 삭제' }))
    const dialog = screen.getByRole('dialog', {
      name: 'READY class를 삭제할까요?',
    })
    const deleteAction = within(dialog).getByRole('button', {
      name: 'READY class 삭제',
    })
    fireEvent.click(deleteAction)
    await waitFor(() => expect(deleteAction).toBeDisabled())
    await waitFor(() => expect(releaseDelete).toBeDefined())

    fireEvent.click(
      within(dialog).getByRole('button', { name: '대화상자 닫기' }),
    )
    expect(dialog).toBeVisible()
    expect(deleteAction).toBeDisabled()

    releaseDelete?.()
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      '같은 요청으로 다시 시도할 수 있습니다',
    )
  })

  it('clears READY form and upload state when the route changes sessions', async () => {
    authenticate()
    const nextSession = {
      ...readySession,
      id: '30000000-0000-0000-0000-000000000002',
      title: '분할 정복과 재귀',
      version: 2,
    }
    server.use(
      http.get('*/api/v1/sessions/:sessionId', ({ params }) =>
        HttpResponse.json(
          params.sessionId === nextSession.id ? nextSession : readySession,
        ),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    const router = renderAt(`/sessions/${readySession.id}`)

    const heading = await screen.findByRole('heading', {
      name: readySession.title,
    })
    expect(heading).toHaveAttribute('id', 'session-detail-title')
    fireEvent.change(await screen.findByLabelText('PDF 파일 선택'), {
      target: {
        files: [
          new File(['%PDF-old'], 'old-session.pdf', {
            type: 'application/pdf',
          }),
        ],
      },
    })
    expect(screen.getByText('old-session.pdf')).toBeInTheDocument()

    await router.navigate(`/sessions/${nextSession.id}`)

    expect(
      await screen.findByRole('heading', { name: nextSession.title }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('class 제목')).toHaveValue(nextSession.title)
    expect(screen.queryByText('old-session.pdf')).not.toBeInTheDocument()
  })

  it('moves a waiting student from READY to LIVE through canonical status polling', async () => {
    authenticate()
    let sessionRequests = 0
    const studentReadySession = {
      ...readySession,
      course_id: studentCourse.id,
    }
    const studentLiveSession = {
      ...studentReadySession,
      status: 'LIVE' as const,
      version: 2,
      started_at: '2026-07-14T06:20:00Z',
      updated_at: '2026-07-14T06:20:00Z',
    }
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () => {
        sessionRequests += 1
        return HttpResponse.json(
          sessionRequests === 1 ? studentReadySession : studentLiveSession,
        )
      }),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(studentCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/transcript', () => {
        const version = {
          id: '70000000-0000-0000-0000-000000000001',
          session_id: readySession.id,
          source: 'LIVE',
          status: 'FINALIZING',
          version: 1,
          last_sequence: 0,
          is_canonical: true,
          recording_id: null,
          created_by_job_id: null,
          created_by_job_attempt: null,
          finalized_at: null,
          failed_at: null,
          created_at: '2026-07-14T06:20:00Z',
          updated_at: '2026-07-14T06:20:00Z',
        }
        return HttpResponse.json({
          transcript: {
            session_id: readySession.id,
            status: 'FINALIZING',
            current_version: version,
            canonical_version_id: version.id,
            canonical_version: version,
            updated_at: '2026-07-14T06:20:00Z',
          },
          selected_version: version,
          segments: [],
          gaps: [],
          next_cursor: null,
        })
      }),
      http.get('*/api/v1/sessions/:sessionId/question-clusters', () =>
        HttpResponse.json({
          scope: 'CURRENT',
          generation: null,
          clustering_state: {
            pending: false,
            requested_through_sequence: 0,
            applied_through_sequence: 0,
            current_revision: 0,
            current_generation: null,
            final_generation: null,
            active_job_id: null,
            retry_job_id: null,
            last_job: null,
          },
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    expect(
      await screen.findByRole('heading', {
        name: '교수자가 수업을 준비하고 있습니다.',
      }),
    ).toBeInTheDocument()
    expect(
      await screen.findByText('학생 수업 참여', undefined, { timeout: 7_000 }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: studentLiveSession.title,
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '수업 종료' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: '교수자 마이크 전송' }),
    ).not.toBeInTheDocument()
    expect(sessionRequests).toBeGreaterThanOrEqual(2)
    expect(
      screen.queryByRole('button', { name: '수업 시작' }),
    ).not.toBeInTheDocument()
  }, 8_000)

  it('renders the professor LIVE production view with professor-only operations', async () => {
    authenticate()
    const liveSession = liveSessionFor(professorCourse.id)
    installLiveRouteHandlers(professorCourse, liveSession)

    renderAt(`/sessions/${liveSession.id}`)

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: liveSession.title,
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('교수자 수업 운영')).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: '교수자 마이크 전송' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: '수업 원본 녹음' }),
    ).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: '수업 종료' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '실시간 강의 내용' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '익명 질문' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '질문 답변' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '수업 따라잡기 AI' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '강의자료' }),
    ).toBeInTheDocument()
  })

  it('renders the student LIVE production view without professor operations or requests', async () => {
    authenticate()
    const liveSession = liveSessionFor(studentCourse.id)
    let professorOnlyRequests = 0
    installLiveRouteHandlers(studentCourse, liveSession, () => {
      professorOnlyRequests += 1
    })

    renderAt(`/sessions/${liveSession.id}`)

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: liveSession.title,
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('학생 수업 참여')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '실시간 강의 내용' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '익명 질문' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '수업 따라잡기 AI' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('교수자 수업 운영')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: '교수자 마이크 전송' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: '수업 원본 녹음' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '수업 종료' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: '질문 답변' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: '강의자료' }),
    ).not.toBeInTheDocument()
    await waitFor(() => expect(professorOnlyRequests).toBe(0))
  })

  it('blocks professor end while a voice Answer is CAPTURING', async () => {
    authenticate()
    const liveSession = liveSessionFor(professorCourse.id)
    let endRequests = 0
    installLiveRouteHandlers(professorCourse, liveSession)
    server.use(
      http.get('*/api/v1/sessions/:sessionId/answers', () =>
        HttpResponse.json({
          items: [
            {
              id: '80000000-0000-0000-0000-000000000001',
              session_id: liveSession.id,
              answer_type: 'VOICE',
              status: 'CAPTURING',
              version: 1,
              target: {
                type: 'STUDENT_QUESTION',
                question_id: '90000000-0000-0000-0000-000000000001',
              },
              target_text_snapshot: '음수 간선은 왜 문제가 되나요?',
              text_content: null,
              source_transcript_version_id: null,
              canonical_transcript_mapping: null,
              organization_state: {
                status: 'NOT_STARTED',
                job_id: null,
                attempt: null,
                retryable: false,
                organization: null,
              },
              capture_started_after_sequence: 2,
              start_sequence: null,
              end_sequence: null,
              started_at: '2026-07-15T06:05:00Z',
              completed_at: null,
              updated_at: '2026-07-15T06:05:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post('*/api/v1/sessions/:sessionId/end', () => {
        endRequests += 1
        return HttpResponse.json({}, { status: 500 })
      }),
    )

    renderAt(`/sessions/${liveSession.id}`)

    expect(await screen.findByText('답변 캡처 중')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '수업 종료' }))

    const alertCopy = await screen.findByText(
      '진행 중인 음성 Answer를 먼저 완료하거나 취소해 주세요.',
    )
    const alert = alertCopy.closest('[role="alert"]')
    expect(alert).not.toBeNull()
    expect(alert).toHaveFocus()
    expect(
      screen.queryByRole('dialog', { name: '수업을 종료할까요?' }),
    ).not.toBeInTheDocument()
    expect(endRequests).toBe(0)
  })

  it('rechecks Answer safety and opens the end dialog after a failed check recovers', async () => {
    authenticate()
    const liveSession = liveSessionFor(professorCourse.id)
    let answerRequests = 0
    let failSafetyCheck = true
    installLiveRouteHandlers(professorCourse, liveSession)
    server.use(
      http.get('*/api/v1/sessions/:sessionId/answers', () => {
        answerRequests += 1
        if (answerRequests > 1 && failSafetyCheck) {
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: 'Answer 상태를 확인하지 못했습니다.',
                request_id: 'req_answer_safety',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
    )

    renderAt(`/sessions/${liveSession.id}`)
    await screen.findByRole('heading', { level: 1, name: liveSession.title })
    await screen.findByText('아직 완료된 Answer가 없습니다')
    fireEvent.click(screen.getByRole('button', { name: '수업 종료' }))

    expect(
      await screen.findByText(
        'Answer 상태를 확인하지 못해 안전하게 종료를 막았습니다.',
        undefined,
        { timeout: 3_000 },
      ),
    ).toBeInTheDocument()
    failSafetyCheck = false
    fireEvent.click(
      screen.getByRole('button', { name: 'Answer 상태 다시 확인' }),
    )

    expect(
      await screen.findByRole('dialog', { name: '수업을 종료할까요?' }),
    ).toBeInTheDocument()
    expect(answerRequests).toBeGreaterThanOrEqual(3)
  })

  it('blocks end from the synchronous CAPTURING cache while the follow-up Answer fetch is pending', async () => {
    authenticate()
    const liveSession = liveSessionFor(professorCourse.id)
    const questionId = '90000000-0000-0000-0000-000000000002'
    const answerId = '80000000-0000-0000-0000-000000000002'
    let answerRequests = 0
    let endRequests = 0
    let releaseAnswerRefetch: (() => void) | undefined
    const pendingAnswerRefetch = new Promise<Response>((resolve) => {
      releaseAnswerRefetch = () =>
        resolve(
          HttpResponse.json({
            items: [],
            next_cursor: null,
          }),
        )
    })
    installLiveRouteHandlers(professorCourse, liveSession)
    server.use(
      http.get('*/api/v1/sessions/:sessionId/questions', () =>
        HttpResponse.json({
          items: [
            {
              id: questionId,
              session_id: liveSession.id,
              content: '음수 간선은 왜 문제가 되나요?',
              status: 'OPEN',
              version: 1,
              clustering_sequence: 1,
              reaction_count: 2,
              reacted_by_me: false,
              cluster_id: null,
              created_at: '2026-07-15T06:04:00Z',
              updated_at: '2026-07-15T06:04:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/answers', () => {
        answerRequests += 1
        if (answerRequests === 1) {
          return HttpResponse.json({ items: [], next_cursor: null })
        }
        return pendingAnswerRefetch
      }),
      http.post('*/api/v1/sessions/:sessionId/answers', async ({ request }) => {
        expect(request.headers.get('Idempotency-Key')).toBeTruthy()
        expect(await request.json()).toEqual({
          answer_type: 'VOICE',
          target: {
            type: 'STUDENT_QUESTION',
            question_id: questionId,
          },
        })
        return HttpResponse.json({
          id: answerId,
          session_id: liveSession.id,
          answer_type: 'VOICE',
          status: 'CAPTURING',
          version: 1,
          target: {
            type: 'STUDENT_QUESTION',
            question_id: questionId,
          },
          target_text_snapshot: '음수 간선은 왜 문제가 되나요?',
          text_content: null,
          source_transcript_version_id: null,
          canonical_transcript_mapping: null,
          organization_state: {
            status: 'NOT_STARTED',
            job_id: null,
            attempt: null,
            retryable: false,
            organization: null,
          },
          capture_started_after_sequence: 2,
          start_sequence: null,
          end_sequence: null,
          started_at: '2026-07-15T06:05:00Z',
          completed_at: null,
          updated_at: '2026-07-15T06:05:00Z',
        })
      }),
      http.post('*/api/v1/sessions/:sessionId/end', () => {
        endRequests += 1
        return HttpResponse.json({}, { status: 500 })
      }),
    )

    renderAt(`/sessions/${liveSession.id}`)
    fireEvent.click(
      await screen.findByRole('button', { name: '음성 답변 시작' }),
    )
    expect(await screen.findByText('답변 캡처 중')).toBeInTheDocument()
    await waitFor(() => expect(answerRequests).toBeGreaterThanOrEqual(2))

    fireEvent.click(screen.getByRole('button', { name: '수업 종료' }))

    expect(
      await screen.findByText(
        '진행 중인 음성 Answer를 먼저 완료하거나 취소해 주세요.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('dialog', { name: '수업을 종료할까요?' }),
    ).not.toBeInTheDocument()
    expect(endRequests).toBe(0)
    releaseAnswerRefetch?.()
  })

  it('keeps end disabled while an Answer create request is still in flight', async () => {
    authenticate()
    const liveSession = liveSessionFor(professorCourse.id)
    const questionId = '90000000-0000-0000-0000-000000000003'
    let createRequests = 0
    let releaseCreate: ((response: Response) => void) | undefined
    const pendingCreate = new Promise<Response>((resolve) => {
      releaseCreate = resolve
    })
    installLiveRouteHandlers(professorCourse, liveSession)
    server.use(
      http.get('*/api/v1/sessions/:sessionId/questions', () =>
        HttpResponse.json({
          items: [
            {
              id: questionId,
              session_id: liveSession.id,
              content: 'Answer 생성 중에는 종료할 수 있나요?',
              status: 'OPEN',
              version: 1,
              clustering_sequence: 2,
              reaction_count: 1,
              reacted_by_me: false,
              cluster_id: null,
              created_at: '2026-07-15T06:06:00Z',
              updated_at: '2026-07-15T06:06:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post('*/api/v1/sessions/:sessionId/answers', async () => {
        createRequests += 1
        return pendingCreate
      }),
    )

    renderAt(`/sessions/${liveSession.id}`)
    fireEvent.click(
      await screen.findByRole('button', { name: '음성 답변 시작' }),
    )
    await waitFor(() => expect(createRequests).toBe(1))

    expect(
      screen.getByRole('button', { name: 'Answer 확인 중…' }),
    ).toBeDisabled()
    expect(
      screen.getByText('Answer 상태를 확인한 뒤 수업을 종료할 수 있습니다.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('dialog', { name: '수업을 종료할까요?' }),
    ).not.toBeInTheDocument()

    releaseCreate?.(
      HttpResponse.json({
        id: '80000000-0000-0000-0000-000000000003',
        session_id: liveSession.id,
        answer_type: 'VOICE',
        status: 'CAPTURING',
        version: 1,
        target: { type: 'STUDENT_QUESTION', question_id: questionId },
        target_text_snapshot: 'Answer 생성 중에는 종료할 수 있나요?',
        text_content: null,
        source_transcript_version_id: null,
        canonical_transcript_mapping: null,
        organization_state: {
          status: 'NOT_STARTED',
          job_id: null,
          attempt: null,
          retryable: false,
          organization: null,
        },
        capture_started_after_sequence: 2,
        start_sequence: null,
        end_sequence: null,
        started_at: '2026-07-15T06:06:00Z',
        completed_at: null,
        updated_at: '2026-07-15T06:06:00Z',
      }),
    )
  })

  it('blocks READY start while a PDF is processing', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () =>
        HttpResponse.json({
          items: [
            {
              id: '40000000-0000-0000-0000-000000000001',
              session_id: readySession.id,
              display_name: '그래프-탐색.pdf',
              mime_type: 'application/pdf',
              byte_size: 1234,
              page_count: null,
              processing_status: 'PROCESSING',
              created_at: '2026-07-14T06:10:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    expect(
      await screen.findByText('처리 중인 PDF 완료 대기'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '수업 시작' })).toBeDisabled()
  })

  it('keeps READY start blocked until a failed material query is retried', async () => {
    authenticate()
    let materialRequests = 0
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(professorCourse),
      ),
      http.get('*/api/v1/sessions/:sessionId/materials', () => {
        materialRequests += 1
        return materialRequests <= 2
          ? HttpResponse.json(
              {
                error: {
                  code: 'DEPENDENCY_UNAVAILABLE',
                  message: '잠시 후 다시 시도해 주세요.',
                  request_id: 'req_materials_retry',
                  details: null,
                },
              },
              { status: 503 },
            )
          : HttpResponse.json({ items: [], next_cursor: null })
      }),
      http.get('*/api/v1/sessions/:sessionId/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    expect(
      await screen.findByText('강의자료를 불러오지 못했습니다', undefined, {
        timeout: 3_000,
      }),
    ).toBeInTheDocument()
    const start = screen.getByRole('button', { name: '수업 시작' })
    expect(start).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '자료 목록 다시 시도' }))
    await waitFor(() => expect(start).toBeEnabled())
    expect(materialRequests).toBe(3)
  })

  it('does not render READY professor controls when Course access is forbidden', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json(readySession),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(
          {
            error: {
              code: 'COURSE_FORBIDDEN',
              message: '이 Course에 접근할 수 없습니다.',
              request_id: 'req_ready_forbidden',
              details: null,
            },
          },
          { status: 403 },
        ),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    expect(
      await screen.findByRole('heading', {
        name: '이 Course에 접근할 권한이 없습니다',
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '수업 시작' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByLabelText('PDF 파일 선택')).not.toBeInTheDocument()
  })

  it('does not render professor session controls for a student', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/sessions/:sessionId', () =>
        HttpResponse.json({ ...readySession, course_id: studentCourse.id }),
      ),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(studentCourse),
      ),
    )
    renderAt(`/sessions/${readySession.id}`)

    expect(
      await screen.findByRole('heading', { name: readySession.title }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.getByRole('heading', {
          name: '교수자가 수업을 준비하고 있습니다.',
        }),
      ).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: '수업 시작' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '제목 저장' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'class 삭제' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByLabelText('PDF 파일 선택')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '처리 다시 시도' }),
    ).not.toBeInTheDocument()
  })
})

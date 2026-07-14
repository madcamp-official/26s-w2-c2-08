import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { appRoutes } from '../../app/router'
import { server } from '../../test/server'

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

function renderAt(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return router
}

function authenticate() {
  server.use(http.get('*/api/v1/me', () => HttpResponse.json(user)))
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

    expect(
      await screen.findByRole('heading', { name: '오늘의 class 준비' }),
    ).toBeInTheDocument()
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
        screen.getByText(
          '학생은 class 상태와 수업 기록을 읽기 전용으로 확인합니다.',
        ),
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
  })
})

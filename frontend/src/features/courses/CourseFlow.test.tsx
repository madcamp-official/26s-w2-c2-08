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
          items: role === 'PROFESSOR' ? [professorCourse] : [studentCourse],
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
    expect(screen.getByText('알고리즘')).toBeInTheDocument()
    expect(screen.getByText('운영체제')).toBeInTheDocument()
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
      await screen.findByRole('heading', { name: '학생 Course' }),
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
      await screen.findByText('이 Course의 유일한 교수자 owner입니다.', {
        exact: false,
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

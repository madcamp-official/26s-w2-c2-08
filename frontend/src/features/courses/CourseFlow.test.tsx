import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
})

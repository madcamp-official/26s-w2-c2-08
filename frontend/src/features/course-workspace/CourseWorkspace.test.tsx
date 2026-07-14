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

const course = {
  id: '10000000-0000-0000-0000-000000000001',
  title: '알고리즘',
  semester: '2026 여름학기',
  role: 'STUDENT' as const,
  current_session: null,
  created_at: '2026-07-14T00:00:00Z',
}

const completedSession = {
  id: '30000000-0000-0000-0000-000000000001',
  course_id: course.id,
  title: '그래프 탐색',
  lecture_date: '2026-07-13',
  status: 'COMPLETED' as const,
  version: 1,
  canonical_transcript_version_id: null,
  started_at: '2026-07-13T06:00:00Z',
  ended_at: '2026-07-13T07:00:00Z',
  completed_at: '2026-07-13T07:05:00Z',
  created_at: '2026-07-13T05:55:00Z',
  updated_at: '2026-07-13T07:05:00Z',
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
  server.use(
    http.get('*/api/v1/me', () => HttpResponse.json(user)),
    http.get('*/api/v1/courses/:courseId', () => HttpResponse.json(course)),
  )
}

describe('Course workspace shell', () => {
  it('shows exactly four archive links and routes each link to its screen', async () => {
    authenticate()
    const router = renderAt(`/courses/${course.id}/materials`)

    expect(
      await screen.findByRole('heading', { name: '모든 class의 PDF 자료' }),
    ).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', {
      name: 'Course 기록 탐색',
    })
    const links = within(navigation).getAllByRole('link')
    expect(links).toHaveLength(4)
    expect(links.map((link) => link.textContent)).toEqual([
      'PDF 자료',
      'Transcript',
      'AI 요약',
      '질의응답',
    ])
    expect(
      within(navigation).getByRole('link', { name: 'PDF 자료' }),
    ).toHaveAttribute('aria-current', 'page')

    fireEvent.click(within(navigation).getByRole('link', { name: 'AI 요약' }))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        `/courses/${course.id}/summaries`,
      ),
    )
    expect(
      await screen.findByRole('heading', { name: '모든 class의 AI 요약' }),
    ).toBeInTheDocument()
  })

  it('keeps the LIVE CLASS slot visible when there is no active class', async () => {
    authenticate()
    renderAt(`/courses/${course.id}/transcripts`)

    expect(await screen.findByText('LIVE CLASS')).toBeInTheDocument()
    expect(screen.getByText('현재 class 없음')).toBeInTheDocument()
    expect(
      screen.getByText('진행 중인 class가 생기면 이곳에 표시됩니다.'),
    ).toBeInTheDocument()
  })

  it('labels READY without presenting it as a live class', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json({
          ...course,
          current_session: {
            id: '20000000-0000-0000-0000-000000000001',
            title: '다음 class',
            lecture_date: '2026-07-15',
            status: 'READY',
            started_at: null,
          },
        }),
      ),
    )
    renderAt(`/courses/${course.id}/qna`)

    expect(await screen.findByText('LIVE CLASS')).toBeInTheDocument()
    expect(screen.getByText('시작 전')).toBeInTheDocument()
    expect(screen.queryByText('진행 중')).not.toBeInTheDocument()
  })

  it('loads completed classes by cursor and preserves the first page', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/sessions', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        if (cursor === 'next-page') {
          return HttpResponse.json({
            items: [
              {
                ...completedSession,
                id: '30000000-0000-0000-0000-000000000002',
                title: '동적 계획법',
              },
            ],
            next_cursor: null,
          })
        }
        return HttpResponse.json({
          items: [completedSession],
          next_cursor: 'next-page',
        })
      }),
    )
    renderAt(`/courses/${course.id}/materials`)

    expect(await screen.findByText('그래프 탐색')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '지난 class 더 보기' }))
    expect(await screen.findByText('동적 계획법')).toBeInTheDocument()
    expect(screen.getByText('그래프 탐색')).toBeInTheDocument()
  })

  it('hides the workspace when Course membership is denied', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(user)),
      http.get('*/api/v1/courses/:courseId', () =>
        HttpResponse.json(
          {
            error: {
              code: 'COURSE_ACCESS_DENIED',
              message: '접근할 수 없습니다.',
              request_id: 'req_workspace_forbidden',
              details: null,
            },
          },
          { status: 403 },
        ),
      ),
    )
    renderAt(`/courses/${course.id}/materials`)

    expect(
      await screen.findByRole('heading', {
        name: '이 Course에 접근할 권한이 없습니다',
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('navigation', { name: 'Course 기록 탐색' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('LIVE CLASS')).not.toBeInTheDocument()
  })
})

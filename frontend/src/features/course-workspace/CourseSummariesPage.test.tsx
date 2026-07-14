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

const courseId = '10000000-0000-0000-0000-000000000001'

function session(
  id: string,
  title: string,
  status: 'PROCESSING' | 'COMPLETED' = 'COMPLETED',
) {
  return {
    id,
    title,
    lecture_date: '2026-07-13',
    status,
    started_at: '2026-07-13T06:00:00Z',
  }
}

function finalSummary(id: string, sessionId: string, content: string) {
  return {
    id,
    session_id: sessionId,
    job_id: `job-${id}`,
    summary_type: 'FINAL' as const,
    visibility: 'COURSE_MEMBERS' as const,
    content,
    source_transcript_version_id: `version-${id}`,
    source_start_sequence: 1,
    source_end_sequence: 12,
    model_name: null,
    prompt_version: 'final-v1',
    created_at: '2026-07-13T07:05:00Z',
  }
}

function errorResponse(status = 422) {
  return HttpResponse.json(
    {
      error: {
        code: 'ARCHIVE_UNAVAILABLE',
        message: 'archive를 불러오지 못했습니다.',
        request_id: 'req_summary_archive',
        details: null,
      },
    },
    { status },
  )
}

function authenticate() {
  server.use(
    http.get('*/api/v1/me', () =>
      HttpResponse.json({
        id: '00000000-0000-0000-0000-000000000001',
        display_name: '김도현',
        email: 'dohyun@example.test',
        avatar_url: null,
      }),
    ),
    http.get('*/api/v1/courses/:courseId', () =>
      HttpResponse.json({
        id: courseId,
        title: '알고리즘',
        semester: '2026 여름학기',
        role: 'STUDENT',
        current_session: null,
        created_at: '2026-07-01T00:00:00Z',
      }),
    ),
  )
}

function renderPage() {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [`/courses/${courseId}/summaries`],
  })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
}

describe('Course Summary archive', () => {
  it('shows public FINAL content and distinguishes every terminal or pending state', async () => {
    authenticate()
    const availableSession = session('session-available', '그래프 탐색')
    const publicSummary = finalSummary(
      'summary-public',
      availableSession.id,
      '그래프 탐색과 최단 경로를 정리했습니다.',
    )
    server.use(
      http.get('*/api/v1/courses/:courseId/summaries', () =>
        HttpResponse.json({
          items: [
            {
              session: availableSession,
              state: { status: 'AVAILABLE', reason: null },
              summary: publicSummary,
              summary_url: `/api/v1/summaries/${publicSummary.id}`,
            },
            {
              session: session('session-pending', '동적 계획법', 'PROCESSING'),
              state: { status: 'PENDING', reason: null },
              summary: null,
              summary_url: null,
            },
            {
              session: session('session-empty', '정렬'),
              state: {
                status: 'NOT_APPLICABLE',
                reason: {
                  code: 'NO_FINAL_TRANSCRIPT',
                  message: '요약할 강의 내용이 없습니다.',
                },
              },
              summary: null,
              summary_url: null,
            },
            {
              session: session('session-failed', '해시'),
              state: {
                status: 'FAILED',
                reason: {
                  code: 'SUMMARY_SOURCE_UNAVAILABLE',
                  message: 'Transcript 처리 문제로 요약을 만들지 못했습니다.',
                },
              },
              summary: null,
              summary_url: null,
            },
            {
              session: session('session-integrity', '트리'),
              state: { status: 'DATA_INTEGRITY_ERROR', reason: null },
              summary: null,
              summary_url: null,
            },
          ],
          next_cursor: null,
        }),
      ),
    )
    renderPage()

    expect(
      await screen.findByText('그래프 탐색과 최단 경로를 정리했습니다.'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '요약 상세 열기' }),
    ).toHaveAttribute(
      'href',
      expect.stringContaining(`/api/v1/summaries/${publicSummary.id}`),
    )
    expect(screen.getByText('요약 준비 중')).toBeInTheDocument()
    expect(screen.getByText('요약할 내용 없음')).toBeInTheDocument()
    expect(screen.getByText('요약 생성 실패')).toBeInTheDocument()
    expect(screen.getByText('요약 상태 확인 필요')).toBeInTheDocument()
    expect(
      screen.getByText(
        '요약 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
      ),
    ).toBeInTheDocument()
  })

  it('never renders requester-only LIVE summary content from a malformed archive item', async () => {
    authenticate()
    const privateSession = session('session-private', '비공개 결과')
    server.use(
      http.get('*/api/v1/courses/:courseId/summaries', () =>
        HttpResponse.json({
          items: [
            {
              session: privateSession,
              state: { status: 'AVAILABLE', reason: null },
              summary: {
                ...finalSummary(
                  'summary-private',
                  privateSession.id,
                  '요청자 전용 LIVE 요약 원문',
                ),
                summary_type: 'LIVE',
                visibility: 'REQUESTER_ONLY',
              },
              summary_url: '/api/v1/summaries/summary-private',
            },
          ],
          next_cursor: null,
        }),
      ),
    )
    renderPage()

    expect(await screen.findByText('요약 상태 확인 필요')).toBeInTheDocument()
    expect(
      screen.queryByText('요청자 전용 LIVE 요약 원문'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: '요약 상세 열기' }),
    ).not.toBeInTheDocument()
  })

  it('appends the next cursor page without replacing an existing summary', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/summaries', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        const itemSession = cursor
          ? session('session-second', '동적 계획법')
          : session('session-first', '그래프 탐색')
        const itemSummary = finalSummary(
          cursor ? 'summary-second' : 'summary-first',
          itemSession.id,
          cursor ? '두 번째 요약' : '첫 번째 요약',
        )
        return HttpResponse.json({
          items: [
            {
              session: itemSession,
              state: { status: 'AVAILABLE', reason: null },
              summary: itemSummary,
              summary_url: `/api/v1/summaries/${itemSummary.id}`,
            },
          ],
          next_cursor: cursor ? null : 'next-summaries',
        })
      }),
    )
    renderPage()

    expect(await screen.findByText('첫 번째 요약')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'AI 요약 더 보기' }))
    expect(await screen.findByText('두 번째 요약')).toBeInTheDocument()
    expect(screen.getByText('첫 번째 요약')).toBeInTheDocument()
  })

  it('keeps loaded summaries and the class rail when a next page fails', async () => {
    authenticate()
    const itemSession = session('session-first', '그래프 탐색')
    const itemSummary = finalSummary(
      'summary-first',
      itemSession.id,
      '표시를 유지할 요약',
    )
    server.use(
      http.get('*/api/v1/courses/:courseId/summaries', ({ request }) => {
        if (new URL(request.url).searchParams.has('cursor')) {
          return errorResponse()
        }
        return HttpResponse.json({
          items: [
            {
              session: itemSession,
              state: { status: 'AVAILABLE', reason: null },
              summary: itemSummary,
              summary_url: `/api/v1/summaries/${itemSummary.id}`,
            },
          ],
          next_cursor: 'next-summaries',
        })
      }),
    )
    renderPage()

    expect(await screen.findByText('표시를 유지할 요약')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'AI 요약 더 보기' }))
    expect(
      await screen.findByText(
        '다음 class를 불러오지 못했습니다. 표시된 요약은 유지됩니다.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('표시를 유지할 요약')).toBeInTheDocument()
    expect(screen.getByText('LIVE CLASS')).toBeInTheDocument()
  })

  it('recovers an initial archive error without removing workspace navigation', async () => {
    authenticate()
    let requests = 0
    server.use(
      http.get('*/api/v1/courses/:courseId/summaries', () => {
        requests += 1
        return requests === 1
          ? errorResponse()
          : HttpResponse.json({ items: [], next_cursor: null })
      }),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', {
        name: 'AI 요약 archive를 불러오지 못했습니다',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('navigation', { name: 'Course 기록 탐색' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))
    expect(
      await screen.findByRole('heading', {
        name: '표시할 AI 요약이 없습니다',
      }),
    ).toBeInTheDocument()
    await waitFor(() => expect(requests).toBe(2))
  })

  it('keeps the workspace around an empty Summary archive', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/summaries', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', {
        name: '표시할 AI 요약이 없습니다',
      }),
    ).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', {
      name: 'Course 기록 탐색',
    })
    expect(
      within(navigation).getByRole('link', { name: 'AI 요약' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('LIVE CLASS')).toBeInTheDocument()
  })
})

import { fireEvent, render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { appRoutes } from '../../app/router'
import { server } from '../../test/server'

const courseId = '10000000-0000-0000-0000-000000000001'
const session = {
  id: '20000000-0000-0000-0000-000000000001',
  title: '그래프 탐색',
  lecture_date: '2026-07-13',
  status: 'COMPLETED' as const,
  started_at: '2026-07-13T06:00:00Z',
}

function material(
  id: string,
  displayName: string,
  status: 'UPLOADED' | 'PROCESSING' | 'READY' | 'FAILED',
) {
  return {
    id,
    session_id: session.id,
    display_name: displayName,
    mime_type: 'application/pdf' as const,
    byte_size: 2048,
    page_count: status === 'READY' ? 12 : null,
    processing_status: status,
    created_at: '2026-07-13T05:50:00Z',
  }
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
    initialEntries: [`/courses/${courseId}/materials`],
  })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
}

describe('Course material archive', () => {
  it('offers inline viewing and attachment download without exposing failed content', async () => {
    authenticate()
    const ready = material(
      '30000000-0000-0000-0000-000000000001',
      'week-01.pdf',
      'READY',
    )
    const failed = material(
      '30000000-0000-0000-0000-000000000002',
      'broken.pdf',
      'FAILED',
    )
    server.use(
      http.get('*/api/v1/courses/:courseId/materials', () =>
        HttpResponse.json({
          items: [
            {
              session,
              material: ready,
              content_url: `/api/v1/materials/${ready.id}/content`,
              download_url: `/api/v1/materials/${ready.id}/content?disposition=attachment`,
            },
            {
              session,
              material: failed,
              content_url: null,
              download_url: null,
            },
          ],
          next_cursor: null,
        }),
      ),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', { name: '모든 class의 PDF 자료' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '새 탭에서 열기' }),
    ).toHaveAttribute('href', `/api/v1/materials/${ready.id}/content`)
    expect(screen.getByRole('link', { name: '다운로드' })).toHaveAttribute(
      'href',
      `/api/v1/materials/${ready.id}/content?disposition=attachment`,
    )
    const failedItem = screen.getByText('broken.pdf').closest('li')
    expect(failedItem).not.toBeNull()
    expect(within(failedItem!).queryByRole('link')).not.toBeInTheDocument()
    expect(
      within(failedItem!).getByText('원문을 사용할 수 없습니다'),
    ).toBeInTheDocument()
  })

  it('appends the next cursor page without replacing existing materials', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/materials', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        const item = cursor
          ? material(
              '30000000-0000-0000-0000-000000000004',
              'week-02.pdf',
              'PROCESSING',
            )
          : material(
              '30000000-0000-0000-0000-000000000003',
              'week-01.pdf',
              'UPLOADED',
            )
        return HttpResponse.json({
          items: [
            {
              session,
              material: item,
              content_url: `/api/v1/materials/${item.id}/content`,
              download_url: `/api/v1/materials/${item.id}/content?disposition=attachment`,
            },
          ],
          next_cursor: cursor ? null : 'next-materials',
        })
      }),
    )
    renderPage()

    expect(await screen.findByText('week-01.pdf')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'PDF 자료 더 보기' }))
    expect(await screen.findByText('week-02.pdf')).toBeInTheDocument()
    expect(screen.getByText('week-01.pdf')).toBeInTheDocument()
  })

  it('shows an archive-local empty state while keeping workspace navigation', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/materials', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', {
        name: '연결된 PDF 자료가 없습니다',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('navigation', { name: 'Course 기록 탐색' }),
    ).toBeInTheDocument()
    expect(screen.getByText('LIVE CLASS')).toBeInTheDocument()
  })
})

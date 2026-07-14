import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { server } from '../test/server'
import { AppProviders } from './providers'
import { appRoutes } from './router'

function renderAt(path: string) {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [path],
  })

  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )

  return router
}

describe('application router', () => {
  it('shows the common not-found state for an unknown route', () => {
    renderAt('/missing-page')

    expect(
      screen.getByRole('heading', {
        name: '요청한 페이지를 찾을 수 없습니다',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('offers login and email signup from the shared shell when signed out', async () => {
    renderAt('/')

    expect(await screen.findByRole('link', { name: '로그인' })).toHaveAttribute(
      'href',
      '/login',
    )
    expect(screen.getByRole('link', { name: '이메일로 시작' })).toHaveAttribute(
      'href',
      '/signup',
    )
    expect(
      screen.getByRole('link', { name: '로그인하고 시작하기' }),
    ).toHaveAttribute('href', '/login?return_to=/')
    expect(
      screen.getByRole('link', { name: '이메일로 가입하기' }),
    ).toHaveAttribute('href', '/signup?return_to=/')
    expect(
      screen.getByRole('heading', { name: '실시간 Transcript' }),
    ).toBeInTheDocument()
  })

  it('offers Course and account navigation from the shared shell when signed in', async () => {
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json({
          id: '00000000-0000-0000-0000-000000000001',
          display_name: '김도현',
          email: 'dohyun@example.test',
          avatar_url: null,
        }),
      ),
      http.get('*/api/v1/courses', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    const router = renderAt('/')

    expect(
      await screen.findByRole('link', { name: '내 Course' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: /내 정보/ })).toHaveAttribute(
      'href',
      '/account',
    )

    await router.navigate('/account')
    await waitFor(() =>
      expect(screen.getByRole('link', { name: '내 정보' })).toHaveAttribute(
        'aria-current',
        'page',
      ),
    )
  })

  it('keeps an account lookup failure distinct from a signed-out state', async () => {
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '잠시 후 다시 시도해 주세요.',
              request_id: 'req_test',
              details: null,
            },
          },
          { status: 503 },
        ),
      ),
    )
    renderAt('/')

    expect(
      await screen.findByRole(
        'button',
        { name: '계정 상태 다시 확인' },
        { timeout: 3_000 },
      ),
    ).toBeEnabled()
    expect(
      screen.queryByRole('link', { name: '로그인' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '실시간 Transcript' }),
    ).toBeInTheDocument()
  })
})

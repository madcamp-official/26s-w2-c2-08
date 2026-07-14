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

function renderAt(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return router
}

describe('authentication flow', () => {
  it('restores a protected path through the login URL', async () => {
    renderAt('/account?tab=security')

    expect(
      await screen.findByRole('heading', {
        name: '강의의 흐름으로 다시 들어오세요.',
      }),
    ).toBeInTheDocument()
    const login = await screen.findByRole('link', {
      name: 'Google 계정으로 계속하기',
    })
    const url = new URL(login.getAttribute('href') ?? window.location.href)
    expect(url.searchParams.get('return_to')).toBe('/account?tab=security')
  })

  it('returns an already authenticated user to the requested screen', async () => {
    server.use(http.get('*/api/v1/me', () => HttpResponse.json(user)))
    renderAt('/login?return_to=/account')

    expect(
      await screen.findByRole('heading', { name: '내 정보' }),
    ).toBeInTheDocument()
    expect(screen.getByText('dohyun@example.test')).toBeInTheDocument()
  })

  it('logs in with email and restores the requested route', async () => {
    server.use(
      http.post('*/api/v1/auth/email/login', async ({ request }) => {
        expect(await request.json()).toEqual({
          email: 'dohyun@example.test',
          password: 'correct horse battery staple',
        })
        return HttpResponse.json({ user })
      }),
    )
    renderAt('/login?return_to=/account')

    const emailInput = await screen.findByLabelText('이메일')
    fireEvent.change(emailInput, { target: { value: 'dohyun@example.test' } })
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'correct horse battery staple' },
    })
    fireEvent.click(screen.getByRole('button', { name: '이메일로 로그인' }))

    expect(
      await screen.findByRole('heading', { name: '내 정보' }),
    ).toBeInTheDocument()
  })

  it('offers an email account creation screen', async () => {
    renderAt('/login?return_to=/courses/join')

    fireEvent.click(
      await screen.findByRole('link', { name: '이메일 계정 만들기' }),
    )

    expect(
      await screen.findByRole('heading', {
        name: '나만의 강의 흐름을 시작하세요.',
      }),
    ).toBeInTheDocument()
    expect(await screen.findByLabelText('표시 이름')).toBeInTheDocument()
  })

  it('navigates only after logout succeeds', async () => {
    let authenticated = true
    server.use(
      http.get('*/api/v1/me', () =>
        authenticated
          ? HttpResponse.json(user)
          : HttpResponse.json(
              {
                error: {
                  code: 'AUTHENTICATION_REQUIRED',
                  message: '로그인이 필요합니다.',
                  request_id: 'req_test',
                  details: null,
                },
              },
              { status: 401 },
            ),
      ),
      http.post('*/api/v1/auth/logout', () => {
        authenticated = false
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderAt('/account')

    expect(
      await screen.findByRole('heading', { name: '내 정보' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '로그아웃' }))

    expect(
      await screen.findByRole('heading', {
        name: '강의의 흐름으로 다시 들어오세요.',
      }),
    ).toBeInTheDocument()
    expect(
      await screen.findByText('안전하게 로그아웃했습니다.'),
    ).toBeInTheDocument()
  })

  it('keeps the account screen when logout fails', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(user)),
      http.post('*/api/v1/auth/logout', () =>
        HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '일시적인 오류입니다.',
              request_id: 'req_test',
              details: null,
            },
          },
          { status: 503 },
        ),
      ),
    )
    renderAt('/account')

    expect(
      await screen.findByRole('heading', { name: '내 정보' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '로그아웃',
      }),
    )

    expect(
      await screen.findByText(
        '로그아웃하지 못했습니다. 현재 Session은 그대로 유지됩니다.',
      ),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: '내 정보' }),
      ).toBeInTheDocument(),
    )
  })
})

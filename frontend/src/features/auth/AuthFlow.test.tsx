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

const accountProfessorCourse = {
  id: '10000000-0000-0000-0000-000000000001',
  title: '알고리즘',
  semester: '2026 여름학기',
  role: 'PROFESSOR' as const,
  join_code: 'ABCXYZ',
  current_session: null,
  created_at: '2026-07-14T00:00:00Z',
}

const accountStudentCourse = {
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

  it('hides account and Course data when the current-user request fails', async () => {
    let courseRequests = 0
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '잠시 후 다시 시도해 주세요.',
              request_id: 'req_account_me',
              details: null,
            },
          },
          { status: 503 },
        ),
      ),
      http.get('*/api/v1/courses', () => {
        courseRequests += 1
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
    )
    renderAt('/account')

    expect(
      await screen.findByRole(
        'heading',
        { name: '내 정보를 불러오지 못했습니다' },
        { timeout: 3_000 },
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('dohyun@example.test')).not.toBeInTheDocument()
    expect(courseRequests).toBe(0)
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

  it('connects an invalid credential error to both login fields', async () => {
    server.use(
      http.post('*/api/v1/auth/email/login', () =>
        HttpResponse.json(
          {
            error: {
              code: 'INVALID_CREDENTIALS',
              message: '인증 정보를 확인해 주세요.',
              request_id: 'req_login',
              details: null,
            },
          },
          { status: 401 },
        ),
      ),
    )
    renderAt('/login')

    const emailInput = await screen.findByLabelText('이메일')
    const passwordInput = screen.getByLabelText('비밀번호')
    fireEvent.change(emailInput, { target: { value: 'wrong@example.test' } })
    fireEvent.change(passwordInput, { target: { value: 'wrong-password' } })
    fireEvent.click(screen.getByRole('button', { name: '이메일로 로그인' }))

    const error = await screen.findByText(
      '이메일 또는 비밀번호가 올바르지 않습니다.',
    )
    expect(emailInput).toHaveAttribute('aria-invalid', 'true')
    expect(passwordInput).toHaveAttribute('aria-invalid', 'true')
    expect(emailInput).toHaveAttribute('aria-describedby', error.id)
    expect(passwordInput).toHaveAttribute('aria-describedby', error.id)
  })

  it('shows a safe notice when Google login was cancelled', async () => {
    renderAt('/login?auth_error=cancelled')

    expect(
      await screen.findByText(
        'Google 로그인이 취소되었습니다. 준비되면 다시 시도해 주세요.',
      ),
    ).toHaveAttribute('role', 'alert')
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

  it('creates an email account and restores the requested route', async () => {
    server.use(
      http.post('*/api/v1/auth/email/register', async ({ request }) => {
        expect(await request.json()).toEqual({
          display_name: '김도현',
          email: 'dohyun@example.test',
          password: 'correct horse battery staple',
        })
        return HttpResponse.json({ user })
      }),
    )
    renderAt('/signup?return_to=/account')

    fireEvent.change(await screen.findByLabelText('표시 이름'), {
      target: { value: '김도현' },
    })
    fireEvent.change(screen.getByLabelText('이메일'), {
      target: { value: 'dohyun@example.test' },
    })
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'correct horse battery staple' },
    })
    fireEvent.click(screen.getByRole('button', { name: '이메일 계정 만들기' }))

    expect(
      await screen.findByRole('heading', { name: '내 정보' }),
    ).toBeInTheDocument()
  })

  it('connects an existing email error to the signup email field', async () => {
    server.use(
      http.post('*/api/v1/auth/email/register', () =>
        HttpResponse.json(
          {
            error: {
              code: 'EMAIL_ALREADY_REGISTERED',
              message: '이미 사용 중인 이메일입니다.',
              request_id: 'req_signup',
              details: null,
            },
          },
          { status: 409 },
        ),
      ),
    )
    renderAt('/signup')

    fireEvent.change(await screen.findByLabelText('표시 이름'), {
      target: { value: '김도현' },
    })
    const emailInput = screen.getByLabelText('이메일')
    fireEvent.change(emailInput, {
      target: { value: 'registered@example.test' },
    })
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'correct horse battery staple' },
    })
    fireEvent.click(screen.getByRole('button', { name: '이메일 계정 만들기' }))

    const error = await screen.findByText(
      '이미 등록된 이메일입니다. 기존 로그인 방식을 사용해 주세요.',
    )
    expect(emailInput).toHaveAttribute('aria-invalid', 'true')
    expect(emailInput).toHaveAttribute('aria-describedby', error.id)
  })

  it('shows independent Course role summaries without inventing a total count', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(user)),
      http.get('*/api/v1/courses', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role')
        return HttpResponse.json({
          items:
            role === 'PROFESSOR'
              ? [accountProfessorCourse]
              : [accountStudentCourse],
          next_cursor: role === 'PROFESSOR' ? 'next-owned-page' : null,
        })
      }),
    )
    renderAt('/account')

    expect(
      await screen.findByLabelText('관리 중인 Course 1개 이상'),
    ).toHaveTextContent('1')
    expect(screen.getByLabelText('참여 중인 Course 1개')).toHaveTextContent('1')
    expect(
      screen.getByRole('link', { name: '전체 Course 보기' }),
    ).toHaveAttribute('href', '/')
  })

  it('keeps the successful Course role summary visible when the other role fails', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(user)),
      http.get('*/api/v1/courses', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role')
        if (role === 'PROFESSOR') {
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: '잠시 후 다시 시도해 주세요.',
                request_id: 'req_account_courses',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return HttpResponse.json({
          items: [accountStudentCourse],
          next_cursor: null,
        })
      }),
    )
    renderAt('/account')

    expect(
      await screen.findByText('개수를 확인하지 못했습니다', undefined, {
        timeout: 3_000,
      }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('참여 중인 Course 1개')).toHaveTextContent('1')
    expect(screen.queryByText('운영체제')).not.toBeInTheDocument()
  })

  it('blocks withdrawal before the request when an owned Course is known', async () => {
    let withdrawalRequests = 0
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(user)),
      http.get('*/api/v1/courses', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role')
        return HttpResponse.json({
          items: role === 'PROFESSOR' ? [accountProfessorCourse] : [],
          next_cursor: null,
        })
      }),
      http.delete('*/api/v1/me', () => {
        withdrawalRequests += 1
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderAt('/account')

    await screen.findByLabelText('관리 중인 Course 1개')
    fireEvent.click(screen.getByRole('button', { name: '계정 탈퇴 검토' }))
    const dialog = screen.getByRole('dialog')
    const submit = within(dialog).getByRole('button', { name: '계정 탈퇴' })

    expect(submit).toBeDisabled()
    expect(
      within(dialog).getByText('관리 중인 Course가 남아 있습니다'),
    ).toBeInTheDocument()
    fireEvent.click(submit)
    expect(withdrawalRequests).toBe(0)
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
    const router = renderAt('/account')

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
    await waitFor(() =>
      expect(router.state.location).toMatchObject({
        pathname: '/login',
        search: '?logged_out=1',
      }),
    )
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

  it('ends the current session only after account withdrawal succeeds', async () => {
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
      http.delete('*/api/v1/me', () => {
        authenticated = false
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const router = renderAt('/account')

    fireEvent.click(
      await screen.findByRole('button', { name: '계정 탈퇴 검토' }),
    )
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '계정 탈퇴',
      }),
    )

    expect(
      await screen.findByText(
        '계정을 탈퇴했습니다. 다시 이용하려면 새 계정으로 로그인하세요.',
      ),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(router.state.location).toMatchObject({
        pathname: '/login',
        search: '?withdrawn=1',
      }),
    )
  })

  it('keeps the account screen when an owner Course blocks withdrawal', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(user)),
      http.delete('*/api/v1/me', () =>
        HttpResponse.json(
          {
            error: {
              code: 'OWNED_COURSE_REQUIRES_DELETION',
              message: '생성한 Course를 먼저 삭제해야 합니다.',
              request_id: 'req_test',
              details: null,
            },
          },
          { status: 409 },
        ),
      ),
    )
    renderAt('/account')

    fireEvent.click(
      await screen.findByRole('button', { name: '계정 탈퇴 검토' }),
    )
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: '계정 탈퇴',
      }),
    )

    expect(
      await within(screen.getByRole('dialog')).findByText(
        '생성한 Course를 먼저 삭제한 뒤 계정을 탈퇴할 수 있습니다.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '내 정보' })).toBeInTheDocument()
  })
})

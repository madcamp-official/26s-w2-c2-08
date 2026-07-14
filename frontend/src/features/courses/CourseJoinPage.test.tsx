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

const joinedCourse = {
  id: '20000000-0000-0000-0000-000000000001',
  title: '운영체제',
  semester: '2026 여름학기',
  role: 'STUDENT' as const,
  current_session: null,
  created_at: '2026-07-13T00:00:00Z',
}

function authenticate() {
  server.use(http.get('*/api/v1/me', () => HttpResponse.json(user)))
}

function renderJoinPage() {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ['/courses/join'],
  })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return router
}

function apiError(status: number, code: string) {
  return HttpResponse.json(
    {
      error: {
        code,
        message: '요청을 처리하지 못했습니다.',
        request_id: `req_join_${status}`,
        details: null,
      },
    },
    { status },
  )
}

describe('COURSE_JOIN_PAGE', () => {
  it('rejects malformed full values without truncating or sending a request', async () => {
    authenticate()
    let requests = 0
    server.use(
      http.post('*/api/v1/courses/join', () => {
        requests += 1
        return HttpResponse.json(joinedCourse, { status: 201 })
      }),
    )
    renderJoinPage()

    const input = await screen.findByLabelText('참여 코드')
    fireEvent.change(input, { target: { value: 'abcde' } })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))
    expect(input).toHaveFocus()
    expect(input).toHaveAccessibleDescription(
      '영문 대문자 6자로 된 참여 코드를 입력해 주세요.',
    )

    fireEvent.change(input, { target: { value: 'abcdefg' } })
    expect(input).toHaveValue('ABCDEFG')
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))
    expect(requests).toBe(0)
  })

  it('normalizes the entire pasted value, locks pending input, and focuses a new membership result', async () => {
    authenticate()
    let releaseRequest: (() => void) | undefined
    let requestBody: unknown
    let idempotencyKey: string | null = null
    server.use(
      http.post('*/api/v1/courses/join', async ({ request }) => {
        requestBody = await request.json()
        idempotencyKey = request.headers.get('Idempotency-Key')
        await new Promise<void>((resolve) => {
          releaseRequest = resolve
        })
        return HttpResponse.json(joinedCourse, { status: 201 })
      }),
    )
    renderJoinPage()

    const input = await screen.findByLabelText('참여 코드')
    fireEvent.paste(input, {
      clipboardData: { getData: () => '  abcxyz  ' },
    })
    expect(input).toHaveValue('ABCXYZ')
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))

    expect(
      await screen.findByRole('button', { name: '참여 확인 중…' }),
    ).toBeDisabled()
    expect(input).toBeDisabled()
    expect(screen.getByRole('link', { name: '취소' })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    expect(requestBody).toEqual({ join_code: 'ABCXYZ' })
    expect(idempotencyKey).toMatch(/\S+/)

    releaseRequest?.()
    const title = await screen.findByRole('heading', {
      name: '운영체제 Course에 참여했습니다',
    })
    await waitFor(() => expect(title).toHaveFocus())
    expect(screen.getByText('학생')).toBeInTheDocument()
    expect(screen.queryByText('ABCXYZ')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Course로 이동' })).toHaveAttribute(
      'href',
      `/courses/${joinedCourse.id}`,
    )
  })

  it('distinguishes an existing student membership from a new join', async () => {
    authenticate()
    server.use(
      http.post('*/api/v1/courses/join', () => HttpResponse.json(joinedCourse)),
    )
    renderJoinPage()

    fireEvent.change(await screen.findByLabelText('참여 코드'), {
      target: { value: 'ABCXYZ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))

    expect(
      await screen.findByRole('heading', {
        name: '이미 참여 중인 Course입니다',
      }),
    ).toHaveFocus()
    expect(screen.getByText('이미 참여 중')).toBeInTheDocument()
    expect(screen.queryByText('ABCXYZ')).not.toBeInTheDocument()
  })

  it('keeps invalid and rotated codes in the same field-level error state', async () => {
    authenticate()
    server.use(
      http.post('*/api/v1/courses/join', () =>
        apiError(404, 'RESOURCE_NOT_FOUND'),
      ),
    )
    renderJoinPage()

    const input = await screen.findByLabelText('참여 코드')
    fireEvent.change(input, { target: { value: 'OLDKEY' } })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))

    await waitFor(() => expect(input).toHaveFocus())
    expect(input).toHaveAccessibleDescription('참여 코드를 확인해 주세요.')
    expect(screen.queryByText('운영체제')).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'NEWKEY' } })
    expect(input).not.toHaveAccessibleDescription('참여 코드를 확인해 주세요.')
  })

  it('preserves a professor membership and routes back to managed Courses', async () => {
    authenticate()
    server.use(
      http.post('*/api/v1/courses/join', () =>
        apiError(409, 'MEMBERSHIP_CONFLICT'),
      ),
    )
    renderJoinPage()

    fireEvent.change(await screen.findByLabelText('참여 코드'), {
      target: { value: 'ABCXYZ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))

    expect(
      await screen.findByRole('heading', {
        name: '교수자 역할을 그대로 유지합니다',
      }),
    ).toHaveFocus()
    expect(
      screen.getByRole('link', { name: '관리 Course 보기' }),
    ).toHaveAttribute('href', '/#course-professor')
    expect(screen.queryByDisplayValue('ABCXYZ')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '다른 코드 입력' }))
    expect(await screen.findByLabelText('참여 코드')).toHaveFocus()
  })

  it('hides the submitted code when the server forbids the request', async () => {
    authenticate()
    server.use(
      http.post('*/api/v1/courses/join', () =>
        apiError(403, 'COURSE_ACCESS_DENIED'),
      ),
    )
    renderJoinPage()

    fireEvent.change(await screen.findByLabelText('참여 코드'), {
      target: { value: 'ABCXYZ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Course 참여 요청을 처리할 수 없습니다',
      }),
    ).toBeInTheDocument()
    expect(screen.queryByDisplayValue('ABCXYZ')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '다시 입력' }))
    expect(await screen.findByLabelText('참여 코드')).toHaveValue('')
  })

  it('hides the code and clears stale authentication before returning to login', async () => {
    let expired = false
    server.use(
      http.get('*/api/v1/me', () =>
        expired
          ? apiError(401, 'AUTHENTICATION_REQUIRED')
          : HttpResponse.json(user),
      ),
      http.post('*/api/v1/courses/join', () => {
        expired = true
        return apiError(401, 'AUTHENTICATION_REQUIRED')
      }),
    )
    const router = renderJoinPage()

    fireEvent.change(await screen.findByLabelText('참여 코드'), {
      target: { value: 'ABCXYZ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))

    expect(
      await screen.findByRole('heading', {
        name: '로그인 상태를 다시 확인해 주세요',
      }),
    ).toBeInTheDocument()
    expect(screen.queryByDisplayValue('ABCXYZ')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '다시 로그인' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe('?return_to=%2Fcourses%2Fjoin')
  })

  it('keeps one idempotency key for a retry and changes it with the code', async () => {
    authenticate()
    const keys: string[] = []
    server.use(
      http.post('*/api/v1/courses/join', ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        return apiError(503, 'DEPENDENCY_UNAVAILABLE')
      }),
    )
    renderJoinPage()

    const input = await screen.findByLabelText('참여 코드')
    fireEvent.change(input, { target: { value: 'ABCXYZ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))
    expect(
      await screen.findByText('Course에 참여하지 못했습니다.'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))
    await waitFor(() => expect(keys).toHaveLength(2))
    expect(keys[1]).toBe(keys[0])

    fireEvent.change(input, { target: { value: 'NEWKEY' } })
    expect(
      screen.queryByText('Course에 참여하지 못했습니다.'),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Course 참여하기' }))
    await waitFor(() => expect(keys).toHaveLength(3))
    expect(keys[2]).not.toBe(keys[1])
  })
})

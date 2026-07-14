import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { AppProviders } from '../../app/providers'
import { appRoutes } from '../../app/router'
import { server } from '../../test/server'

const user = {
  id: '00000000-0000-0000-0000-000000000001',
  display_name: '김도현',
  email: 'dohyun@example.test',
  avatar_url: null,
}

const createdCourse = {
  id: '10000000-0000-0000-0000-000000000001',
  title: '알고리즘',
  semester: '2026 여름학기',
  role: 'PROFESSOR' as const,
  join_code: 'ABCXYZ',
  current_session: null,
  created_at: '2026-07-14T00:00:00Z',
}

function renderCreatePage() {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ['/courses/new'],
  })
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

function fillCreateForm(
  title = '  알고리즘  ',
  semester = '  2026 여름학기  ',
) {
  fireEvent.change(screen.getByLabelText('과목명'), {
    target: { value: title },
  })
  fireEvent.change(screen.getByLabelText('학기'), {
    target: { value: semester },
  })
}

describe('COURSE_CREATE_PAGE', () => {
  it('connects field-specific validation and focuses the first invalid field', async () => {
    authenticate()
    let requests = 0
    server.use(
      http.post('*/api/v1/courses', () => {
        requests += 1
        return HttpResponse.json(createdCourse, { status: 201 })
      }),
    )
    renderCreatePage()

    const title = await screen.findByLabelText('과목명')
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))

    expect(title).toHaveFocus()
    expect(title).toHaveAccessibleDescription(
      '공백이 아닌 과목명을 입력해 주세요.',
    )
    expect(screen.getByLabelText('학기')).toHaveAccessibleDescription(
      '공백이 아닌 학기를 입력해 주세요.',
    )
    expect(requests).toBe(0)

    fireEvent.change(title, { target: { value: '알고리즘' } })
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))
    expect(screen.getByLabelText('학기')).toHaveFocus()
  })

  it('submits the typed contract once, locks pending input, and focuses the result', async () => {
    authenticate()
    let releaseRequest: (() => void) | undefined
    let requestBody: unknown
    let idempotencyKey: string | null = null
    server.use(
      http.post('*/api/v1/courses', async ({ request }) => {
        requestBody = await request.json()
        idempotencyKey = request.headers.get('Idempotency-Key')
        await new Promise<void>((resolve) => {
          releaseRequest = resolve
        })
        return HttpResponse.json(createdCourse, { status: 201 })
      }),
    )
    renderCreatePage()

    await screen.findByRole('heading', { name: '한 학기 Course 만들기' })
    fillCreateForm()
    const submit = screen.getByRole('button', { name: 'Course 만들기' })
    fireEvent.click(submit)

    expect(
      await screen.findByRole('button', { name: 'Course 만드는 중…' }),
    ).toBeDisabled()
    expect(screen.getByLabelText('과목명')).toBeDisabled()
    expect(screen.getByLabelText('학기')).toBeDisabled()
    expect(screen.getByRole('link', { name: '취소' })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    expect(requestBody).toEqual({
      title: '알고리즘',
      semester: '2026 여름학기',
    })
    expect(idempotencyKey).toMatch(/\S+/)

    releaseRequest?.()
    const resultTitle = await screen.findByRole('heading', {
      name: '알고리즘 Course를 만들었습니다',
    })
    await waitFor(() => expect(resultTitle).toHaveFocus())
    expect(screen.getByText('ABCXYZ')).toBeInTheDocument()
    expect(screen.getByText('교수자')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Course로 이동' })).toHaveAttribute(
      'href',
      `/courses/${createdCourse.id}`,
    )
  })

  it('reuses an idempotency key for the same retry and rotates it after input changes', async () => {
    authenticate()
    const keys: string[] = []
    server.use(
      http.post('*/api/v1/courses', ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        return HttpResponse.json(
          {
            error: {
              code: 'DEPENDENCY_UNAVAILABLE',
              message: '잠시 후 다시 시도해 주세요.',
              request_id: `req_create_${keys.length}`,
              details: null,
            },
          },
          { status: 503 },
        )
      }),
    )
    renderCreatePage()

    await screen.findByLabelText('과목명')
    fillCreateForm('알고리즘', '2026 여름학기')
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))
    expect(
      await screen.findByText('Course를 만들지 못했습니다.'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))
    await waitFor(() => expect(keys).toHaveLength(2))
    expect(keys[1]).toBe(keys[0])

    fireEvent.change(screen.getByLabelText('과목명'), {
      target: { value: '자료구조' },
    })
    expect(
      screen.queryByText('Course를 만들지 못했습니다.'),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))
    await waitFor(() => expect(keys).toHaveLength(3))
    expect(keys[2]).not.toBe(keys[1])
  })

  it('hides Course input after a mutation reports an expired login', async () => {
    let expired = false
    server.use(
      http.get('*/api/v1/me', () =>
        expired
          ? HttpResponse.json(
              {
                error: {
                  code: 'AUTHENTICATION_REQUIRED',
                  message: '로그인이 필요합니다.',
                  request_id: 'req_create_expired_me',
                  details: null,
                },
              },
              { status: 401 },
            )
          : HttpResponse.json(user),
      ),
      http.post('*/api/v1/courses', () => {
        expired = true
        return HttpResponse.json(
          {
            error: {
              code: 'AUTHENTICATION_REQUIRED',
              message: '로그인이 필요합니다.',
              request_id: 'req_create_expired',
              details: null,
            },
          },
          { status: 401 },
        )
      }),
    )
    const router = renderCreatePage()

    await screen.findByLabelText('과목명')
    fillCreateForm('알고리즘', '2026 여름학기')
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))

    expect(
      await screen.findByRole('heading', {
        name: '로그인 상태를 다시 확인해 주세요',
      }),
    ).toBeInTheDocument()
    expect(screen.queryByDisplayValue('알고리즘')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '다시 로그인' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe('?return_to=%2Fcourses%2Fnew')
  })

  it('announces both clipboard success and failure without hiding the result', async () => {
    authenticate()
    server.use(
      http.post('*/api/v1/courses', () =>
        HttpResponse.json(createdCourse, { status: 201 }),
      ),
    )
    const writeText = vi.fn().mockResolvedValueOnce(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    renderCreatePage()

    await screen.findByLabelText('과목명')
    fillCreateForm('알고리즘', '2026 여름학기')
    fireEvent.click(screen.getByRole('button', { name: 'Course 만들기' }))
    fireEvent.click(await screen.findByRole('button', { name: '코드 복사' }))

    expect(writeText).toHaveBeenCalledWith('ABCXYZ')
    expect(
      await screen.findByText('참여 코드를 복사했습니다.'),
    ).toBeInTheDocument()

    writeText.mockRejectedValueOnce(new Error('clipboard unavailable'))
    fireEvent.click(screen.getByRole('button', { name: '코드 복사' }))
    expect(
      await screen.findByText('참여 코드를 복사하지 못했습니다.'),
    ).toBeInTheDocument()
    expect(screen.getByText('ABCXYZ')).toBeInTheDocument()
  })
})

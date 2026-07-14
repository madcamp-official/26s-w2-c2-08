import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { server } from '../../test/server'
import { getCurrentUser, googleLoginUrl, logoutCurrentSession } from './api'

describe('auth API', () => {
  it('loads the current user through the typed contract', async () => {
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json({
          id: '00000000-0000-0000-0000-000000000001',
          display_name: '김도현',
          email: 'dohyun@example.test',
          avatar_url: null,
        }),
      ),
    )

    await expect(getCurrentUser()).resolves.toMatchObject({
      display_name: '김도현',
      email: 'dohyun@example.test',
    })
  })

  it('uses a browser navigation URL with the restored route', () => {
    const url = new URL(googleLoginUrl('/account?tab=security'))

    expect(url.pathname).toBe('/api/v1/auth/google/start')
    expect(url.searchParams.get('return_to')).toBe('/account?tab=security')
  })

  it('treats the idempotent 204 logout as success', async () => {
    server.use(
      http.post(
        '*/api/v1/auth/logout',
        () => new HttpResponse(null, { status: 204 }),
      ),
    )

    await expect(logoutCurrentSession()).resolves.toBeUndefined()
  })
})

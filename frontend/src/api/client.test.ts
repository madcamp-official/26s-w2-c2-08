import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  vi.resetModules()
})

describe('API client base URL', () => {
  it('does not duplicate the API path when a legacy /api base URL is configured', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '/api')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    const { apiClient, apiUrl } = await import('./client')
    await apiClient.GET('/api/health')

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe(`${window.location.origin}/api/health`)
    expect(apiUrl('/api/v1/auth/google/start')).toBe(
      `${window.location.origin}/api/v1/auth/google/start`,
    )
  })
})

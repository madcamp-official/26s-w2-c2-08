import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the API health status returned by the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ status: 'ok' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(screen.getByText('API 상태 확인 중…')).toBeInTheDocument()
    expect(await screen.findByText('API 연결 정상 · ok')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({
        headers: { Accept: 'application/json' },
      }),
    )
  })
})

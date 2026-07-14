import { describe, expect, it } from 'vitest'

import { apiErrorFromResponse, normalizeApiError } from './errors'

describe('API error normalization', () => {
  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'not-found'],
    [409, 'conflict'],
    [422, 'validation'],
  ] as const)('maps HTTP %i to the %s state', (status, kind) => {
    const response = new Response(null, { status })
    const error = apiErrorFromResponse(response, {
      error: {
        code: 'TEST_ERROR',
        message: '안전한 오류 메시지',
        request_id: 'req_test',
        details: null,
      },
    })

    expect(error).toMatchObject({
      status,
      kind,
      code: 'TEST_ERROR',
      requestId: 'req_test',
      message: '안전한 오류 메시지',
    })
  })

  it('uses a safe network message for unknown fetch failures', () => {
    const error = normalizeApiError(new TypeError('provider detail'))

    expect(error.code).toBe('NETWORK_ERROR')
    expect(error.message).not.toContain('provider detail')
  })
})

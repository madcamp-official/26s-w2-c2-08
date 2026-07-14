import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/errors'
import { shouldRetryQuery } from './query-client'

describe('query retry policy', () => {
  it.each([401, 403, 404, 409, 422])('does not retry HTTP %i', (status) => {
    expect(shouldRetryQuery(0, new ApiError('실패', { status }))).toBe(false)
  })

  it('retries a transient failure once', () => {
    expect(shouldRetryQuery(0, new ApiError('실패', { status: 503 }))).toBe(
      true,
    )
    expect(shouldRetryQuery(1, new ApiError('실패', { status: 503 }))).toBe(
      false,
    )
  })
})

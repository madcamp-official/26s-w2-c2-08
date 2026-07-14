import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/errors'
import { statePanelKindForApiError } from './api-error-state'

describe('API error state mapping', () => {
  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'not-found'],
    [409, 'conflict'],
    [422, 'validation'],
    [503, 'error'],
  ] as const)('maps HTTP %i to %s UI', (status, kind) => {
    expect(statePanelKindForApiError(new ApiError('실패', { status }))).toBe(
      kind,
    )
  })
})

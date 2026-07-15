import { describe, expect, it } from 'vitest'

import { sessionNeedsStatusPolling } from './queries'

describe('Session query polling', () => {
  it.each([
    ['READY', true],
    ['LIVE', false],
    ['PROCESSING', false],
    ['COMPLETED', false],
  ] as const)(
    'uses REST fallback polling for Session %s',
    (status, expected) => {
      expect(sessionNeedsStatusPolling({ status })).toBe(expected)
    },
  )

  it('does not poll before the Session is available', () => {
    expect(sessionNeedsStatusPolling(undefined)).toBe(false)
  })
})

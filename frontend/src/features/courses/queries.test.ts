import { describe, expect, it } from 'vitest'

import { sessionNeedsStatusPolling, sessionQueryOptions } from './queries'

describe('Session query polling', () => {
  it.each([
    ['READY', true],
    ['LIVE', true],
    ['PROCESSING', true],
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

  it('keeps lifecycle polling active in hidden tabs and rechecks on focus', () => {
    const options = sessionQueryOptions('session-1')

    expect(options.refetchIntervalInBackground).toBe(true)
    expect(options.refetchOnWindowFocus).toBe(true)
  })
})

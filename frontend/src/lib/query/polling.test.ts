import { describe, expect, it } from 'vitest'

import { pollingIntervalForJob } from './polling'

describe('AIJob polling interval', () => {
  it('polls while a job is pending or running', () => {
    expect(pollingIntervalForJob('PENDING')).toBe(1_500)
    expect(pollingIntervalForJob('RUNNING')).toBe(1_000)
  })

  it('stops after a terminal state', () => {
    expect(pollingIntervalForJob('SUCCEEDED')).toBe(false)
    expect(pollingIntervalForJob('FAILED')).toBe(false)
    expect(pollingIntervalForJob(undefined)).toBe(false)
  })
})

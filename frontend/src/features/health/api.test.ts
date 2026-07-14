import { describe, expect, it } from 'vitest'

import { getApiHealth } from './api'

describe('health API', () => {
  it('reads the OpenAPI-typed health response through MSW', async () => {
    await expect(getApiHealth()).resolves.toEqual({ status: 'ok' })
  })
})

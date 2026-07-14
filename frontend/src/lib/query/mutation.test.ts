import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/errors'
import { withApiErrorNormalization } from './mutation'

describe('mutation error normalization', () => {
  it('preserves a structured API error', async () => {
    const source = new ApiError('Course 상태가 변경되었습니다.', {
      status: 409,
      code: 'COURSE_STATE_CONFLICT',
    })
    const mutation = withApiErrorNormalization(async (courseId: string) => {
      void courseId
      throw source
    })

    await expect(mutation('course-1')).rejects.toBe(source)
  })

  it('turns an unknown failure into a safe network error', async () => {
    const mutation = withApiErrorNormalization(async (courseId: string) => {
      void courseId
      throw new TypeError('raw provider failure')
    })

    await expect(mutation('course-1')).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      kind: 'unknown',
    })
  })
})

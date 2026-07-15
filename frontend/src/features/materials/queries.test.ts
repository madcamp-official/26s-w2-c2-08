import { describe, expect, it } from 'vitest'

import type { LectureMaterial } from './api'
import { materialsNeedPolling } from './queries'

const material = {
  id: '40000000-0000-0000-0000-000000000001',
  session_id: '30000000-0000-0000-0000-000000000001',
  display_name: 'lecture.pdf',
  mime_type: 'application/pdf',
  byte_size: 1234,
  page_count: null,
  processing_status: 'UPLOADED',
  created_at: '2026-07-14T00:00:00Z',
} satisfies LectureMaterial

describe('Material query polling', () => {
  it.each([
    ['UPLOADED', true],
    ['PROCESSING', true],
    ['READY', false],
    ['FAILED', false],
  ] as const)(
    'polls Material status %s only while it can advance',
    (status, expected) => {
      expect(
        materialsNeedPolling({
          items: [{ ...material, processing_status: status }],
          next_cursor: null,
        }),
      ).toBe(expected)
    },
  )

  it('does not poll before the canonical Material list is available', () => {
    expect(materialsNeedPolling(undefined)).toBe(false)
  })
})

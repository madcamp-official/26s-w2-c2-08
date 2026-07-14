import { describe, expect, it } from 'vitest'

import { mergeCursorPages } from './cursor'

describe('cursor page merging', () => {
  it('keeps order and removes overlapping items after a refetch', () => {
    const result = mergeCursorPages(
      [
        {
          items: [
            { id: 'question-1', content: '첫 질문' },
            { id: 'question-2', content: '둘째 질문' },
          ],
          next_cursor: 'cursor-2',
        },
        {
          items: [
            { id: 'question-2', content: '둘째 질문' },
            { id: 'question-3', content: '셋째 질문' },
          ],
          next_cursor: null,
        },
      ],
      (item) => item.id,
    )

    expect(result.items.map((item) => item.id)).toEqual([
      'question-1',
      'question-2',
      'question-3',
    ])
    expect(result.nextCursor).toBeNull()
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '../../api/client'
import { getLiveTranscript } from './api'

vi.mock('../../api/client', () => ({
  apiClient: { GET: vi.fn() },
}))

const get = vi.mocked(apiClient.GET)

function page(
  versionId: string,
  segments: Array<{ id: string }>,
  nextCursor: string | null,
) {
  return {
    transcript: {},
    selected_version: { id: versionId },
    segments,
    gaps: [],
    next_cursor: nextCursor,
  }
}

describe('getLiveTranscript', () => {
  beforeEach(() => get.mockReset())

  it('collects every max-100 page while pinning the selected version', async () => {
    get
      .mockResolvedValueOnce({
        data: page('version-a', [{ id: 'segment-1' }], 'cursor-2'),
        error: undefined,
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: page('version-a', [{ id: 'segment-2' }], null),
        error: undefined,
        response: new Response(),
      } as never)

    const result = await getLiveTranscript('session-1')

    expect(result.segments.map((segment) => segment.id)).toEqual([
      'segment-1',
      'segment-2',
    ])
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[0]?.[1]).toMatchObject({
      params: { query: { limit: 100 } },
    })
    expect(get.mock.calls[1]?.[1]).toMatchObject({
      params: {
        query: {
          cursor: 'cursor-2',
          limit: 100,
          transcript_version_id: 'version-a',
        },
      },
    })
  })

  it('rejects a repeated cursor instead of looping forever', async () => {
    get
      .mockResolvedValueOnce({
        data: page('version-a', [], 'cursor-loop'),
        error: undefined,
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: page('version-a', [], 'cursor-loop'),
        error: undefined,
        response: new Response(),
      } as never)

    await expect(getLiveTranscript('session-1')).rejects.toMatchObject({
      message: 'Transcript cursor가 반복되어 복구를 중단했습니다.',
    })
  })

  it('rejects pages from a different transcript version', async () => {
    get
      .mockResolvedValueOnce({
        data: page('version-a', [], 'cursor-2'),
        error: undefined,
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: page('version-b', [], null),
        error: undefined,
        response: new Response(),
      } as never)

    await expect(getLiveTranscript('session-1')).rejects.toMatchObject({
      message: 'Transcript version이 페이지 조회 중 변경되었습니다.',
    })
  })
})

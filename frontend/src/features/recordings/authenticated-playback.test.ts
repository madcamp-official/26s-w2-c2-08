import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchAuthenticatedPlaybackUrl } from './authenticated-playback'

describe('fetchAuthenticatedPlaybackUrl', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses a credentialed request before returning a local Blob URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue({ size: 9 }),
    })
    const createObjectUrl = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:goal-recording')
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchAuthenticatedPlaybackUrl('/api/v1/recordings/recording-1/playback'),
    ).resolves.toBe('blob:goal-recording')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/recordings/recording-1/playback'),
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(createObjectUrl).toHaveBeenCalledTimes(1)
  })

  it('does not create a Blob URL for an unauthorized playback response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    const createObjectUrl = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:unreachable')
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchAuthenticatedPlaybackUrl('/api/v1/recordings/recording-1/playback'),
    ).rejects.toThrow('401')

    expect(createObjectUrl).not.toHaveBeenCalled()
  })
})

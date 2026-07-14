import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  completeRecordingUpload: vi.fn(),
  createRecordingUpload: vi.fn(),
  getRecordingUpload: vi.fn(),
  uploadRecordingChunk: vi.fn(),
}))
const localDb = vi.hoisted(() => ({
  blobFrom: vi.fn(),
  deleteAcknowledgedFragments: vi.fn(),
  getRecordingMeta: vi.fn(),
  putRecordingMeta: vi.fn(),
}))

vi.mock('./api', () => api)
vi.mock('./local-db', () => localDb)

import { uploadLocalRecording } from './uploader'

const metadata = {
  sessionId: 'session-1',
  clientStreamId: 'stream-1',
  contentType: 'audio/webm' as const,
  durationMs: 1_000,
  totalBytes: 4,
  nextSequence: 1,
  finalSha256: 'a'.repeat(64),
  finalized: true,
  uploadId: null,
  acknowledgedOffset: 0,
  failedReason: null,
}

describe('uploadLocalRecording', () => {
  it('removes local fragments only after the server confirms a contiguous offset', async () => {
    localDb.getRecordingMeta.mockResolvedValue(metadata)
    api.createRecordingUpload.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 0,
    })
    localDb.blobFrom.mockResolvedValue(
      new Blob(['test'], { type: 'audio/webm' }),
    )
    api.uploadRecordingChunk.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 4,
    })
    api.completeRecordingUpload.mockResolvedValue({})

    const progress = vi.fn()
    await uploadLocalRecording('session-1', progress)

    expect(localDb.deleteAcknowledgedFragments).toHaveBeenNthCalledWith(
      1,
      'session-1',
      0,
    )
    expect(localDb.deleteAcknowledgedFragments).toHaveBeenNthCalledWith(
      2,
      'session-1',
      4,
    )
    expect(api.completeRecordingUpload).toHaveBeenCalledWith(
      'upload-1',
      metadata.finalSha256,
    )
    expect(progress).toHaveBeenLastCalledWith('completed', 4)
  })

  it('keeps local fragments when a chunk request fails', async () => {
    localDb.getRecordingMeta.mockResolvedValue(metadata)
    api.createRecordingUpload.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 0,
    })
    localDb.blobFrom.mockResolvedValue(
      new Blob(['test'], { type: 'audio/webm' }),
    )
    api.uploadRecordingChunk.mockRejectedValue(
      new Error('network disconnected'),
    )

    await expect(uploadLocalRecording('session-1', vi.fn())).rejects.toThrow(
      'network disconnected',
    )

    expect(localDb.deleteAcknowledgedFragments).toHaveBeenCalledTimes(1)
    expect(localDb.deleteAcknowledgedFragments).toHaveBeenLastCalledWith(
      'session-1',
      0,
    )
  })

  it('resumes a known upload at the server offset after a refresh', async () => {
    localDb.getRecordingMeta.mockResolvedValue({
      ...metadata,
      totalBytes: 8,
      uploadId: 'upload-1',
    })
    api.getRecordingUpload.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 4,
    })
    localDb.blobFrom.mockResolvedValue(
      new Blob(['more'], { type: 'audio/webm' }),
    )
    api.uploadRecordingChunk.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 8,
    })
    api.completeRecordingUpload.mockResolvedValue({})

    await uploadLocalRecording('session-1', vi.fn())

    expect(api.createRecordingUpload).not.toHaveBeenCalled()
    expect(api.getRecordingUpload).toHaveBeenCalledWith('upload-1')
    expect(localDb.blobFrom).toHaveBeenCalledWith(
      'session-1',
      4,
      4,
      'audio/webm',
    )
    expect(localDb.deleteAcknowledgedFragments).toHaveBeenNthCalledWith(
      1,
      'session-1',
      4,
    )
  })
})

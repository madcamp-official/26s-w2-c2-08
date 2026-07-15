import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RecordingMeta } from './local-db'

const api = vi.hoisted(() => ({
  completeRecordingUpload: vi.fn(),
  createRecordingUpload: vi.fn(),
  getSessionRecording: vi.fn(),
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

const acquireLease = vi.fn(async () => vi.fn())

function upload(
  progress: Parameters<typeof uploadLocalRecording>[1] = vi.fn(),
) {
  return uploadLocalRecording('session-1', progress, acquireLease)
}

const baseMeta: RecordingMeta = {
  sessionId: 'session-1',
  clientStreamId: 'stream-1',
  contentType: 'audio/webm',
  durationMs: 1_000,
  totalBytes: 4,
  nextSequence: 1,
  finalSha256: 'a'.repeat(64),
  finalized: true,
  uploadId: null,
  acknowledgedOffset: 0,
  failedReason: null,
  uploadCreateKey: null,
  uploadCompleteKey: null,
  uploadState: 'NOT_STARTED',
}

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), { status })
}

describe('uploadLocalRecording recovery', () => {
  let current: RecordingMeta

  beforeEach(() => {
    vi.clearAllMocks()
    acquireLease.mockImplementation(async () => vi.fn())
    current = { ...baseMeta }
    localDb.getRecordingMeta.mockImplementation(async () => current)
    localDb.putRecordingMeta.mockImplementation(async (next: RecordingMeta) => {
      current = next
    })
    localDb.blobFrom.mockResolvedValue(new Blob(['data']))
    localDb.deleteAcknowledgedFragments.mockResolvedValue(undefined)
    api.uploadRecordingChunk.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 4,
    })
    api.createRecordingUpload.mockResolvedValue({
      id: 'upload-2',
      offset_bytes: 0,
    })
    api.completeRecordingUpload.mockResolvedValue({})
    api.getSessionRecording.mockResolvedValue({ status: 'UPLOADING' })
  })

  it('reports failed when the first local metadata read rejects', async () => {
    localDb.getRecordingMeta.mockRejectedValue(new Error('IndexedDB blocked'))
    const progress = vi.fn()

    await expect(upload(progress)).rejects.toThrow('IndexedDB blocked')

    expect(progress).toHaveBeenLastCalledWith('failed')
  })

  it('persists and reuses the create idempotency key after a lost response', async () => {
    api.createRecordingUpload
      .mockRejectedValueOnce(new Error('response lost'))
      .mockResolvedValueOnce({ id: 'upload-1', offset_bytes: 0 })

    await expect(upload()).rejects.toThrow('response lost')
    const persistedKey = current.uploadCreateKey

    await upload()

    expect(persistedKey).toEqual(expect.any(String))
    expect(api.createRecordingUpload).toHaveBeenNthCalledWith(
      1,
      'session-1',
      expect.any(Object),
      persistedKey,
    )
    expect(api.createRecordingUpload).toHaveBeenNthCalledWith(
      2,
      'session-1',
      expect.any(Object),
      persistedKey,
    )
    expect(current.uploadState).toBe('COMPLETED')
  })

  it('persists and reuses the complete idempotency key after a lost response', async () => {
    current = {
      ...current,
      uploadId: 'upload-1',
      uploadState: 'ACTIVE',
      acknowledgedOffset: 4,
    }
    api.getRecordingUpload.mockResolvedValue({
      id: 'upload-1',
      offset_bytes: 4,
    })
    api.completeRecordingUpload
      .mockRejectedValueOnce(new Error('response lost'))
      .mockResolvedValueOnce({})

    await expect(upload()).rejects.toThrow('response lost')
    const persistedKey = current.uploadCompleteKey

    await upload()

    expect(persistedKey).toEqual(expect.any(String))
    expect(api.completeRecordingUpload).toHaveBeenNthCalledWith(
      1,
      'upload-1',
      baseMeta.finalSha256,
      persistedKey,
    )
    expect(api.completeRecordingUpload).toHaveBeenNthCalledWith(
      2,
      'upload-1',
      baseMeta.finalSha256,
      persistedKey,
    )
    expect(current.uploadState).toBe('COMPLETED')
  })

  it('reconciles a hidden completed upload from canonical Recording state', async () => {
    current = {
      ...current,
      uploadId: 'upload-1',
      uploadState: 'ACTIVE',
      uploadCompleteKey: 'complete-key',
    }
    api.getRecordingUpload.mockRejectedValue(httpError(404))
    api.getSessionRecording.mockResolvedValue({ status: 'UPLOADED' })
    const progress = vi.fn()

    await upload(progress)

    expect(current.uploadState).toBe('COMPLETED')
    expect(progress).toHaveBeenLastCalledWith('completed', 4)
    expect(api.completeRecordingUpload).not.toHaveBeenCalled()
  })

  it.each([
    [404, 'UPLOAD_PENDING', 0, 'fresh'],
    [404, 'UPLOAD_PENDING', 2, 'expired'],
    [404, 'FAILED', 0, 'fresh'],
    [404, 'FAILED', 2, 'expired'],
    [410, 'UPLOAD_PENDING', 0, 'fresh'],
    [410, 'UPLOAD_PENDING', 2, 'expired'],
    [410, 'FAILED', 0, 'fresh'],
    [410, 'FAILED', 2, 'expired'],
  ] as const)(
    'reconciles HTTP %i with canonical %s at offset %i as %s',
    async (httpStatus, status, acknowledgedOffset, expected) => {
      current = {
        ...current,
        uploadId: 'upload-1',
        uploadState: 'ACTIVE',
        acknowledgedOffset,
      }
      api.getRecordingUpload.mockRejectedValue(httpError(httpStatus))
      api.getSessionRecording.mockResolvedValue({ status })
      const progress = vi.fn()

      await upload(progress)

      if (expected === 'fresh') {
        expect(api.createRecordingUpload).toHaveBeenCalledWith(
          'session-1',
          expect.any(Object),
          expect.any(String),
        )
        expect(current.uploadId).toBe('upload-2')
        expect(current.uploadState).toBe('COMPLETED')
        expect(progress).toHaveBeenLastCalledWith('completed', 4)
      } else {
        expect(api.createRecordingUpload).not.toHaveBeenCalled()
        expect(current.uploadState).toBe('EXPIRED')
        expect(progress).toHaveBeenLastCalledWith('expired', acknowledgedOffset)
      }
    },
  )

  it('restarts after an expired create replay while the complete local source remains', async () => {
    api.createRecordingUpload
      .mockRejectedValueOnce(httpError(410))
      .mockResolvedValueOnce({ id: 'upload-fresh', offset_bytes: 0 })
    api.getSessionRecording.mockResolvedValue({ status: 'FAILED' })

    await upload()

    expect(api.createRecordingUpload).toHaveBeenCalledTimes(2)
    expect(current.uploadId).toBe('upload-fresh')
    expect(current.uploadState).toBe('COMPLETED')
  })

  it('restarts after the first zero-offset chunk races upload expiry', async () => {
    api.createRecordingUpload
      .mockResolvedValueOnce({ id: 'upload-expired', offset_bytes: 0 })
      .mockResolvedValueOnce({ id: 'upload-fresh', offset_bytes: 0 })
    api.uploadRecordingChunk
      .mockRejectedValueOnce(httpError(410))
      .mockResolvedValueOnce({ id: 'upload-fresh', offset_bytes: 4 })
    api.getSessionRecording.mockResolvedValue({ status: 'UPLOAD_PENDING' })

    await upload()

    expect(api.createRecordingUpload).toHaveBeenCalledTimes(2)
    expect(api.uploadRecordingChunk).toHaveBeenCalledTimes(2)
    expect(current.uploadId).toBe('upload-fresh')
    expect(current.uploadState).toBe('COMPLETED')
  })

  it('keeps canonical completion visible when the local terminal write fails', async () => {
    current = {
      ...current,
      uploadId: 'upload-1',
      uploadState: 'ACTIVE',
    }
    api.getRecordingUpload.mockRejectedValue(httpError(404))
    api.getSessionRecording.mockResolvedValue({ status: 'UPLOADED' })
    localDb.putRecordingMeta.mockRejectedValue(new Error('IndexedDB blocked'))
    const progress = vi.fn()

    await upload(progress)

    expect(progress).toHaveBeenLastCalledWith('completed', 4)
  })

  it('preserves a complete local source until an expired upload can be reconciled', async () => {
    current = {
      ...current,
      uploadId: 'upload-1',
      uploadState: 'ACTIVE',
    }
    api.getRecordingUpload.mockRejectedValue(httpError(410))
    api.getSessionRecording
      .mockResolvedValueOnce({ status: 'UPLOADING' })
      .mockResolvedValue({ status: 'UPLOAD_PENDING' })
    const firstProgress = vi.fn()

    await expect(upload(firstProgress)).rejects.toMatchObject({ status: 410 })
    expect(current.uploadState).toBe('ACTIVE')
    expect(current.acknowledgedOffset).toBe(0)
    expect(firstProgress).toHaveBeenLastCalledWith('failed')

    const secondProgress = vi.fn()
    await upload(secondProgress)
    expect(secondProgress).toHaveBeenLastCalledWith('completed', 4)
    expect(current.uploadState).toBe('COMPLETED')
    expect(api.getRecordingUpload).toHaveBeenCalledTimes(2)
  })

  it('allows only one tab to create and upload the local recording', async () => {
    let held = false
    const sharedLease = vi.fn(async () => {
      if (held) return null
      held = true
      return () => {
        held = false
      }
    })
    let finishCreate:
      ((upload: { id: string; offset_bytes: number }) => void) | undefined
    api.createRecordingUpload.mockImplementation(
      () =>
        new Promise<{ id: string; offset_bytes: number }>((resolve) => {
          finishCreate = resolve
        }),
    )
    const first = uploadLocalRecording('session-1', vi.fn(), sharedLease)
    await vi.waitFor(() =>
      expect(api.createRecordingUpload).toHaveBeenCalledTimes(1),
    )
    const secondProgress = vi.fn()

    await uploadLocalRecording('session-1', secondProgress, sharedLease)

    expect(secondProgress).toHaveBeenLastCalledWith('owned_elsewhere')
    expect(api.createRecordingUpload).toHaveBeenCalledTimes(1)

    finishCreate?.({ id: 'upload-1', offset_bytes: 0 })
    await first
    expect(held).toBe(false)
    expect(api.completeRecordingUpload).toHaveBeenCalledTimes(1)

    const takeoverProgress = vi.fn()
    await uploadLocalRecording('session-1', takeoverProgress, sharedLease)
    expect(takeoverProgress).toHaveBeenLastCalledWith('completed', 4)
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RecordingMeta } from './local-db'

const localDb = vi.hoisted(() => ({
  appendFragment: vi.fn(),
  getRecordingMeta: vi.fn(),
  putRecordingMeta: vi.fn(),
  wholeBlob: vi.fn(),
}))
const api = vi.hoisted(() => ({ sha256: vi.fn() }))

vi.mock('./local-db', () => localDb)
vi.mock('./api', () => api)

import {
  LocalRecorder,
  RecordingAlreadyFinalizedError,
  RecordingFailedMetaError,
  RecordingInterruptedMetaError,
  RecordingStreamConflictError,
  recoverLocalRecording,
} from './local-recorder'

const acquireLease = vi.fn(async () => vi.fn())

function createRecorder(onStorageFailure?: () => void) {
  return new LocalRecorder(onStorageFailure, acquireLease)
}

class FakeMediaRecorder {
  static current: FakeMediaRecorder | null = null
  static deferStopEvent = false
  static isTypeSupported(type: string) {
    return type === 'audio/webm;codecs=opus'
  }

  state: RecordingState = 'inactive'
  ondataavailable: ((event: BlobEvent) => void) | null = null
  onstop: ((event: Event) => void) | null = null

  constructor(stream: MediaStream, options: MediaRecorderOptions) {
    void stream
    void options
    FakeMediaRecorder.current = this
  }

  start() {
    this.state = 'recording'
  }

  requestData() {
    this.ondataavailable?.({ data: new Blob(['part']) } as BlobEvent)
  }

  pause() {
    this.state = 'paused'
  }

  resume() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['last']) } as BlobEvent)
    if (!FakeMediaRecorder.deferStopEvent) this.emitStop()
  }

  emitStop() {
    this.onstop?.(new Event('stop'))
  }
}

const metadata: RecordingMeta = {
  sessionId: 'session-1',
  clientStreamId: 'stream-1',
  contentType: 'audio/webm' as const,
  durationMs: 0,
  totalBytes: 0,
  nextSequence: 0,
  finalSha256: null,
  finalized: false,
  uploadId: null,
  acknowledgedOffset: 0,
  failedReason: null,
}

describe('LocalRecorder finalization', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    acquireLease.mockImplementation(async () => vi.fn())
    FakeMediaRecorder.current = null
    FakeMediaRecorder.deferStopEvent = false
  })

  it('waits for the final IndexedDB fragment before calculating the upload hash', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    let current: RecordingMeta | null = null
    let finishAppend: ((value: RecordingMeta) => void) | undefined
    localDb.getRecordingMeta.mockImplementation(async () => current)
    localDb.putRecordingMeta.mockImplementation(async (next: RecordingMeta) => {
      current = next
    })
    localDb.appendFragment.mockImplementation(
      () =>
        new Promise<RecordingMeta>((resolve) => {
          finishAppend = (next) => {
            current = next
            resolve(next)
          }
        }),
    )
    localDb.wholeBlob.mockResolvedValue(new Blob(['last']))
    api.sha256.mockResolvedValue('a'.repeat(64))

    try {
      const recorder = createRecorder()
      await recorder.start('session-1', {} as MediaStream, 'stream-1')
      const stopping = recorder.stop()

      await vi.waitFor(() => {
        expect(localDb.appendFragment).toHaveBeenCalled()
      })
      expect(localDb.wholeBlob).not.toHaveBeenCalled()

      finishAppend?.({
        ...metadata,
        totalBytes: 4,
        nextSequence: 1,
      })
      await stopping

      expect(localDb.wholeBlob).toHaveBeenCalledWith('session-1', 'audio/webm')
      expect(api.sha256).toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('finalizes pending fragments even when MediaRecorder already became inactive', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    localDb.getRecordingMeta
      .mockResolvedValueOnce(null)
      .mockResolvedValue({ ...metadata, totalBytes: 5 })
    localDb.wholeBlob.mockResolvedValue(new Blob(['saved']))
    api.sha256.mockResolvedValue('b'.repeat(64))
    const stopTrack = vi.fn()

    try {
      const recorder = createRecorder()
      await recorder.start(
        'session-1',
        { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream,
        'stream-1',
      )
      if (FakeMediaRecorder.current) {
        FakeMediaRecorder.current.state = 'inactive'
      }

      const finalized = await recorder.stop()

      expect(localDb.wholeBlob).toHaveBeenCalledWith('session-1', 'audio/webm')
      expect(finalized).toMatchObject({
        finalized: true,
        finalSha256: 'b'.repeat(64),
      })
      expect(stopTrack).toHaveBeenCalledTimes(1)
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('quiesces and resumes the same recorder while end acceptance is checked', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    let current: RecordingMeta | null = null
    localDb.getRecordingMeta.mockImplementation(async () => current)
    localDb.putRecordingMeta.mockImplementation(async (next: RecordingMeta) => {
      current = next
    })
    localDb.appendFragment.mockImplementation(
      async (meta: RecordingMeta, blob: Blob, durationMs: number) => {
        current = {
          ...meta,
          durationMs,
          totalBytes: meta.totalBytes + blob.size,
          nextSequence: meta.nextSequence + 1,
        }
        return current
      },
    )
    localDb.wholeBlob.mockResolvedValue(new Blob(['partlast']))
    api.sha256.mockResolvedValue('f'.repeat(64))

    try {
      const recorder = createRecorder()
      await recorder.start('session-1', {} as MediaStream, 'stream-1')

      await recorder.quiesceForEnd()
      expect(FakeMediaRecorder.current?.state).toBe('paused')

      await expect(recorder.resumeAfterEndFailure()).resolves.toBe(true)
      expect(FakeMediaRecorder.current?.state).toBe('recording')

      await expect(recorder.stop()).resolves.toMatchObject({
        finalized: true,
        totalBytes: 8,
      })
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('fails closed when a paused recorder cannot resume after an end request failure', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    let current: RecordingMeta | null = null
    const stopTrack = vi.fn()
    const releaseLease = vi.fn()
    acquireLease.mockResolvedValueOnce(releaseLease)
    localDb.getRecordingMeta.mockImplementation(async () => current)
    localDb.putRecordingMeta.mockImplementation(async (next: RecordingMeta) => {
      current = next
    })
    localDb.appendFragment.mockImplementation(
      async (meta: RecordingMeta, blob: Blob) => {
        current = {
          ...meta,
          totalBytes: meta.totalBytes + blob.size,
          nextSequence: meta.nextSequence + 1,
        }
        return current
      },
    )

    try {
      const recorder = createRecorder()
      await recorder.start(
        'session-1',
        { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream,
        'stream-1',
      )
      await recorder.quiesceForEnd()
      if (FakeMediaRecorder.current) {
        FakeMediaRecorder.current.resume = () => {
          throw new DOMException('cannot resume', 'InvalidStateError')
        }
      }

      await expect(recorder.resumeAfterEndFailure()).resolves.toBe(false)
      expect(FakeMediaRecorder.current?.state).toBe('inactive')
      expect(stopTrack).toHaveBeenCalledTimes(1)
      expect(releaseLease).toHaveBeenCalledTimes(1)
      await expect(recorder.stop()).resolves.toMatchObject({
        failedReason: 'LOCAL_CAPTURE_INTERRUPTED',
        finalized: false,
        finalSha256: null,
        finalizationReady: false,
      })
      expect(localDb.wholeBlob).not.toHaveBeenCalled()
      expect(api.sha256).not.toHaveBeenCalled()
      expect(releaseLease).toHaveBeenCalledTimes(1)
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('recovers orphaned fragments after the former recording lease disappeared', async () => {
    const release = vi.fn()
    const recoveryLease = vi.fn(async () => release)
    const orphan = {
      ...metadata,
      durationMs: 4_000,
      totalBytes: 4,
      finalizationReady: true,
    }
    localDb.getRecordingMeta.mockResolvedValue(orphan)
    localDb.wholeBlob.mockResolvedValue(new Blob(['data']))
    api.sha256.mockResolvedValue('c'.repeat(64))

    const result = await recoverLocalRecording('session-1', recoveryLease)

    expect(result).toEqual({
      status: 'finalized',
      meta: {
        ...orphan,
        finalized: true,
        finalSha256: 'c'.repeat(64),
      },
    })
    expect(localDb.putRecordingMeta).toHaveBeenCalledWith(
      expect.objectContaining({
        durationMs: 4_000,
        totalBytes: 4,
        finalized: true,
      }),
    )
    expect(release).toHaveBeenCalledTimes(1)
  })

  it('fails closed when an orphan has no committed final-fragment marker', async () => {
    const interrupted = {
      ...metadata,
      durationMs: 4_000,
      totalBytes: 4,
      finalizationReady: false,
    }
    localDb.getRecordingMeta.mockResolvedValue(interrupted)

    const result = await recoverLocalRecording(
      'session-1',
      async () => () => undefined,
    )

    expect(result).toEqual({
      status: 'failed',
      meta: {
        ...interrupted,
        failedReason: 'LOCAL_CAPTURE_INTERRUPTED',
        finalSha256: null,
      },
    })
    expect(localDb.wholeBlob).not.toHaveBeenCalled()
    expect(api.sha256).not.toHaveBeenCalled()
  })

  it('does not race orphan recovery against a normal in-flight finalizer', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    let held = false
    const sharedLease = vi.fn(async () => {
      if (held) return null
      held = true
      return () => {
        held = false
      }
    })
    localDb.getRecordingMeta
      .mockResolvedValueOnce(null)
      .mockResolvedValue({ ...metadata, totalBytes: 5 })
    localDb.wholeBlob.mockResolvedValue(new Blob(['saved']))
    api.sha256.mockResolvedValue('d'.repeat(64))

    try {
      const recorder = new LocalRecorder(undefined, sharedLease)
      await recorder.start('session-1', {} as MediaStream, 'stream-1')
      if (FakeMediaRecorder.current)
        FakeMediaRecorder.current.state = 'inactive'

      await expect(
        recoverLocalRecording('session-1', sharedLease),
      ).resolves.toEqual({ status: 'owned_elsewhere' })
      expect(localDb.wholeBlob).not.toHaveBeenCalled()

      await recorder.stop()
      expect(held).toBe(false)
      expect(localDb.wholeBlob).toHaveBeenCalledTimes(1)
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('does not concatenate fragments from a previous MediaRecorder instance', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    localDb.getRecordingMeta.mockResolvedValue({
      ...metadata,
      durationMs: 4_000,
      totalBytes: 4,
    })

    try {
      await expect(
        createRecorder().start('session-1', {} as MediaStream, 'stream-1'),
      ).rejects.toBeInstanceOf(RecordingInterruptedMetaError)
      expect(localDb.putRecordingMeta).toHaveBeenCalledWith(
        expect.objectContaining({
          failedReason: 'LOCAL_CAPTURE_INTERRUPTED',
          finalizationReady: false,
        }),
      )
      expect(localDb.appendFragment).not.toHaveBeenCalled()
      expect(FakeMediaRecorder.current).toBeNull()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('rejects a second tab while the recording lifecycle lock is owned', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    try {
      await expect(
        new LocalRecorder(undefined, async () => null).start(
          'session-1',
          {} as MediaStream,
          'stream-new',
        ),
      ).rejects.toBeInstanceOf(RecordingStreamConflictError)
      expect(localDb.getRecordingMeta).not.toHaveBeenCalled()
      expect(localDb.putRecordingMeta).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('serializes an unmount stop with an in-flight recording start', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    let finishPut: (() => void) | undefined
    localDb.getRecordingMeta
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(metadata)
    localDb.putRecordingMeta
      .mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            finishPut = resolve
          }),
      )
      .mockResolvedValue(undefined)
    localDb.wholeBlob.mockResolvedValue(new Blob([]))
    const stopTrack = vi.fn()

    try {
      const recorder = createRecorder()
      const starting = recorder.start(
        'session-1',
        { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream,
        'stream-1',
      )
      await vi.waitFor(() => expect(finishPut).toBeTypeOf('function'))
      const stopping = recorder.stop()
      finishPut?.()

      await starting
      const finalized = await stopping

      expect(FakeMediaRecorder.current).toBeNull()
      expect(finalized).toMatchObject({
        finalized: false,
        failedReason: 'EMPTY_RECORDING',
        finalSha256: null,
      })
      expect(api.sha256).not.toHaveBeenCalled()
      expect(stopTrack).toHaveBeenCalledTimes(1)
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('does not append new fragments to an already finalized recording', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    localDb.getRecordingMeta.mockResolvedValue({
      ...metadata,
      finalized: true,
      finalSha256: 'd'.repeat(64),
    })

    try {
      await expect(
        createRecorder().start('session-1', {} as MediaStream, 'stream-1'),
      ).rejects.toBeInstanceOf(RecordingAlreadyFinalizedError)
      expect(FakeMediaRecorder.current).toBeNull()
      expect(localDb.putRecordingMeta).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('does not restart a local recording whose metadata is already failed', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    localDb.getRecordingMeta.mockResolvedValue({
      ...metadata,
      failedReason: 'LOCAL_STORAGE_FAILED',
    })

    try {
      await expect(
        createRecorder().start('session-1', {} as MediaStream, 'stream-1'),
      ).rejects.toBeInstanceOf(RecordingFailedMetaError)
      expect(FakeMediaRecorder.current).toBeNull()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('records a terminal failure when final blob assembly fails', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    const onStorageFailure = vi.fn()
    const stopTrack = vi.fn()
    localDb.getRecordingMeta
      .mockResolvedValueOnce(null)
      .mockResolvedValue(metadata)
    localDb.appendFragment.mockResolvedValue({
      ...metadata,
      totalBytes: 4,
      nextSequence: 1,
    })
    localDb.wholeBlob.mockRejectedValue(new Error('IndexedDB read failed'))

    try {
      const recorder = createRecorder(onStorageFailure)
      await recorder.start(
        'session-1',
        { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream,
        'stream-1',
      )

      const result = await recorder.stop()

      expect(result).toMatchObject({
        finalized: false,
        failedReason: 'LOCAL_FINALIZATION_FAILED',
        finalSha256: null,
      })
      expect(onStorageFailure).toHaveBeenCalledTimes(1)
      expect(stopTrack).toHaveBeenCalledTimes(1)
      expect(api.sha256).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('stops capture and releases its track after an IndexedDB fragment failure', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    const stopTrack = vi.fn()
    const onStorageFailure = vi.fn()
    localDb.getRecordingMeta
      .mockResolvedValueOnce(null)
      .mockResolvedValue(metadata)
    localDb.appendFragment.mockRejectedValue(new Error('quota exceeded'))
    localDb.putRecordingMeta
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('meta write failed'))

    try {
      const recorder = createRecorder(onStorageFailure)
      await recorder.start(
        'session-1',
        { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream,
        'stream-1',
      )
      FakeMediaRecorder.current?.ondataavailable?.({
        data: new Blob(['chunk']),
      } as BlobEvent)

      await vi.waitFor(() => expect(onStorageFailure).toHaveBeenCalledTimes(1))
      expect(FakeMediaRecorder.current?.state).toBe('inactive')
      expect(stopTrack).toHaveBeenCalledTimes(1)
      const result = await recorder.stop()
      expect(result).toMatchObject({
        failedReason: 'LOCAL_STORAGE_FAILED',
        finalized: false,
        finalSha256: null,
      })
      expect(localDb.wholeBlob).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })

  it('settles stop when the final fragment fails before MediaRecorder emits stop', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    FakeMediaRecorder.deferStopEvent = true
    const stopTrack = vi.fn()
    const onStorageFailure = vi.fn()
    let rejectAppend: ((reason: Error) => void) | undefined
    localDb.getRecordingMeta
      .mockResolvedValueOnce(null)
      .mockResolvedValue(metadata)
    localDb.appendFragment.mockImplementation(
      () =>
        new Promise<typeof metadata>((_resolve, reject) => {
          rejectAppend = reject
        }),
    )
    localDb.putRecordingMeta
      .mockResolvedValueOnce(undefined)
      .mockRejectedValue(new Error('meta write failed'))

    try {
      const recorder = createRecorder(onStorageFailure)
      await recorder.start(
        'session-1',
        { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream,
        'stream-1',
      )
      const stopping = recorder.stop()
      await vi.waitFor(() => expect(localDb.appendFragment).toHaveBeenCalled())

      rejectAppend?.(new Error('final fragment failed'))
      await vi.waitFor(() => expect(onStorageFailure).toHaveBeenCalledTimes(1))

      const result = await stopping
      expect(result).toMatchObject({
        failedReason: 'LOCAL_STORAGE_FAILED',
        finalized: false,
        finalSha256: null,
      })
      expect(stopTrack).toHaveBeenCalledTimes(1)
      expect(localDb.wholeBlob).not.toHaveBeenCalled()
    } finally {
      FakeMediaRecorder.current?.emitStop()
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })
})

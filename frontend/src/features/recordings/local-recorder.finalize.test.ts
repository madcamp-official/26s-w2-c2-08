import { describe, expect, it, vi } from 'vitest'
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

import { LocalRecorder } from './local-recorder'

class FakeMediaRecorder {
  static current: FakeMediaRecorder | null = null
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

  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['last']) } as BlobEvent)
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
  it('waits for the final IndexedDB fragment before calculating the upload hash', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: FakeMediaRecorder,
    })
    let current = metadata
    let finishAppend: ((value: typeof metadata) => void) | undefined
    localDb.getRecordingMeta.mockImplementation(async () => current)
    localDb.appendFragment.mockImplementation(
      () =>
        new Promise<typeof metadata>((resolve) => {
          finishAppend = (next) => {
            current = next
            resolve(next)
          }
        }),
    )
    localDb.wholeBlob.mockResolvedValue(new Blob(['last']))
    api.sha256.mockResolvedValue('a'.repeat(64))

    try {
      const recorder = new LocalRecorder()
      await recorder.start('session-1', {} as MediaStream, 'stream-1')
      const stopping = recorder.stop()

      await Promise.resolve()
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
})

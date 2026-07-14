import {
  appendFragment,
  getRecordingMeta,
  putRecordingMeta,
  wholeBlob,
  type RecordingMeta,
} from './local-db'
import { sha256 } from './api'

export class BrowserRecordingUnsupportedError extends Error {}

export class LocalRecorder {
  private recorder: MediaRecorder | null = null
  private startedAt = 0
  private meta: RecordingMeta | null = null
  private fragmentWrites: Promise<void> = Promise.resolve()

  constructor(private readonly onStorageFailure?: () => void) {}

  async start(sessionId: string, stream: MediaStream, clientStreamId: string) {
    if (typeof MediaRecorder === 'undefined')
      throw new BrowserRecordingUnsupportedError()
    const contentType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm'
      : MediaRecorder.isTypeSupported('audio/mp4')
        ? 'audio/mp4'
        : null
    if (!contentType) throw new BrowserRecordingUnsupportedError()
    const existing = await getRecordingMeta(sessionId)
    this.meta = existing ?? {
      sessionId,
      clientStreamId,
      contentType,
      durationMs: 0,
      totalBytes: 0,
      nextSequence: 0,
      finalSha256: null,
      finalized: false,
      uploadId: null,
      acknowledgedOffset: 0,
      failedReason: null,
    }
    await putRecordingMeta(this.meta)
    this.startedAt = performance.now()
    this.recorder = new MediaRecorder(stream, { mimeType: contentType })
    this.recorder.ondataavailable = (event) => {
      if (!event.data.size) return
      this.fragmentWrites = this.fragmentWrites
        .then(async () => {
          if (!this.meta) return
          this.meta = await appendFragment(this.meta, event.data)
        })
        .catch(async () => {
          if (!this.meta) return
          this.meta = {
            ...this.meta,
            failedReason: 'LOCAL_STORAGE_FAILED',
          }
          await putRecordingMeta(this.meta)
          this.onStorageFailure?.()
        })
    }
    this.recorder.start(1_000)
  }

  async stop() {
    const recorder = this.recorder
    if (!recorder || recorder.state === 'inactive' || !this.meta)
      return this.meta
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve()
      recorder.stop()
    })
    await this.fragmentWrites
    const current = await getRecordingMeta(this.meta.sessionId)
    if (!current) return null
    if (current.failedReason) {
      this.meta = current
      return current
    }
    const durationMs = Math.max(
      current.durationMs,
      Math.round(performance.now() - this.startedAt),
    )
    const blob = await wholeBlob(current.sessionId, current.contentType)
    const finalized = {
      ...current,
      durationMs,
      totalBytes: blob.size,
      finalized: true,
      finalSha256: await sha256(blob),
    }
    await putRecordingMeta(finalized)
    this.meta = finalized
    return finalized
  }
}

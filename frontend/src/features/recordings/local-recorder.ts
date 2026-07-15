import {
  appendFragment,
  getRecordingMeta,
  putRecordingMeta,
  wholeBlob,
  type RecordingMeta,
} from './local-db'
import { sha256 } from './api'

export class BrowserRecordingUnsupportedError extends Error {}
export class RecordingStreamConflictError extends Error {}
export class RecordingAlreadyFinalizedError extends Error {}
export class RecordingFailedMetaError extends Error {
  constructor(readonly reason: string) {
    super(reason)
  }
}
export class RecordingInterruptedMetaError extends Error {}
export class RecordingLeaseUnavailableError extends Error {}

export type RecordingLeaseAcquirer = (
  sessionId: string,
) => Promise<(() => void) | null>

export async function acquireLocalRecordingLease(
  sessionId: string,
): Promise<(() => void) | null> {
  const manager = typeof navigator === 'undefined' ? undefined : navigator.locks
  if (!manager) throw new RecordingLeaseUnavailableError()
  return new Promise((resolve) => {
    let resolved = false
    const settle = (release: (() => void) | null) => {
      if (resolved) return
      resolved = true
      resolve(release)
    }
    void manager
      .request(
        `goal:local-recording:${sessionId}`,
        { mode: 'exclusive', ifAvailable: true },
        async (lock) => {
          if (!lock) {
            settle(null)
            return
          }
          let release!: () => void
          const held = new Promise<void>((done) => {
            release = done
          })
          let released = false
          settle(() => {
            if (released) return
            released = true
            release()
          })
          await held
        },
      )
      .catch(() => settle(null))
  })
}

export type LocalRecordingRecoveryResult =
  | { status: 'missing' }
  | { status: 'owned_elsewhere' }
  | { status: 'finalized'; meta: RecordingMeta }
  | { status: 'failed'; meta: RecordingMeta }

async function persistRecoveryFailure(meta: RecordingMeta, reason: string) {
  const failed = {
    ...meta,
    failedReason: reason,
    finalized: false,
    finalSha256: null,
    finalizationReady: false,
  }
  try {
    await putRecordingMeta(failed)
  } catch {
    // Return the terminal in-memory state even when IndexedDB remains unavailable.
  }
  return failed
}

/** Finalize fragments left behind after the tab that owned MediaRecorder disappeared. */
export async function recoverLocalRecording(
  sessionId: string,
  acquireLease: RecordingLeaseAcquirer = acquireLocalRecordingLease,
): Promise<LocalRecordingRecoveryResult> {
  let releaseLease: (() => void) | null = null
  let meta: RecordingMeta | null = null
  try {
    releaseLease = await acquireLease(sessionId)
    if (!releaseLease) return { status: 'owned_elsewhere' }
    meta = await getRecordingMeta(sessionId)
    if (!meta) return { status: 'missing' }
    if (meta.failedReason) return { status: 'failed', meta }
    if (meta.finalized) return { status: 'finalized', meta }
    if (!meta.finalizationReady) {
      return {
        status: 'failed',
        meta: await persistRecoveryFailure(meta, 'LOCAL_CAPTURE_INTERRUPTED'),
      }
    }

    const blob = await wholeBlob(meta.sessionId, meta.contentType)
    if (blob.size === 0) {
      return {
        status: 'failed',
        meta: await persistRecoveryFailure(meta, 'EMPTY_RECORDING'),
      }
    }
    if (blob.size !== meta.totalBytes) {
      return {
        status: 'failed',
        meta: await persistRecoveryFailure(meta, 'LOCAL_FINALIZATION_FAILED'),
      }
    }
    const finalized = {
      ...meta,
      totalBytes: blob.size,
      finalized: true,
      finalSha256: await sha256(blob),
    }
    await putRecordingMeta(finalized)
    return { status: 'finalized', meta: finalized }
  } catch (error) {
    if (meta && !meta.finalized && !meta.failedReason) {
      return {
        status: 'failed',
        meta: await persistRecoveryFailure(meta, 'LOCAL_FINALIZATION_FAILED'),
      }
    }
    throw error
  } finally {
    releaseLease?.()
  }
}

export class LocalRecorder {
  private recorder: MediaRecorder | null = null
  private stream: MediaStream | null = null
  private startedAt = 0
  private meta: RecordingMeta | null = null
  private fragmentWrites: Promise<void> = Promise.resolve()
  private startPromise: Promise<void> | null = null
  private stopPromise: Promise<RecordingMeta | null> | null = null
  private recorderStopResolver: (() => void) | null = null
  private stopRequested = false
  private storageFailed = false
  private captureStarted = false
  private releaseLease: (() => void) | null = null
  private durationBaseMs = 0
  private pausedAt = 0
  private accumulatedPausedMs = 0
  private endQuiesced = false

  constructor(
    private readonly onStorageFailure?: () => void,
    private readonly acquireLease: RecordingLeaseAcquirer = acquireLocalRecordingLease,
  ) {}

  start(sessionId: string, stream: MediaStream, clientStreamId: string) {
    this.startPromise ??= this.initialize(sessionId, stream, clientStreamId)
    return this.startPromise
  }

  private async initialize(
    sessionId: string,
    stream: MediaStream,
    clientStreamId: string,
  ) {
    this.stream = stream
    try {
      if (typeof MediaRecorder === 'undefined')
        throw new BrowserRecordingUnsupportedError()
      const contentType = MediaRecorder.isTypeSupported(
        'audio/webm;codecs=opus',
      )
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : null
      if (!contentType) throw new BrowserRecordingUnsupportedError()
      this.releaseLease = await this.acquireLease(sessionId)
      if (!this.releaseLease) throw new RecordingStreamConflictError()
      const existing = await getRecordingMeta(sessionId)
      if (existing?.finalized) throw new RecordingAlreadyFinalizedError()
      if (existing?.failedReason) {
        this.meta = existing
        throw new RecordingFailedMetaError(existing.failedReason)
      }
      if (existing?.finalizationReady) {
        throw new RecordingAlreadyFinalizedError()
      }
      if (existing) {
        this.meta = await persistRecoveryFailure(
          existing,
          'LOCAL_CAPTURE_INTERRUPTED',
        )
        throw new RecordingInterruptedMetaError()
      }
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
        uploadCreateKey: null,
        uploadCompleteKey: null,
        uploadState: 'NOT_STARTED',
        finalizationReady: false,
      }
      this.durationBaseMs = this.meta.durationMs
      await putRecordingMeta(this.meta)
      if (this.stopRequested) return
      this.startedAt = performance.now()
      this.recorder = new MediaRecorder(stream, { mimeType: contentType })
      this.recorder.ondataavailable = (event) => {
        if (!event.data.size) return
        this.fragmentWrites = this.fragmentWrites
          .then(async () => {
            if (!this.meta) return
            this.meta = await appendFragment(
              this.meta,
              event.data,
              this.captureDurationMs(),
            )
          })
          .catch(async () => {
            if (this.storageFailed) return
            this.storageFailed = true
            if (this.meta) {
              this.meta = {
                ...this.meta,
                failedReason: 'LOCAL_STORAGE_FAILED',
              }
              try {
                await putRecordingMeta(this.meta)
              } catch {
                // The recorder still must stop when the failure marker cannot persist.
              }
            }
            this.abortRecording()
            this.onStorageFailure?.()
          })
      }
      this.recorder.start(1_000)
      this.captureStarted = true
    } catch (error) {
      this.releaseRecordingStream()
      this.releaseRecordingLease()
      throw error
    }
  }

  async stop() {
    this.stopRequested = true
    this.stopPromise ??= this.finalizeAfterStart()
    return this.stopPromise
  }

  /** Stop collecting new samples while the end HTTP result is still unknown. */
  async quiesceForEnd() {
    try {
      await this.startPromise
    } catch {
      return
    }
    const recorder = this.recorder
    if (!recorder || this.stopRequested || recorder.state !== 'recording')
      return
    try {
      recorder.requestData()
    } catch {
      // pause still prevents post-end samples when an eager flush is unavailable.
    }
    try {
      this.endQuiesced = true
      recorder.pause()
      this.pausedAt = performance.now()
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
    } catch {
      this.endQuiesced = false
      this.pausedAt = 0
      // Final stop remains available after the end request is accepted.
    }
  }

  /** Resume only when REST confirms that the Session is still LIVE. */
  async resumeAfterEndFailure() {
    const recorder = this.recorder
    if (!recorder || this.stopRequested || !this.endQuiesced) return true
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
    if (recorder.state !== 'paused') {
      await this.interruptCaptureAfterResumeFailure()
      return false
    }
    const now = performance.now()
    try {
      recorder.resume()
      this.endQuiesced = false
      if (this.pausedAt) {
        this.accumulatedPausedMs += Math.max(0, now - this.pausedAt)
        this.pausedAt = 0
      }
      return true
    } catch {
      await this.interruptCaptureAfterResumeFailure()
      return false
    }
  }

  private interruptCaptureAfterResumeFailure() {
    this.stopRequested = true
    this.endQuiesced = false
    this.pausedAt = 0
    this.abortRecording()
    if (!this.stopPromise) {
      this.stopPromise = this.persistInterruptedCaptureFailure()
    }
    return this.stopPromise
  }

  private async persistInterruptedCaptureFailure() {
    await this.fragmentWrites
    return this.recordFailure(
      this.storageFailed ? 'LOCAL_STORAGE_FAILED' : 'LOCAL_CAPTURE_INTERRUPTED',
    )
  }

  private async finalizeAfterStart() {
    try {
      await this.startPromise
    } catch {
      // Preserve the original start error for its caller; still close any meta created.
    }
    return this.finalize()
  }

  private async finalize() {
    try {
      if (this.storageFailed) {
        return this.recordFailure('LOCAL_STORAGE_FAILED')
      }
      if (this.meta?.failedReason) return this.meta
      const recorder = this.recorder
      if (!this.meta) return null
      if (recorder && recorder.state !== 'inactive') {
        await new Promise<void>((resolve) => {
          const settle = () => {
            if (this.recorderStopResolver !== settle) return
            this.recorderStopResolver = null
            resolve()
          }
          this.recorderStopResolver = settle
          recorder.onstop = settle
          try {
            recorder.stop()
          } catch {
            settle()
          }
        })
      }
      await this.fragmentWrites
      if (this.storageFailed) {
        return this.recordFailure('LOCAL_STORAGE_FAILED')
      }
      let current = await getRecordingMeta(this.meta.sessionId)
      if (!current) return null
      if (current.failedReason) {
        this.meta = current
        return current
      }
      current = { ...current, finalizationReady: true }
      await putRecordingMeta(current)
      this.meta = current
      const durationMs = Math.max(current.durationMs, this.captureDurationMs())
      const blob = await wholeBlob(current.sessionId, current.contentType)
      if (blob.size === 0) {
        return this.recordFailure('EMPTY_RECORDING')
      }
      if (blob.size !== current.totalBytes) {
        return this.recordFailure('LOCAL_FINALIZATION_FAILED')
      }
      const finalized = {
        ...current,
        durationMs: this.captureStarted ? durationMs : current.durationMs,
        totalBytes: blob.size,
        finalized: true,
        finalSha256: await sha256(blob),
      }
      await putRecordingMeta(finalized)
      this.meta = finalized
      this.recorder = null
      return finalized
    } catch {
      this.onStorageFailure?.()
      return this.recordFailure('LOCAL_FINALIZATION_FAILED')
    } finally {
      this.releaseRecordingStream()
      this.releaseRecordingLease()
    }
  }

  private async recordFailure(reason: string) {
    if (!this.meta) return null
    const failed = {
      ...this.meta,
      failedReason: reason,
      finalized: false,
      finalSha256: null,
      finalizationReady: false,
    }
    try {
      await putRecordingMeta(failed)
    } catch {
      // Keep the in-memory failure authoritative when IndexedDB stays unavailable.
    }
    this.meta = failed
    return failed
  }

  private releaseRecordingStream() {
    this.stream?.getTracks?.().forEach((track) => track.stop())
    this.stream = null
  }

  private captureDurationMs() {
    if (!this.captureStarted) return this.durationBaseMs
    const now = performance.now()
    const activePauseMs = this.pausedAt ? Math.max(0, now - this.pausedAt) : 0
    return (
      this.durationBaseMs +
      Math.max(
        0,
        Math.round(
          now - this.startedAt - this.accumulatedPausedMs - activePauseMs,
        ),
      )
    )
  }

  private releaseRecordingLease() {
    this.releaseLease?.()
    this.releaseLease = null
  }

  private abortRecording() {
    const recorder = this.recorder
    this.recorder = null
    this.recorderStopResolver?.()
    this.recorderStopResolver = null
    if (recorder) {
      recorder.ondataavailable = null
      recorder.onstop = null
      if (recorder.state !== 'inactive') {
        try {
          recorder.stop()
        } catch {
          // Track release remains authoritative when MediaRecorder races inactive.
        }
      }
    }
    this.releaseRecordingStream()
    this.releaseRecordingLease()
  }
}

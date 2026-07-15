import {
  completeRecordingUpload,
  createRecordingUpload,
  getSessionRecording,
  getRecordingUpload,
  uploadRecordingChunk,
} from './api'
import {
  blobFrom,
  deleteAcknowledgedFragments,
  getRecordingMeta,
  putRecordingMeta,
} from './local-db'

const CHUNK_BYTES = 8 * 1024 * 1024

export type UploadState =
  'idle' | 'uploading' | 'completed' | 'failed' | 'expired' | 'owned_elsewhere'

export class LocalRecordingUploadError extends Error {}
export class RecordingUploadLeaseUnavailableError extends Error {}

export async function acquireRecordingUploadLease(
  sessionId: string,
): Promise<(() => void) | null> {
  const manager = navigator.locks
  if (!manager) throw new RecordingUploadLeaseUnavailableError()
  return new Promise((resolve) => {
    let resolved = false
    const settle = (release: (() => void) | null) => {
      if (resolved) return
      resolved = true
      resolve(release)
    }
    void manager
      .request(
        `goal:recording-upload:${sessionId}`,
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

function errorStatus(error: unknown) {
  return typeof error === 'object' && error && 'status' in error
    ? (error as { status?: number }).status
    : undefined
}

async function canonicalRecordingStatus(sessionId: string) {
  try {
    return (await getSessionRecording(sessionId)).status
  } catch {
    return null
  }
}

async function persistTerminalMeta(
  meta: NonNullable<Awaited<ReturnType<typeof getRecordingMeta>>>,
  uploadState: 'COMPLETED' | 'EXPIRED',
) {
  const terminal = { ...meta, uploadState }
  try {
    await putRecordingMeta(terminal)
  } catch {
    // The canonical REST state still owns the terminal UI for this attempt.
  }
  return terminal
}

export async function uploadLocalRecording(
  sessionId: string,
  onProgress: (state: UploadState, offset?: number) => void,
  acquireLease: (
    sessionId: string,
  ) => Promise<(() => void) | null> = acquireRecordingUploadLease,
) {
  let meta = null as Awaited<ReturnType<typeof getRecordingMeta>>
  let releaseLease: (() => void) | null = null
  try {
    releaseLease = await acquireLease(sessionId)
    if (!releaseLease) {
      onProgress('owned_elsewhere')
      return
    }
    meta = await getRecordingMeta(sessionId)
    if (!meta) throw new LocalRecordingUploadError('LOCAL_RECORDING_MISSING')
    if (meta.uploadState === 'COMPLETED') {
      onProgress('completed', meta.totalBytes)
      return
    }
    if (meta.uploadState === 'EXPIRED') {
      onProgress('expired', meta.acknowledgedOffset)
      return
    }
    if (
      meta.failedReason ||
      !meta.finalized ||
      !meta.finalSha256 ||
      meta.totalBytes < 1
    ) {
      throw new LocalRecordingUploadError('LOCAL_RECORDING_NOT_READY')
    }
    const finalSha256 = meta.finalSha256
    onProgress('uploading', meta.acknowledgedOffset)
    let unavailableRestarted = false
    while (true) {
      try {
        const knownUploadId: string | null = meta.uploadId
        let upload: Awaited<ReturnType<typeof getRecordingUpload>> | null =
          knownUploadId ? await getRecordingUpload(knownUploadId) : null
        if (!upload) {
          const uploadCreateKey: string =
            meta.uploadCreateKey ?? crypto.randomUUID()
          meta = { ...meta, uploadCreateKey }
          await putRecordingMeta(meta)
          upload = await createRecordingUpload(
            sessionId,
            {
              client_stream_id: meta.clientStreamId,
              content_type: meta.contentType,
              total_bytes: meta.totalBytes,
              duration_ms: meta.durationMs,
            },
            uploadCreateKey,
          )
          meta = { ...meta, uploadId: upload.id, uploadState: 'ACTIVE' }
          await putRecordingMeta(meta)
        }
        let offset: number = upload.offset_bytes
        await deleteAcknowledgedFragments(sessionId, offset)
        meta = { ...meta, acknowledgedOffset: offset }
        while (offset < meta.totalBytes) {
          const chunk = await blobFrom(
            sessionId,
            offset,
            Math.min(CHUNK_BYTES, meta.totalBytes - offset),
            meta.contentType,
          )
          if (chunk.size === 0) throw new Error('LOCAL_FRAGMENT_MISSING')
          upload = await uploadRecordingChunk(upload.id, offset, chunk)
          offset = upload.offset_bytes
          await deleteAcknowledgedFragments(sessionId, offset)
          meta = { ...meta, acknowledgedOffset: offset }
          onProgress('uploading', offset)
        }
        const uploadCompleteKey = meta.uploadCompleteKey ?? crypto.randomUUID()
        meta = { ...meta, uploadCompleteKey }
        await putRecordingMeta(meta)
        try {
          await completeRecordingUpload(
            upload.id,
            finalSha256,
            uploadCompleteKey,
          )
        } catch (error) {
          if ((await canonicalRecordingStatus(sessionId)) !== 'UPLOADED')
            throw error
        }
        meta = await persistTerminalMeta(
          {
            ...meta,
            acknowledgedOffset: meta.totalBytes,
          },
          'COMPLETED',
        )
        onProgress('completed', meta.totalBytes)
        return
      } catch (error) {
        const status = errorStatus(error)
        if (status !== 404 && status !== 410) throw error
        const canonicalStatus = await canonicalRecordingStatus(sessionId)
        if (canonicalStatus === 'UPLOADED') {
          meta = await persistTerminalMeta(meta, 'COMPLETED')
          onProgress('completed', meta.totalBytes)
          return
        }
        const canonicalCanRestart =
          canonicalStatus === 'UPLOAD_PENDING' || canonicalStatus === 'FAILED'
        if (canonicalCanRestart && meta.acknowledgedOffset === 0) {
          meta = {
            ...meta,
            uploadId: null,
            uploadCreateKey: null,
            uploadCompleteKey: null,
            uploadState: 'NOT_STARTED',
          }
          await putRecordingMeta(meta)
          if (!unavailableRestarted) {
            unavailableRestarted = true
            continue
          }
          throw new LocalRecordingUploadError('RECORDING_UPLOAD_RESTART_FAILED')
        }
        if (
          meta.acknowledgedOffset > 0 &&
          (status === 410 || canonicalCanRestart)
        ) {
          meta = await persistTerminalMeta(meta, 'EXPIRED')
          onProgress('expired', meta.acknowledgedOffset)
          return
        }
        throw error
      }
    }
  } catch (error) {
    onProgress('failed')
    throw error
  } finally {
    releaseLease?.()
  }
}

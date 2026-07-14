import {
  completeRecordingUpload,
  createRecordingUpload,
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
  'idle' | 'uploading' | 'completed' | 'failed' | 'expired'

export async function uploadLocalRecording(
  sessionId: string,
  onProgress: (state: UploadState, offset?: number) => void,
) {
  let meta = await getRecordingMeta(sessionId)
  if (!meta?.finalized || !meta.finalSha256) return
  const finalSha256 = meta.finalSha256
  onProgress('uploading', meta.acknowledgedOffset)
  try {
    const knownUploadId = meta.uploadId
    let upload = knownUploadId
      ? await getRecordingUpload(knownUploadId)
      : await createRecordingUpload(sessionId, {
          client_stream_id: meta.clientStreamId,
          content_type: meta.contentType,
          total_bytes: meta.totalBytes,
          duration_ms: meta.durationMs,
        })
    if (!meta.uploadId) {
      meta = { ...meta, uploadId: upload.id }
      await putRecordingMeta(meta)
    }
    let offset = upload.offset_bytes
    await deleteAcknowledgedFragments(sessionId, offset)
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
      onProgress('uploading', offset)
    }
    await completeRecordingUpload(upload.id, finalSha256)
    onProgress('completed', meta.totalBytes)
  } catch (error) {
    const status =
      typeof error === 'object' && error && 'status' in error
        ? (error as { status?: number }).status
        : undefined
    onProgress(status === 410 ? 'expired' : 'failed')
    throw error
  }
}

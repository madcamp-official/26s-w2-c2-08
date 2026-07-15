import type { components } from '../../api/generated/schema'
import { apiClient, apiUrl } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type SessionRecording = components['schemas']['SessionRecording']
export type RecordingUpload = components['schemas']['RecordingUpload']

function headers(key: string) {
  return { 'Idempotency-Key': key }
}

async function result<T>(
  request: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  empty: string,
): Promise<T> {
  try {
    const { data, error, response } = await request()
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error(empty)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export function getSessionRecording(sessionId: string, signal?: AbortSignal) {
  return result(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/recording', {
        params: { path: { session_id: sessionId } },
        signal,
      }),
    '녹음 메타데이터가 비어 있습니다.',
  )
}

export async function abandonRecordingUpload(sessionId: string) {
  try {
    const { error, response } = await apiClient.POST(
      '/api/v1/sessions/{session_id}/recording/abandon-upload',
      { params: { path: { session_id: sessionId } } },
    )
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function verifyRecordingPlayback(
  playbackUrl: string,
  signal?: AbortSignal,
) {
  try {
    const response = await fetch(apiUrl(playbackUrl), {
      credentials: 'include',
      headers: { Range: 'bytes=0-0' },
      signal,
    })
    if (!response.ok) {
      const payload = await response
        .clone()
        .json()
        .catch(() => null)
      throw apiErrorFromResponse(response, payload)
    }
    await response.body?.cancel()
    return { allowed: true as const }
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function deleteSessionRecording(
  sessionId: string,
  idempotencyKey: string,
) {
  try {
    const { error, response } = await apiClient.DELETE(
      '/api/v1/sessions/{session_id}/recording',
      {
        params: {
          path: { session_id: sessionId },
          header: headers(idempotencyKey),
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export function createRecordingUpload(
  sessionId: string,
  input: components['schemas']['RecordingUploadCreateRequest'],
  idempotencyKey: string,
) {
  return result(
    () =>
      apiClient.POST('/api/v1/sessions/{session_id}/recording/uploads', {
        params: {
          path: { session_id: sessionId },
          header: headers(idempotencyKey),
        },
        body: input,
      }),
    '녹음 upload 응답이 비어 있습니다.',
  )
}

export function getRecordingUpload(uploadId: string) {
  return result(
    () =>
      apiClient.GET('/api/v1/recording-uploads/{upload_id}', {
        params: { path: { upload_id: uploadId } },
      }),
    '녹음 upload 상태가 비어 있습니다.',
  )
}

export async function uploadRecordingChunk(
  uploadId: string,
  offset: number,
  blob: Blob,
): Promise<RecordingUpload> {
  const checksum = await sha256(blob)
  const response = await fetch(
    apiUrl(`/api/v1/recording-uploads/${encodeURIComponent(uploadId)}`),
    {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/octet-stream',
        'Upload-Offset': String(offset),
        'X-Chunk-SHA256': checksum,
      },
      body: blob,
    },
  )
  if (!response.ok) throw await responseError(response)
  return (await response.json()) as RecordingUpload
}

export function completeRecordingUpload(
  uploadId: string,
  sha256: string,
  idempotencyKey: string,
) {
  return result(
    () =>
      apiClient.POST('/api/v1/recording-uploads/{upload_id}/complete', {
        params: {
          path: { upload_id: uploadId },
          header: headers(idempotencyKey),
        },
        body: { sha256 },
      }),
    '녹음 완료 응답이 비어 있습니다.',
  )
}

async function responseError(response: Response) {
  const payload = await response.json().catch(() => null)
  return apiErrorFromResponse(response, payload)
}

export async function sha256(blob: Blob) {
  const bytes = await blob.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type SessionRecord = components['schemas']['SessionRecord']
export type TranscriptTimelinePage =
  components['schemas']['TranscriptTimelinePage']
export type LectureSummary = components['schemas']['LectureSummary']

async function request<T>(
  call: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  emptyMessage: string,
): Promise<T> {
  try {
    const { data, error, response } = await call()
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error(emptyMessage)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/** Compact record manifest. Large collections are intentionally loaded elsewhere. */
export function getSessionRecord(sessionId: string, signal?: AbortSignal) {
  return request<SessionRecord>(async () => {
    const response = await apiClient.GET(
      '/api/v1/sessions/{session_id}/record',
      {
        params: { path: { session_id: sessionId } },
        signal,
      },
    )
    // The generated operation response expands OpenAPI's conditional
    // Transcript index while the component schema keeps it as a union.
    // Both represent the same `/record` contract.
    return response as unknown as {
      data?: SessionRecord
      error?: unknown
      response: Response
    }
  }, '수업 기록 manifest 응답이 비어 있습니다.')
}

export function getRecordTranscriptTimeline(
  sessionId: string,
  transcriptVersionId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/transcript', {
        params: {
          path: { session_id: sessionId },
          query: {
            transcript_version_id: transcriptVersionId,
            cursor: cursor ?? undefined,
            limit: 100,
          },
        },
        signal,
      }),
    'Transcript 타임라인 응답이 비어 있습니다.',
  )
}

export function listFinalSummaries(sessionId: string, signal?: AbortSignal) {
  return request(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/summaries', {
        params: {
          path: { session_id: sessionId },
          query: { summary_type: 'FINAL', limit: 20 },
        },
        signal,
      }),
    '최종 요약 목록 응답이 비어 있습니다.',
  )
}

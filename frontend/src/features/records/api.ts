import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type SessionRecord = components['schemas']['SessionRecord']
export type TranscriptTimelinePage =
  components['schemas']['TranscriptTimelinePage']
export type LectureSummary = components['schemas']['LectureSummary']
export type QuestionListResponse = components['schemas']['QuestionListResponse']
export type QuestionClusterListResponse =
  components['schemas']['QuestionClusterListResponse']
export type QuestionClusterMemberListResponse =
  components['schemas']['QuestionClusterMemberListResponse']
export type AnswerListResponse = components['schemas']['AnswerListResponse']
export type AIJobListResponse = components['schemas']['AIJobListResponse']
export type AIJobAcceptedResponse =
  components['schemas']['AIJobAcceptedResponse']
export type AIJob = components['schemas']['AIJob']

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

export function listRecordQuestions(
  sessionId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request<QuestionListResponse>(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/questions', {
        params: {
          path: { session_id: sessionId },
          query: { sort: 'RECENT', cursor: cursor ?? undefined, limit: 20 },
        },
        signal,
      }),
    '질문 목록 응답이 비어 있습니다.',
  )
}

export function listOpenRecordQuestions(
  sessionId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request<QuestionListResponse>(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/questions', {
        params: {
          path: { session_id: sessionId },
          query: {
            status: 'OPEN',
            sort: 'RECENT',
            cursor: cursor ?? undefined,
            limit: 20,
          },
        },
        signal,
      }),
    '미답변 질문 목록 응답이 비어 있습니다.',
  )
}

export function listRecordAnswers(
  sessionId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request<AnswerListResponse>(async () => {
    const response = await apiClient.GET(
      '/api/v1/sessions/{session_id}/answers',
      {
        params: {
          path: { session_id: sessionId },
          query: { cursor: cursor ?? undefined, limit: 20 },
        },
        signal,
      },
    )
    return response as unknown as {
      data?: AnswerListResponse
      error?: unknown
      response: Response
    }
  }, 'Answer 목록 응답이 비어 있습니다.')
}

export function listFinalQuestionClusters(
  sessionId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request<QuestionClusterListResponse>(async () => {
    const response = await apiClient.GET(
      '/api/v1/sessions/{session_id}/question-clusters',
      {
        params: {
          path: { session_id: sessionId },
          query: { scope: 'FINAL', cursor: cursor ?? undefined, limit: 20 },
        },
        signal,
      },
    )
    return response as unknown as {
      data?: QuestionClusterListResponse
      error?: unknown
      response: Response
    }
  }, '최종 질문 분류 목록 응답이 비어 있습니다.')
}

export function listFinalQuestionClusterMembers(
  sessionId: string,
  clusterId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request<QuestionClusterMemberListResponse>(
    () =>
      apiClient.GET(
        '/api/v1/sessions/{session_id}/question-clusters/{cluster_id}/members',
        {
          params: {
            path: { session_id: sessionId, cluster_id: clusterId },
            query: { cursor: cursor ?? undefined, limit: 20 },
          },
          signal,
        },
      ),
    'Cluster 질문 목록 응답이 비어 있습니다.',
  )
}

export function listRecordJobs(
  sessionId: string,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  return request<AIJobListResponse>(async () => {
    const response = await apiClient.GET('/api/v1/sessions/{session_id}/jobs', {
      params: {
        path: { session_id: sessionId },
        query: { cursor: cursor ?? undefined, limit: 20 },
      },
      signal,
    })
    return response as unknown as {
      data?: AIJobListResponse
      error?: unknown
      response: Response
    }
  }, '공용 작업 목록 응답이 비어 있습니다.')
}

export function retryRecordJob(jobId: string, idempotencyKey: string) {
  return request<AIJobAcceptedResponse>(async () => {
    const response = await apiClient.POST('/api/v1/jobs/{job_id}/retry', {
      params: {
        path: { job_id: jobId },
        header: { 'Idempotency-Key': idempotencyKey },
      },
    })
    return response as unknown as {
      data?: AIJobAcceptedResponse
      error?: unknown
      response: Response
    }
  }, '작업 재시도 응답이 비어 있습니다.')
}

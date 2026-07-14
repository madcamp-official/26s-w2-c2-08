import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type AIJob = components['schemas']['AIJob']
export type LectureSummary = components['schemas']['LectureSummary']
export type SummaryList = components['schemas']['SummaryListResponse']
export type Chat = components['schemas']['Chat']
export type ChatMessage = components['schemas']['ChatMessage']

function headers(key: string) {
  return { 'Idempotency-Key': key }
}

async function request<T>(
  call: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  message: string,
): Promise<T> {
  try {
    const { data, error, response } = await call()
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error(message)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export function listSummaries(sessionId: string, signal?: AbortSignal) {
  return request(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/summaries', {
        params: {
          path: { session_id: sessionId },
          query: { summary_type: 'LIVE', limit: 20 },
        },
        signal,
      }),
    '요약 목록 응답이 비어 있습니다.',
  )
}

export function requestLiveSummary(sessionId: string, idempotencyKey: string) {
  return request(
    () =>
      apiClient.POST('/api/v1/sessions/{session_id}/summaries', {
        params: {
          path: { session_id: sessionId },
          header: headers(idempotencyKey),
        },
        body: { summary_type: 'LIVE', range: null },
      }),
    '요약 작업 응답이 비어 있습니다.',
  )
}

export function getJob(jobId: string, signal?: AbortSignal) {
  return request(
    () =>
      apiClient.GET('/api/v1/jobs/{job_id}', {
        params: { path: { job_id: jobId } },
        signal,
      }),
    '작업 상태 응답이 비어 있습니다.',
  )
}

export function retryJob(jobId: string, idempotencyKey: string) {
  return request(
    () =>
      apiClient.POST('/api/v1/jobs/{job_id}/retry', {
        params: { path: { job_id: jobId }, header: headers(idempotencyKey) },
      }),
    '재시도 작업 응답이 비어 있습니다.',
  )
}

export function listChats(sessionId: string, signal?: AbortSignal) {
  return request(
    () =>
      apiClient.GET('/api/v1/sessions/{session_id}/chats', {
        params: { path: { session_id: sessionId }, query: { limit: 20 } },
        signal,
      }),
    '대화 목록 응답이 비어 있습니다.',
  )
}

export function createChat(
  sessionId: string,
  mode: 'LIVE' | 'REVIEW',
  idempotencyKey: string,
) {
  return request(
    () =>
      apiClient.POST('/api/v1/sessions/{session_id}/chats', {
        params: {
          path: { session_id: sessionId },
          header: headers(idempotencyKey),
        },
        body: { mode },
      }),
    '대화 생성 응답이 비어 있습니다.',
  )
}

export function listMessages(chatId: string, signal?: AbortSignal) {
  return request(
    () =>
      apiClient.GET('/api/v1/chats/{chat_id}/messages', {
        params: { path: { chat_id: chatId }, query: { limit: 100 } },
        signal,
      }),
    '대화 메시지 응답이 비어 있습니다.',
  )
}

export function sendMessage(
  chatId: string,
  content: string,
  idempotencyKey: string,
) {
  return request(
    () =>
      apiClient.POST('/api/v1/chats/{chat_id}/messages', {
        params: { path: { chat_id: chatId }, header: headers(idempotencyKey) },
        body: { content },
      }),
    '대화 요청 응답이 비어 있습니다.',
  )
}

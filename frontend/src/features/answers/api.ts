import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type Answer = components['schemas']['Answer']
export type AnswerListResponse = components['schemas']['AnswerListResponse']
export type AnswerTarget = components['schemas']['AnswerTarget']

export async function listSessionAnswers(
  sessionId: string,
  signal?: AbortSignal,
): Promise<AnswerListResponse> {
  try {
    const items: Answer[] = []
    const seenCursors = new Set<string>()
    let cursor: string | null = null
    do {
      const result = await apiClient.GET(
        '/api/v1/sessions/{session_id}/answers',
        {
          params: {
            path: { session_id: sessionId },
            query: { cursor: cursor ?? undefined, limit: 100 },
          },
          signal,
        },
      )
      const data = result.data as unknown as AnswerListResponse | undefined
      const { error, response } = result
      if (error) throw apiErrorFromResponse(response, error)
      if (!data) throw new Error('Answer 목록 응답이 비어 있습니다.')
      items.push(...(data.items as unknown as Answer[]))
      cursor = data.next_cursor
      if (cursor) {
        if (seenCursors.has(cursor)) {
          throw new Error('Answer cursor가 반복되어 복구를 중단했습니다.')
        }
        seenCursors.add(cursor)
      }
    } while (cursor)
    return { items, next_cursor: null }
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function createVoiceAnswer(
  sessionId: string,
  target: AnswerTarget,
  idempotencyKey: string,
): Promise<Answer> {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/sessions/{session_id}/answers',
      {
        params: {
          path: { session_id: sessionId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: { answer_type: 'VOICE', target },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('음성 Answer 생성 응답이 비어 있습니다.')
    return data as unknown as Answer
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function createTextAnswer(
  sessionId: string,
  questionId: string,
  textContent: string,
  idempotencyKey: string,
): Promise<Answer> {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/sessions/{session_id}/answers',
      {
        params: {
          path: { session_id: sessionId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: {
          answer_type: 'TEXT',
          target: { type: 'STUDENT_QUESTION', question_id: questionId },
          text_content: textContent,
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('텍스트 Answer 생성 응답이 비어 있습니다.')
    return data as unknown as Answer
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function completeVoiceAnswer(
  answerId: string,
  idempotencyKey: string,
): Promise<Answer> {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/answers/{answer_id}/complete',
      {
        params: {
          path: { answer_id: answerId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('Answer 완료 응답이 비어 있습니다.')
    return data as unknown as Answer
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function cancelVoiceAnswer(
  answerId: string,
  idempotencyKey: string,
): Promise<void> {
  try {
    const { error, response } = await apiClient.POST(
      '/api/v1/answers/{answer_id}/cancel',
      {
        params: {
          path: { answer_id: answerId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function updateAnswerText(
  answerId: string,
  textContent: string,
  expectedVersion: number,
): Promise<Answer> {
  try {
    const { data, error, response } = await apiClient.PATCH(
      '/api/v1/answers/{answer_id}',
      {
        params: { path: { answer_id: answerId } },
        body: { text_content: textContent, expected_version: expectedVersion },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('Answer 텍스트 수정 응답이 비어 있습니다.')
    return data as unknown as Answer
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function withdrawAnswerText(
  answerId: string,
  idempotencyKey: string,
): Promise<void> {
  try {
    const { error, response } = await apiClient.DELETE(
      '/api/v1/answers/{answer_id}/text',
      {
        params: {
          path: { answer_id: answerId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

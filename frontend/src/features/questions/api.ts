import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type Question = components['schemas']['Question']
export type QuestionListResponse = components['schemas']['QuestionListResponse']
export type QuestionCreateResponse =
  components['schemas']['QuestionCreateResponse']
export type QuestionReactionState =
  components['schemas']['QuestionReactionState']
export type QuestionSort = components['schemas']['QuestionSort']

interface ListQuestionsInput {
  sessionId: string
  sort: QuestionSort
  cursor?: string | null
  limit?: number
  signal?: AbortSignal
}

export async function listSessionQuestions({
  sessionId,
  sort,
  cursor,
  limit = 20,
  signal,
}: ListQuestionsInput): Promise<QuestionListResponse> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/sessions/{session_id}/questions',
      {
        params: {
          path: { session_id: sessionId },
          query: { status: 'OPEN', sort, cursor: cursor ?? undefined, limit },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('질문 목록 응답이 비어 있습니다.')
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function createQuestion(
  sessionId: string,
  content: string,
  idempotencyKey: string,
): Promise<QuestionCreateResponse> {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/sessions/{session_id}/questions',
      {
        params: {
          path: { session_id: sessionId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: { content },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('질문 생성 응답이 비어 있습니다.')
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function addQuestionReaction(
  questionId: string,
): Promise<QuestionReactionState> {
  try {
    const { data, error, response } = await apiClient.PUT(
      '/api/v1/questions/{question_id}/reaction',
      { params: { path: { question_id: questionId } } },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('반응 추가 응답이 비어 있습니다.')
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function removeQuestionReaction(
  questionId: string,
): Promise<void> {
  try {
    const { error, response } = await apiClient.DELETE(
      '/api/v1/questions/{question_id}/reaction',
      { params: { path: { question_id: questionId } } },
    )
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

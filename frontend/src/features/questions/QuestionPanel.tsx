import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import {
  addQuestionReaction,
  createQuestion,
  listSessionQuestions,
  removeQuestionReaction,
  suggestQuestionDrafts,
  type Question,
} from './api'
import { questionKeys } from './queries'

const MAX_QUESTION_LENGTH = 300
const MAX_QUESTION_DRAFT_LENGTH = 500

interface QuestionPanelProps {
  sessionId: string
  student: boolean
}

function normalizedLength(value: string) {
  return Array.from(value.trim().normalize('NFC')).length
}

function questionErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'SELF_REACTION_FORBIDDEN') {
      return '내가 작성한 질문에는 반응할 수 없습니다.'
    }
    if (error.code === 'SESSION_STATE_CONFLICT') {
      return '수업이 진행 중일 때만 질문과 반응을 변경할 수 있습니다.'
    }
    if (error.code === 'AI_PROVIDER_UNAVAILABLE') {
      return 'AI 질문 작성 도움을 지금 사용할 수 없습니다. 초안은 그대로 유지됩니다.'
    }
    return error.message
  }
  return '요청을 처리하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

export function QuestionPanel({ sessionId, student }: QuestionPanelProps) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [content, setContent] = useState('')
  const [draft, setDraft] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [selectedSuggestion, setSelectedSuggestion] = useState<string | null>(
    null,
  )
  const [draftHelpError, setDraftHelpError] = useState<string | null>(null)
  const [interactionError, setInteractionError] = useState<string | null>(null)
  const contentLength = normalizedLength(content)
  const draftLength = normalizedLength(draft)
  const questions = useInfiniteQuery({
    queryKey: questionKeys.list(sessionId, 'POPULAR'),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listSessionQuestions({
        sessionId,
        sort: 'POPULAR',
        cursor: pageParam,
        signal,
      }),
    getNextPageParam: (page) => page.next_cursor,
  })

  function refresh() {
    void queryClient.invalidateQueries({
      queryKey: questionKeys.session(sessionId),
    })
  }

  const create = useMutation({
    mutationFn: () => createQuestion(sessionId, content, crypto.randomUUID()),
    onSuccess: () => {
      setContent('')
      setInteractionError(null)
      refresh()
      showToast({ tone: 'success', message: '익명 질문을 등록했습니다.' })
    },
    onError: (error) => setInteractionError(questionErrorMessage(error)),
  })
  const draftHelp = useMutation({
    mutationFn: () => suggestQuestionDrafts(sessionId, draft),
    onMutate: () => {
      setDraftHelpError(null)
      setSuggestions([])
      setSelectedSuggestion(null)
    },
    onSuccess: (response) => {
      setSuggestions(response.suggestions)
    },
    onError: (error) => setDraftHelpError(questionErrorMessage(error)),
  })
  const react = useMutation({
    mutationFn: async ({
      question,
      add,
    }: {
      question: Question
      add: boolean
    }) => {
      if (add) await addQuestionReaction(question.id)
      else await removeQuestionReaction(question.id)
    },
    onSuccess: () => {
      setInteractionError(null)
      refresh()
    },
    onError: (error) => setInteractionError(questionErrorMessage(error)),
  })

  const items = questions.data?.pages.flatMap((page) => page.items) ?? []
  const canSubmit = contentLength >= 1 && contentLength <= MAX_QUESTION_LENGTH
  const canRequestDraftHelp =
    draftLength >= 1 && draftLength <= MAX_QUESTION_DRAFT_LENGTH

  return (
    <section className="panel question-panel" aria-labelledby="question-title">
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Live questions</p>
          <h2 id="question-title">익명 질문</h2>
          <p>
            다른 수강생에게 작성자는 공개되지 않으며, 같은 질문도 각각
            등록됩니다.
          </p>
        </div>
        <span className="input-hint">공감 많은 순</span>
      </header>

      {student && (
        <>
          <form
            className="question-draft-helper"
            onSubmit={(event) => {
              event.preventDefault()
              if (canRequestDraftHelp && !draftHelp.isPending) {
                draftHelp.mutate()
              }
            }}
          >
            <div>
              <label htmlFor="question-draft">AI 질문 작성 도움</label>
              <p className="input-hint">
                이해가 안 되는 내용을 편하게 적으면 질문 후보를 만들어 드립니다.
              </p>
            </div>
            <textarea
              id="question-draft"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="예: 음수 가중치가 있으면 왜 이 알고리즘을 쓰면 안 되나요?"
              rows={3}
            />
            <div className="question-composer__footer">
              <span
                className={
                  draftLength > MAX_QUESTION_DRAFT_LENGTH
                    ? 'form-error'
                    : 'input-hint'
                }
              >
                {draftLength}/{MAX_QUESTION_DRAFT_LENGTH}
              </span>
              <Button
                type="submit"
                variant="secondary"
                disabled={!canRequestDraftHelp || draftHelp.isPending}
              >
                {draftHelp.isPending ? '다듬는 중…' : 'AI에게 질문 다듬기'}
              </Button>
            </div>
            {draftHelpError && (
              <p className="form-error" role="alert">
                {draftHelpError}
              </p>
            )}
            {suggestions.length > 0 && (
              <fieldset className="question-draft-helper__suggestions">
                <legend>질문 후보를 선택하세요</legend>
                <p className="input-hint">
                  선택한 뒤 아래 질문 입력칸에서 다시 수정할 수 있습니다.
                </p>
                {suggestions.map((suggestion, index) => {
                  const id = `question-suggestion-${index}`
                  return (
                    <label key={id} htmlFor={id}>
                      <input
                        id={id}
                        type="radio"
                        name="question-suggestion"
                        checked={selectedSuggestion === suggestion}
                        onChange={() => {
                          setSelectedSuggestion(suggestion)
                          setContent(suggestion)
                        }}
                      />
                      <span>{suggestion}</span>
                    </label>
                  )
                })}
              </fieldset>
            )}
          </form>

          <form
            className="question-composer"
            onSubmit={(event) => {
              event.preventDefault()
              if (canSubmit && !create.isPending) create.mutate()
            }}
          >
            <label htmlFor="question-content">질문 작성</label>
            <textarea
              id="question-content"
              value={content}
              maxLength={MAX_QUESTION_LENGTH + 1}
              onChange={(event) => setContent(event.target.value)}
              placeholder="지금 이해가 안 되는 내용을 남겨 보세요."
              rows={3}
            />
            <div className="question-composer__footer">
              <span
                className={
                  contentLength > MAX_QUESTION_LENGTH
                    ? 'form-error'
                    : 'input-hint'
                }
              >
                {contentLength}/{MAX_QUESTION_LENGTH}
              </span>
              <Button type="submit" disabled={!canSubmit || create.isPending}>
                {create.isPending ? '등록 중…' : '익명 질문 등록'}
              </Button>
            </div>
          </form>
        </>
      )}

      {interactionError && (
        <p className="form-error" role="alert">
          {interactionError}
        </p>
      )}
      {questions.isPending && (
        <StatePanel kind="loading" title="질문을 불러오는 중" />
      )}
      {questions.isError && (
        <StatePanel kind="error" title="질문을 불러오지 못했습니다" />
      )}
      {questions.data && items.length === 0 && (
        <StatePanel
          kind="empty"
          title="아직 등록된 질문이 없습니다"
          description={
            student
              ? '첫 질문을 익명으로 남겨 보세요.'
              : '학생 질문이 등록되면 이곳에 표시됩니다.'
          }
        />
      )}
      {items.length > 0 && (
        <>
          <ol className="question-list" aria-label="수업 질문 목록">
            {items.map((question) => (
              <li key={question.id}>
                <p>{question.content}</p>
                <div className="question-list__meta">
                  <span>공감 {question.reaction_count}</span>
                  {student && (
                    <Button
                      variant={question.reacted_by_me ? 'secondary' : 'ghost'}
                      aria-pressed={question.reacted_by_me}
                      disabled={react.isPending}
                      onClick={() =>
                        react.mutate({ question, add: !question.reacted_by_me })
                      }
                    >
                      {question.reacted_by_me ? '공감 취소' : '나도 궁금해요'}
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ol>
          {questions.hasNextPage && (
            <Button
              variant="ghost"
              disabled={questions.isFetchingNextPage}
              onClick={() => void questions.fetchNextPage()}
            >
              {questions.isFetchingNextPage
                ? '더 불러오는 중…'
                : '질문 더 보기'}
            </Button>
          )}
        </>
      )}
    </section>
  )
}

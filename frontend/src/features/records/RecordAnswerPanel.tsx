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
  createTextAnswer,
  updateAnswerText,
  withdrawAnswerText,
  type Answer,
} from '../answers/api'
import { listOpenRecordQuestions, listRecordAnswers } from './api'
import { recordKeys } from './queries'

const MAX_ANSWER_TEXT_LENGTH = 2000

function normalizedLength(value: string) {
  return Array.from(value.trim().normalize('NFC')).length
}

function answerErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'ANSWER_VERSION_CONFLICT') {
      return '다른 변경이 먼저 저장되었습니다. 작성 중인 내용은 그대로 유지합니다.'
    }
    return error.message
  }
  return '요청을 처리하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

function answerTargetLabel(answer: Answer) {
  return answer.target.type === 'STUDENT_QUESTION' ? '학생 질문' : 'AI 대표질문'
}

function organizationCopy(answer: Answer) {
  const state = answer.organization_state
  if (state.status === 'SUCCEEDED' && state.organization) {
    return {
      tone: 'result' as const,
      content: state.organization.content,
      detail: `AI 정리 · 원본 Transcript ${state.organization.start_sequence}–${state.organization.end_sequence} 구간`,
    }
  }
  if (state.status === 'PENDING' || state.status === 'RUNNING') {
    return {
      tone: 'pending' as const,
      content: 'AI가 음성 Answer를 정리하고 있습니다.',
      detail: state.attempt ? `${state.attempt}번째 시도` : '처리 중',
    }
  }
  if (state.status === 'FAILED') {
    return {
      tone: 'failed' as const,
      content:
        'AI 답변 정리를 완료하지 못했습니다. 원본 Answer와 교수자 설명은 그대로 유지합니다.',
      detail: state.attempt ? `${state.attempt}번째 시도 실패` : '정리 실패',
    }
  }
  if (state.status === 'WAITING_SOURCE') {
    return {
      tone: 'pending' as const,
      content: '확정 Transcript가 준비되면 음성 Answer를 정리합니다.',
      detail: 'Transcript 대기 중',
    }
  }
  if (state.status === 'DATA_INTEGRITY_ERROR') {
    return {
      tone: 'failed' as const,
      content:
        '답변 정리 상태를 확인할 수 없습니다. 원본 Answer와 교수자 설명은 그대로 유지합니다.',
      detail: '정리 상태 확인 필요',
    }
  }
  return null
}

function mappingCopy(answer: Answer) {
  if (answer.answer_type !== 'VOICE') return null
  const mapping = answer.canonical_transcript_mapping
  if (!mapping) return '원본 LIVE Transcript 구간을 유지합니다.'
  if (mapping.status === 'SUCCEEDED')
    return '확정 Transcript 구간에 연결되었습니다.'
  if (mapping.status === 'PENDING')
    return '확정 Transcript 구간을 연결하고 있습니다.'
  return '확정 Transcript 구간을 연결하지 못했습니다. 원본 범위를 유지합니다.'
}

export interface TranscriptFocusTarget {
  endSegmentId?: string
  endSequence?: number
  source: 'CANONICAL' | 'ORIGINAL'
  startSegmentId?: string
  startSequence?: number
  versionId: string
}

function transcriptFocusTarget(answer: Answer): TranscriptFocusTarget | null {
  if (answer.answer_type !== 'VOICE') return null
  const mapping = answer.canonical_transcript_mapping
  if (
    mapping?.status === 'SUCCEEDED' &&
    mapping.target_transcript_version_id &&
    mapping.start_segment_id &&
    mapping.end_segment_id
  ) {
    return {
      endSegmentId: mapping.end_segment_id,
      source: 'CANONICAL',
      startSegmentId: mapping.start_segment_id,
      versionId: mapping.target_transcript_version_id,
    }
  }
  if (
    answer.source_transcript_version_id &&
    answer.start_sequence !== null &&
    answer.end_sequence !== null
  ) {
    return {
      endSequence: answer.end_sequence,
      source: 'ORIGINAL',
      startSequence: answer.start_sequence,
      versionId: answer.source_transcript_version_id,
    }
  }
  return null
}

export function RecordAnswerPanel({
  sessionId,
  professor,
  sessionStatus,
  onFocusTranscript,
}: {
  sessionId: string
  professor: boolean
  sessionStatus: 'PROCESSING' | 'COMPLETED'
  onFocusTranscript: (target: TranscriptFocusTarget) => void
}) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [editing, setEditing] = useState<Answer | null>(null)
  const [draft, setDraft] = useState('')
  const [selectedQuestionId, setSelectedQuestionId] = useState('')
  const [newText, setNewText] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const editable = professor && sessionStatus === 'COMPLETED'
  const answers = useInfiniteQuery({
    queryKey: recordKeys.answers(sessionId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listRecordAnswers(sessionId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor,
    refetchInterval: sessionStatus === 'PROCESSING' ? 3_000 : false,
  })
  const openQuestions = useInfiniteQuery({
    queryKey: recordKeys.openQuestions(sessionId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listOpenRecordQuestions(sessionId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor,
    enabled: editable,
  })
  const items = answers.data?.pages.flatMap((page) => page.items) ?? []
  const unansweredQuestions =
    openQuestions.data?.pages.flatMap((page) => page.items) ?? []

  function refresh() {
    void queryClient.invalidateQueries({
      queryKey: recordKeys.answers(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: recordKeys.questions(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: recordKeys.openQuestions(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: recordKeys.manifest(sessionId),
    })
  }

  const createText = useMutation({
    mutationFn: () =>
      createTextAnswer(
        sessionId,
        selectedQuestionId,
        newText,
        crypto.randomUUID(),
      ),
    onSuccess: () => {
      setNewText('')
      setSelectedQuestionId('')
      setErrorMessage(null)
      refresh()
      showToast({ tone: 'success', message: '텍스트 Answer를 등록했습니다.' })
    },
    onError: (error) => setErrorMessage(answerErrorMessage(error)),
  })
  const updateText = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error('수정할 Answer가 없습니다.')
      return updateAnswerText(editing.id, draft, editing.version)
    },
    onSuccess: () => {
      setEditing(null)
      setDraft('')
      setErrorMessage(null)
      refresh()
      showToast({ tone: 'success', message: '교수자 텍스트를 저장했습니다.' })
    },
    onError: (error) => setErrorMessage(answerErrorMessage(error)),
  })
  const withdraw = useMutation({
    mutationFn: (answerId: string) =>
      withdrawAnswerText(answerId, crypto.randomUUID()),
    onSuccess: () => {
      setEditing(null)
      setDraft('')
      setErrorMessage(null)
      refresh()
      showToast({ tone: 'success', message: '교수자 텍스트를 철회했습니다.' })
    },
    onError: (error) => setErrorMessage(answerErrorMessage(error)),
  })

  const newTextLength = normalizedLength(newText)
  const draftLength = normalizedLength(draft)
  const canCreateText =
    selectedQuestionId.length > 0 &&
    newTextLength >= 1 &&
    newTextLength <= MAX_ANSWER_TEXT_LENGTH
  const canSaveText = draftLength >= 1 && draftLength <= MAX_ANSWER_TEXT_LENGTH

  return (
    <section
      className="panel record-answers"
      aria-labelledby="record-answers-title"
    >
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Professor answers</p>
          <h2 id="record-answers-title">교수자 답변</h2>
          <p>
            음성 Answer의 원본 범위와 확정 Transcript 연결 상태를 함께
            보관합니다.
          </p>
        </div>
        {answers.data && <span className="input-hint">{items.length}개</span>}
      </header>

      {errorMessage && (
        <p className="form-error" role="alert">
          {errorMessage}
        </p>
      )}

      {editable && (
        <form
          className="answer-text-composer"
          onSubmit={(event) => {
            event.preventDefault()
            if (canCreateText && !createText.isPending) createText.mutate()
          }}
        >
          <label htmlFor="record-answer-question-target">
            미답변 학생 질문에 텍스트 답변
          </label>
          <select
            id="record-answer-question-target"
            value={selectedQuestionId}
            onChange={(event) => setSelectedQuestionId(event.target.value)}
          >
            <option value="">질문을 선택하세요</option>
            {unansweredQuestions.map((question) => (
              <option key={question.id} value={question.id}>
                {question.content}
              </option>
            ))}
          </select>
          {openQuestions.isPending && (
            <p className="input-hint" role="status">
              미답변 질문을 불러오는 중…
            </p>
          )}
          {openQuestions.isError && !openQuestions.isFetchNextPageError && (
            <StatePanel
              kind="error"
              title="미답변 질문을 불러오지 못했습니다"
              actionLabel="미답변 질문 다시 불러오기"
              onAction={() => void openQuestions.refetch()}
            />
          )}
          {openQuestions.data && unansweredQuestions.length === 0 && (
            <p className="input-hint">답변을 추가할 미답변 질문이 없습니다.</p>
          )}
          {openQuestions.isFetchNextPageError && (
            <StatePanel
              kind="error"
              title="다음 미답변 질문을 불러오지 못했습니다"
              description="이미 불러온 질문은 유지합니다."
              actionLabel="다음 미답변 질문 다시 시도"
              onAction={() => void openQuestions.fetchNextPage()}
            />
          )}
          {openQuestions.hasNextPage && (
            <Button
              type="button"
              variant="ghost"
              disabled={openQuestions.isFetchingNextPage}
              onClick={() => void openQuestions.fetchNextPage()}
            >
              {openQuestions.isFetchingNextPage
                ? '질문 불러오는 중…'
                : '미답변 질문 더 보기'}
            </Button>
          )}
          <label htmlFor="record-answer-new-text">보충 답변 내용</label>
          <textarea
            id="record-answer-new-text"
            aria-describedby="record-answer-new-text-length"
            value={newText}
            maxLength={MAX_ANSWER_TEXT_LENGTH + 1}
            onChange={(event) => setNewText(event.target.value)}
            placeholder="수업 후 보충할 설명을 작성하세요."
            rows={4}
          />
          <div className="question-composer__footer">
            <span
              id="record-answer-new-text-length"
              className={
                newTextLength > MAX_ANSWER_TEXT_LENGTH
                  ? 'form-error'
                  : 'input-hint'
              }
            >
              {newTextLength}/{MAX_ANSWER_TEXT_LENGTH}
            </span>
            <Button
              type="submit"
              disabled={!canCreateText || createText.isPending}
            >
              {createText.isPending ? '등록 중…' : '텍스트 Answer 등록'}
            </Button>
          </div>
        </form>
      )}

      {answers.isPending && (
        <StatePanel kind="loading" title="Answer를 불러오는 중" />
      )}
      {answers.isError && !answers.isFetchNextPageError && (
        <StatePanel
          kind="error"
          title="Answer를 불러오지 못했습니다"
          actionLabel="Answer 다시 불러오기"
          onAction={() => void answers.refetch()}
        />
      )}
      {answers.data && items.length === 0 && (
        <StatePanel kind="empty" title="아직 완료된 Answer가 없습니다" />
      )}
      {items.length > 0 && (
        <ol className="answer-list" aria-label="질문 답변 목록">
          {items.map((answer) => {
            const organization = organizationCopy(answer)
            const mapping = mappingCopy(answer)
            const focusTarget = transcriptFocusTarget(answer)
            return (
              <li key={answer.id}>
                <span className="badge">{answerTargetLabel(answer)}</span>
                <p>{answer.target_text_snapshot}</p>
                {answer.answer_type === 'VOICE' && (
                  <div className="answer-range">
                    <p className="input-hint">
                      원본 Transcript {answer.start_sequence ?? '-'}–
                      {answer.end_sequence ?? '-'} 구간 · {mapping}
                    </p>
                    {focusTarget && (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => onFocusTranscript(focusTarget)}
                      >
                        {focusTarget.source === 'CANONICAL'
                          ? '확정 Transcript 구간 보기'
                          : '원본 Transcript 구간 보기'}
                      </Button>
                    )}
                  </div>
                )}
                {answer.text_content && <p>{answer.text_content}</p>}
                {organization && (
                  <div
                    className={`answer-organization answer-organization--${organization.tone}`}
                    role={organization.tone === 'failed' ? 'alert' : 'status'}
                  >
                    <strong>AI 답변 정리</strong>
                    <p>{organization.content}</p>
                    <span className="input-hint">{organization.detail}</span>
                  </div>
                )}
                {editable && (
                  <div className="form-actions">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setEditing(answer)
                        setDraft(answer.text_content ?? '')
                        setErrorMessage(null)
                      }}
                    >
                      {answer.text_content ? '텍스트 수정' : '텍스트 추가'}
                    </Button>
                    {answer.text_content && (
                      <Button
                        variant="ghost"
                        disabled={withdraw.isPending}
                        onClick={() => withdraw.mutate(answer.id)}
                      >
                        텍스트 철회
                      </Button>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
      {answers.isFetchNextPageError && (
        <StatePanel
          kind="error"
          title="다음 Answer를 불러오지 못했습니다"
          description="이미 불러온 Answer는 유지합니다. 같은 위치부터 다시 시도합니다."
          actionLabel="다음 Answer 다시 시도"
          onAction={() => void answers.fetchNextPage()}
        />
      )}
      {answers.hasNextPage && (
        <Button
          variant="secondary"
          disabled={answers.isFetchingNextPage}
          onClick={() => void answers.fetchNextPage()}
        >
          {answers.isFetchingNextPage
            ? 'Answer 불러오는 중…'
            : 'Answer 더 보기'}
        </Button>
      )}

      {editable && editing && (
        <form
          className="answer-text-editor"
          onSubmit={(event) => {
            event.preventDefault()
            if (canSaveText && !updateText.isPending) updateText.mutate()
          }}
        >
          <h3>교수자 텍스트 수정</h3>
          <label htmlFor={`record-answer-edit-${editing.id}`}>
            교수자 답변 내용
          </label>
          <textarea
            id={`record-answer-edit-${editing.id}`}
            aria-describedby={`record-answer-edit-length-${editing.id}`}
            value={draft}
            maxLength={MAX_ANSWER_TEXT_LENGTH + 1}
            onChange={(event) => setDraft(event.target.value)}
            rows={5}
          />
          <div className="question-composer__footer">
            <span
              id={`record-answer-edit-length-${editing.id}`}
              className={
                draftLength > MAX_ANSWER_TEXT_LENGTH
                  ? 'form-error'
                  : 'input-hint'
              }
            >
              {draftLength}/{MAX_ANSWER_TEXT_LENGTH}
            </span>
            <div className="form-actions">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setEditing(null)}
              >
                취소
              </Button>
              <Button
                type="submit"
                disabled={!canSaveText || updateText.isPending}
              >
                {updateText.isPending ? '저장 중…' : '저장'}
              </Button>
            </div>
          </div>
        </form>
      )}
    </section>
  )
}

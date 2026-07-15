import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { listSessionQuestions } from '../questions/api'
import { questionKeys } from '../questions/queries'
import {
  cancelVoiceAnswer,
  completeVoiceAnswer,
  createTextAnswer,
  updateAnswerText,
  withdrawAnswerText,
  type Answer,
} from './api'
import { answerKeys, sessionAnswersQueryOptions } from './queries'

const MAX_ANSWER_TEXT_LENGTH = 2000

interface AnswerPanelProps {
  sessionId: string
  professor: boolean
  sessionStatus: string
}

function normalizedLength(value: string) {
  return Array.from(value.trim().normalize('NFC')).length
}

function answerErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'ANSWER_VERSION_CONFLICT') {
      return '다른 변경이 먼저 저장되었습니다. 작성 중인 내용은 그대로 유지합니다.'
    }
    if (error.code === 'ANSWER_TRANSCRIPT_NOT_READY') {
      return '아직 확정된 Transcript가 없어 완료할 수 없습니다. 잠시 뒤 다시 시도해 주세요.'
    }
    return error.message
  }
  return '요청을 처리하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

function answerTargetLabel(answer: Answer) {
  return answer.target.type === 'STUDENT_QUESTION' ? '학생 질문' : 'AI 대표질문'
}

export function AnswerPanel({
  sessionId,
  professor,
  sessionStatus,
}: AnswerPanelProps) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [editing, setEditing] = useState<Answer | null>(null)
  const [draft, setDraft] = useState('')
  const [selectedQuestionId, setSelectedQuestionId] = useState('')
  const [newText, setNewText] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const completionKeys = useRef<Record<string, string>>({})
  const cancellationKeys = useRef<Record<string, string>>({})
  const createTextKey = useRef<{ signature: string; key: string } | null>(null)
  const withdrawalKeys = useRef<Record<string, string>>({})
  const answers = useQuery(sessionAnswersQueryOptions(sessionId))
  const unansweredQuestions = useQuery({
    queryKey: questionKeys.list(sessionId, 'RECENT', 'OPEN'),
    queryFn: ({ signal }) =>
      listSessionQuestions({
        sessionId,
        sort: 'RECENT',
        status: 'OPEN',
        signal,
      }),
    enabled: professor && sessionStatus === 'COMPLETED',
  })

  function refresh() {
    void queryClient.invalidateQueries({
      queryKey: answerKeys.session(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: questionKeys.session(sessionId),
    })
  }

  const complete = useMutation({
    mutationFn: (answerId: string) =>
      completeVoiceAnswer(
        answerId,
        (completionKeys.current[answerId] ??= crypto.randomUUID()),
      ),
    onSuccess: (_, answerId) => {
      delete completionKeys.current[answerId]
      setErrorMessage(null)
      refresh()
      showToast({
        tone: 'success',
        message: '음성 Answer 구간을 완료했습니다.',
      })
    },
    onError: (error) => setErrorMessage(answerErrorMessage(error)),
  })
  const cancel = useMutation({
    mutationFn: (answerId: string) =>
      cancelVoiceAnswer(
        answerId,
        (cancellationKeys.current[answerId] ??= crypto.randomUUID()),
      ),
    onSuccess: (_, answerId) => {
      delete cancellationKeys.current[answerId]
      setErrorMessage(null)
      refresh()
      showToast({
        tone: 'success',
        message: '음성 Answer 캡처를 취소했습니다.',
      })
    },
    onError: (error) => setErrorMessage(answerErrorMessage(error)),
  })
  const createText = useMutation({
    mutationFn: () => {
      const signature = JSON.stringify([
        selectedQuestionId,
        newText.normalize('NFC'),
      ])
      if (createTextKey.current?.signature !== signature) {
        createTextKey.current = { signature, key: crypto.randomUUID() }
      }
      return createTextAnswer(
        sessionId,
        selectedQuestionId,
        newText,
        createTextKey.current.key,
      )
    },
    onSuccess: () => {
      createTextKey.current = null
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
      withdrawAnswerText(
        answerId,
        (withdrawalKeys.current[answerId] ??= crypto.randomUUID()),
      ),
    onSuccess: (_, answerId) => {
      delete withdrawalKeys.current[answerId]
      setEditing(null)
      setDraft('')
      setErrorMessage(null)
      refresh()
      showToast({ tone: 'success', message: '교수자 텍스트를 철회했습니다.' })
    },
    onError: (error) => setErrorMessage(answerErrorMessage(error)),
  })

  const items = answers.data?.items ?? []
  const capturing = items.find((answer) => answer.status === 'CAPTURING')
  const newTextLength = normalizedLength(newText)
  const draftLength = normalizedLength(draft)
  const canCreateText =
    selectedQuestionId.length > 0 &&
    newTextLength >= 1 &&
    newTextLength <= MAX_ANSWER_TEXT_LENGTH
  const canSaveText = draftLength >= 1 && draftLength <= MAX_ANSWER_TEXT_LENGTH

  return (
    <section className="panel answer-panel" aria-labelledby="answer-title">
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Professor answers</p>
          <h2 id="answer-title">질문 답변</h2>
          <p>
            음성 답변은 선택 시점의 질문 문구와 Transcript 구간을 함께
            보관합니다.
          </p>
        </div>
        <span className="input-hint">{items.length}개</span>
      </header>

      {errorMessage && (
        <p className="form-error" role="alert">
          {errorMessage}
        </p>
      )}

      {professor && sessionStatus === 'LIVE' && capturing && (
        <div className="answer-capture" aria-live="polite">
          <p>
            <strong>답변 캡처 중</strong> · {capturing.target_text_snapshot}
          </p>
          <div className="form-actions">
            <Button
              disabled={complete.isPending || cancel.isPending}
              onClick={() => complete.mutate(capturing.id)}
            >
              {complete.isPending ? '완료 중…' : '답변 완료'}
            </Button>
            <Button
              variant="ghost"
              disabled={complete.isPending || cancel.isPending}
              onClick={() => cancel.mutate(capturing.id)}
            >
              {cancel.isPending ? '취소 중…' : '캡처 취소'}
            </Button>
          </div>
        </div>
      )}

      {professor && sessionStatus === 'COMPLETED' && (
        <form
          className="answer-text-composer"
          onSubmit={(event) => {
            event.preventDefault()
            if (canCreateText && !createText.isPending) createText.mutate()
          }}
        >
          <label htmlFor="answer-question-target">
            미답변 학생 질문에 텍스트 답변
          </label>
          <select
            id="answer-question-target"
            value={selectedQuestionId}
            onChange={(event) => setSelectedQuestionId(event.target.value)}
          >
            <option value="">질문을 선택하세요</option>
            {(unansweredQuestions.data?.items ?? []).map((question) => (
              <option key={question.id} value={question.id}>
                {question.content}
              </option>
            ))}
          </select>
          <textarea
            value={newText}
            onChange={(event) => setNewText(event.target.value)}
            placeholder="수업 후 보충할 설명을 작성하세요."
            rows={4}
          />
          <div className="question-composer__footer">
            <span
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
      {answers.isError && (
        <StatePanel kind="error" title="Answer를 불러오지 못했습니다" />
      )}
      {answers.data && items.length === 0 && (
        <StatePanel
          kind="empty"
          title="아직 완료된 Answer가 없습니다"
          description={
            professor && sessionStatus === 'LIVE'
              ? '질문 또는 대표질문에서 음성 답변을 시작할 수 있습니다.'
              : '교수자가 답변을 남기면 이곳에 표시됩니다.'
          }
        />
      )}
      {items.length > 0 && (
        <ol className="answer-list" aria-label="질문 답변 목록">
          {items.map((answer) => (
            <li key={answer.id}>
              <span className="badge">{answerTargetLabel(answer)}</span>
              <p>{answer.target_text_snapshot}</p>
              {answer.status === 'CAPTURING' ? (
                <p className="input-hint">음성 답변 구간을 캡처 중입니다.</p>
              ) : (
                <>
                  {answer.answer_type === 'VOICE' && (
                    <p className="input-hint">
                      Transcript {answer.start_sequence ?? '-'}–
                      {answer.end_sequence ?? '-'} 구간
                    </p>
                  )}
                  {answer.text_content && <p>{answer.text_content}</p>}
                  {!answer.text_content && answer.answer_type === 'TEXT' && (
                    <p className="input-hint">텍스트를 불러오는 중입니다.</p>
                  )}
                  {professor && sessionStatus === 'COMPLETED' && (
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
                </>
              )}
            </li>
          ))}
        </ol>
      )}

      {editing && (
        <form
          className="answer-text-composer"
          onSubmit={(event) => {
            event.preventDefault()
            if (canSaveText && !updateText.isPending) updateText.mutate()
          }}
        >
          <label htmlFor="answer-edit-text">교수자 텍스트 답변</label>
          <p className="input-hint">{editing.target_text_snapshot}</p>
          <textarea
            id="answer-edit-text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={5}
          />
          <div className="question-composer__footer">
            <span
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
                disabled={updateText.isPending}
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

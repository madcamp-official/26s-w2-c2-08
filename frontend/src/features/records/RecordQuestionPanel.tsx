import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { createQuestion } from '../questions/api'
import { listRecordQuestions } from './api'
import { recordKeys } from './queries'

function questionStatusLabel(status: 'OPEN' | 'SELECTED' | 'ANSWERED') {
  if (status === 'ANSWERED') return '답변 완료'
  if (status === 'SELECTED') return '답변 진행 중'
  return '미답변'
}

export function RecordQuestionPanel({
  sessionId,
  sessionStatus,
  student,
}: {
  sessionId: string
  sessionStatus: 'PROCESSING' | 'COMPLETED'
  student: boolean
}) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [content, setContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const request = useRef<{ content: string; key: string } | null>(null)
  const contentLength = Array.from(content.trim().normalize('NFC')).length
  const questions = useInfiniteQuery({
    queryKey: recordKeys.questions(sessionId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listRecordQuestions(sessionId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor,
    refetchInterval: sessionStatus === 'PROCESSING' ? 3_000 : false,
  })
  const items = questions.data?.pages.flatMap((page) => page.items) ?? []
  const create = useMutation({
    mutationFn: () => {
      const normalized = content.normalize('NFC')
      if (request.current?.content !== normalized) {
        request.current = { content: normalized, key: crypto.randomUUID() }
      }
      return createQuestion(sessionId, content, request.current.key)
    },
    onSuccess: () => {
      request.current = null
      setContent('')
      setError(null)
      void queryClient.invalidateQueries({
        queryKey: recordKeys.questions(sessionId),
      })
      showToast({ tone: 'success', message: '수업 질문을 등록했습니다.' })
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : '질문을 등록하지 못했습니다. 다시 시도해 주세요.',
      ),
  })
  const canSubmit = contentLength >= 1 && contentLength <= 300

  return (
    <section
      className="panel record-questions"
      aria-labelledby="record-questions-title"
    >
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Questions and answers</p>
          <h2 id="record-questions-title">수업 질문</h2>
          <p>
            수업 중과 종료 후 남긴 질문 및 답변 상태를 시간순으로 확인합니다.
          </p>
        </div>
        {questions.data && <span className="input-hint">{items.length}개</span>}
      </header>

      {student && (
        <form
          className="question-composer"
          onSubmit={(event) => {
            event.preventDefault()
            if (canSubmit && !create.isPending) create.mutate()
          }}
        >
          <label htmlFor="record-question-content">수업 후 질문 작성</label>
          <textarea
            id="record-question-content"
            value={content}
            disabled={create.isPending}
            onChange={(event) => setContent(event.target.value)}
            placeholder="복습하면서 궁금해진 내용을 남겨 보세요."
            rows={3}
          />
          <div className="question-composer__footer">
            <span className={contentLength > 300 ? 'form-error' : 'input-hint'}>
              {contentLength}/300
            </span>
            <Button type="submit" disabled={!canSubmit || create.isPending}>
              {create.isPending ? '등록 중…' : '익명 질문 등록'}
            </Button>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </form>
      )}

      {questions.isPending && (
        <StatePanel kind="loading" title="질문을 불러오는 중" />
      )}
      {questions.isError && !questions.isFetchNextPageError && (
        <StatePanel
          kind="error"
          title="질문을 불러오지 못했습니다"
          actionLabel="질문 다시 불러오기"
          onAction={() => void questions.refetch()}
        />
      )}
      {questions.data && items.length === 0 && (
        <StatePanel kind="empty" title="등록된 질문이 없습니다" />
      )}
      {items.length > 0 && (
        <ol className="record-question-list" aria-label="수업 질문 목록">
          {items.map((question) => (
            <li key={question.id}>
              <div>
                <span className="badge">
                  {questionStatusLabel(question.status)}
                </span>
                <p>{question.content}</p>
              </div>
              <span className="input-hint">
                반응 {question.reaction_count} · 질문 #
                {question.clustering_sequence}
              </span>
            </li>
          ))}
        </ol>
      )}
      {questions.isFetchNextPageError && (
        <StatePanel
          kind="error"
          title="다음 질문을 불러오지 못했습니다"
          description="이미 불러온 질문은 유지합니다. 같은 위치부터 다시 시도합니다."
          actionLabel="다음 질문 다시 시도"
          onAction={() => void questions.fetchNextPage()}
        />
      )}
      {questions.hasNextPage && (
        <Button
          variant="secondary"
          disabled={questions.isFetchingNextPage}
          onClick={() => void questions.fetchNextPage()}
        >
          {questions.isFetchingNextPage ? '질문 불러오는 중…' : '질문 더 보기'}
        </Button>
      )}
    </section>
  )
}

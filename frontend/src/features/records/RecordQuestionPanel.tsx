import { useInfiniteQuery } from '@tanstack/react-query'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
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
}: {
  sessionId: string
  sessionStatus: 'PROCESSING' | 'COMPLETED'
}) {
  const questions = useInfiniteQuery({
    queryKey: recordKeys.questions(sessionId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listRecordQuestions(sessionId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor,
    refetchInterval: sessionStatus === 'PROCESSING' ? 3_000 : false,
  })
  const items = questions.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <section
      className="panel record-questions"
      aria-labelledby="record-questions-title"
    >
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Questions and answers</p>
          <h2 id="record-questions-title">수업 질문</h2>
          <p>수업 중 남긴 질문과 답변 상태를 시간순으로 확인합니다.</p>
        </div>
        {questions.data && <span className="input-hint">{items.length}개</span>}
      </header>

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

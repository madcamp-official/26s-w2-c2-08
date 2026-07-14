import { useInfiniteQuery } from '@tanstack/react-query'
import { Link, useOutletContext } from 'react-router-dom'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import type { CourseQnaArchiveItem } from './api'
import type { CourseWorkspaceContextValue } from './context'
import { courseQnaInfiniteQueryOptions } from './queries'

function answerCopy(item: CourseQnaArchiveItem) {
  const answer = item.answer
  if (!answer) return null
  if (answer.text_content) return answer.text_content
  if (answer.organization) {
    return answer.organization.content
  }
  return answer.answer_type === 'VOICE'
    ? '완료된 음성 Answer는 class 기록에서 Transcript 범위와 함께 확인할 수 있습니다.'
    : '완료된 Answer입니다.'
}

function itemLabel(item: CourseQnaArchiveItem) {
  return item.target_type === 'STUDENT_QUESTION' ? '학생 질문' : 'AI 대표질문'
}

export function CourseQnaPage() {
  const { course } = useOutletContext<CourseWorkspaceContextValue>()
  const qna = useInfiniteQuery(courseQnaInfiniteQueryOptions(course.id))
  const items = qna.data?.pages.flatMap((page) => page.items) ?? []

  if (qna.isPending) {
    return <StatePanel kind="loading" title="질의응답을 모으는 중" />
  }
  if (qna.isError && items.length === 0) {
    return (
      <StatePanel
        kind="error"
        title="질의응답 archive를 불러오지 못했습니다"
        description="Course와 class 목록은 유지됩니다."
        actionLabel="다시 시도"
        onAction={() => void qna.refetch()}
      />
    )
  }

  return (
    <section className="course-archive-page" aria-labelledby="qna-title">
      <header className="course-archive-heading">
        <div>
          <p className="eyebrow">Course archive</p>
          <h2 id="qna-title">모든 class의 질의응답</h2>
          <p>
            작성자를 노출하지 않는 학생 질문과 완료된 공개 Answer를 모아 봅니다.
          </p>
        </div>
        <span className="badge">{items.length}개 표시</span>
      </header>

      {items.length === 0 ? (
        <StatePanel
          kind="empty"
          title="표시할 질의응답이 없습니다"
          description="학생 질문이나 완료된 대표질문 Answer가 생기면 이곳에 표시됩니다."
        />
      ) : (
        <ol className="course-qna-archive" aria-live="polite">
          {items.map((item) => {
            const answer = answerCopy(item)
            const itemId =
              item.target_type === 'STUDENT_QUESTION'
                ? item.question.id
                : item.representative_question_id
            return (
              <li
                key={`${item.target_type}-${itemId}`}
                className="panel course-qna-archive__item"
              >
                <div className="course-qna-archive__meta">
                  <span className="badge">{itemLabel(item)}</span>
                  <span>{item.session.title}</span>
                  <time dateTime={item.occurred_at}>
                    {item.session.lecture_date}
                  </time>
                </div>
                <div className="course-qna-archive__question">
                  <h3>{item.target_text_snapshot}</h3>
                  {item.target_type === 'STUDENT_QUESTION' && (
                    <span>
                      반응 {item.question.reaction_count}개 · 작성자 비공개
                    </span>
                  )}
                </div>
                {answer ? (
                  <div className="course-qna-archive__answer">
                    <strong>완료된 Answer</strong>
                    <p>{answer}</p>
                  </div>
                ) : (
                  <p className="course-qna-archive__unanswered">
                    아직 답변이 없습니다.
                  </p>
                )}
                <Link className="button button--ghost" to={item.record_url}>
                  class 기록 보기
                </Link>
              </li>
            )
          })}
        </ol>
      )}

      {qna.isError && items.length > 0 && (
        <div className="course-archive-page__page-error" role="alert">
          <p>다음 질의응답을 불러오지 못했습니다. 표시된 항목은 유지됩니다.</p>
          <Button variant="secondary" onClick={() => void qna.fetchNextPage()}>
            다시 시도
          </Button>
        </div>
      )}
      {qna.hasNextPage && !qna.isError && (
        <Button
          variant="secondary"
          disabled={qna.isFetchingNextPage}
          onClick={() => void qna.fetchNextPage()}
        >
          {qna.isFetchingNextPage ? '불러오는 중…' : '질의응답 더 보기'}
        </Button>
      )}
    </section>
  )
}

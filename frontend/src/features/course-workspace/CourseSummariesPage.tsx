import { useInfiniteQuery } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'

import { apiUrl } from '../../api/client'
import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import type { CourseSummaryArchiveItem } from './api'
import type { CourseWorkspaceContextValue } from './context'
import { courseSummariesInfiniteQueryOptions } from './queries'

interface SummaryPresentation {
  label: string
  description: string
  tone: 'available' | 'pending' | 'muted' | 'failed' | 'integrity'
}

function isPublicFinalSummary(
  item: CourseSummaryArchiveItem,
): item is CourseSummaryArchiveItem & {
  summary: NonNullable<CourseSummaryArchiveItem['summary']>
  summary_url: string
} {
  return (
    item.state.status === 'AVAILABLE' &&
    item.summary !== null &&
    item.summary.summary_type === 'FINAL' &&
    item.summary.visibility === 'COURSE_MEMBERS' &&
    typeof item.summary_url === 'string'
  )
}

function summaryPresentation(
  item: CourseSummaryArchiveItem,
): SummaryPresentation {
  if (item.state.status === 'AVAILABLE') {
    return isPublicFinalSummary(item)
      ? {
          label: '요약 완료',
          description: 'Course 구성원에게 공개된 FINAL Summary입니다.',
          tone: 'available',
        }
      : {
          label: '요약 상태 확인 필요',
          description:
            '요약 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
          tone: 'integrity',
        }
  }
  if (item.state.status === 'PENDING') {
    return {
      label: '요약 준비 중',
      description: '최종 Transcript를 기준으로 요약을 준비하고 있습니다.',
      tone: 'pending',
    }
  }
  if (item.state.status === 'NOT_APPLICABLE') {
    return {
      label: '요약할 내용 없음',
      description: item.state.reason?.message ?? '요약할 강의 내용이 없습니다.',
      tone: 'muted',
    }
  }
  if (item.state.status === 'FAILED') {
    return {
      label: '요약 생성 실패',
      description:
        item.state.reason?.message ??
        'Transcript 처리 문제로 요약을 만들지 못했습니다.',
      tone: 'failed',
    }
  }
  return {
    label: '요약 상태 확인 필요',
    description: '요약 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
    tone: 'integrity',
  }
}

export function CourseSummariesPage() {
  const { course } = useOutletContext<CourseWorkspaceContextValue>()
  const summaries = useInfiniteQuery(
    courseSummariesInfiniteQueryOptions(course.id),
  )
  const items = summaries.data?.pages.flatMap((page) => page.items) ?? []

  if (summaries.isPending) {
    return <StatePanel kind="loading" title="AI 요약을 모으는 중" />
  }

  if (summaries.isError && items.length === 0) {
    return (
      <StatePanel
        kind="error"
        title="AI 요약 archive를 불러오지 못했습니다"
        description="Course와 class 목록은 유지됩니다. 요약 영역만 다시 시도해 주세요."
        actionLabel="다시 시도"
        onAction={() => void summaries.refetch()}
      />
    )
  }

  return (
    <section className="course-archive-page" aria-labelledby="summaries-title">
      <header className="course-archive-heading">
        <div>
          <p className="eyebrow">Course archive</p>
          <h2 id="summaries-title">모든 class의 AI 요약</h2>
          <p>
            Course 구성원에게 공개된 FINAL Summary와 처리 상태만 모아 봅니다.
          </p>
        </div>
        <span className="badge">{items.length}개 class</span>
      </header>

      {items.length === 0 ? (
        <StatePanel
          kind="empty"
          title="표시할 AI 요약이 없습니다"
          description="class 후처리가 시작되면 공용 FINAL Summary 상태가 이곳에 표시됩니다."
        />
      ) : (
        <ul className="course-summary-archive" aria-live="polite">
          {items.map((item) => {
            const presentation = summaryPresentation(item)
            const available = isPublicFinalSummary(item)
            return (
              <li className="panel" key={item.session.id}>
                <header className="course-summary-archive__heading">
                  <div>
                    <span
                      className={`course-summary-status course-summary-status--${presentation.tone}`}
                    >
                      {presentation.label}
                    </span>
                    <h3>{item.session.title}</h3>
                    <p>
                      {item.session.lecture_date} · {item.session.status}
                    </p>
                  </div>
                </header>
                {available ? (
                  <div className="course-summary-archive__content">
                    <p>{item.summary.content}</p>
                    <a
                      className="button button--ghost"
                      href={apiUrl(item.summary_url)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      요약 상세 열기
                    </a>
                  </div>
                ) : (
                  <p className="course-summary-archive__state-copy">
                    {presentation.description}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {summaries.isError && items.length > 0 && (
        <div className="course-archive-page__page-error" role="alert">
          <p>다음 class를 불러오지 못했습니다. 표시된 요약은 유지됩니다.</p>
          <Button
            variant="secondary"
            onClick={() => void summaries.fetchNextPage()}
          >
            다시 시도
          </Button>
        </div>
      )}

      {summaries.hasNextPage && !summaries.isError && (
        <Button
          variant="secondary"
          disabled={summaries.isFetchingNextPage}
          onClick={() => void summaries.fetchNextPage()}
        >
          {summaries.isFetchingNextPage ? '불러오는 중…' : 'AI 요약 더 보기'}
        </Button>
      )}
    </section>
  )
}

import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import type { CourseTranscriptArchiveItem } from './api'
import type { CourseWorkspaceContextValue } from './context'
import { CourseTranscriptTimeline } from './CourseTranscriptTimeline'
import { courseTranscriptsInfiniteQueryOptions } from './queries'

function transcriptCopy(item: CourseTranscriptArchiveItem) {
  const state = item.transcript.state
  if (!state) return 'Transcript 없음'
  if (state.status === 'FINALIZING') return '처리 중'
  if (state.status === 'EMPTY') return '내용 없음'
  if (state.status === 'FAILED') {
    return state.canonical_version?.source === 'LIVE'
      ? 'HQ 실패 · LIVE final 유지'
      : '처리 실패'
  }
  return state.canonical_version?.source === 'RECORDING'
    ? 'HQ canonical'
    : 'LIVE final'
}

export function CourseTranscriptsPage() {
  const { course } = useOutletContext<CourseWorkspaceContextValue>()
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(
    null,
  )
  const transcripts = useInfiniteQuery(
    courseTranscriptsInfiniteQueryOptions(course.id),
  )
  const items = transcripts.data?.pages.flatMap((page) => page.items) ?? []

  if (transcripts.isPending) {
    return <StatePanel kind="loading" title="Transcript를 모으는 중" />
  }
  if (transcripts.isError && items.length === 0) {
    return (
      <StatePanel
        kind="error"
        title="Transcript archive를 불러오지 못했습니다"
        description="Course와 class 목록은 유지됩니다."
        actionLabel="다시 시도"
        onAction={() => void transcripts.refetch()}
      />
    )
  }

  return (
    <section
      className="course-archive-page"
      aria-labelledby="transcripts-title"
    >
      <header className="course-archive-heading">
        <div>
          <p className="eyebrow">Course archive</p>
          <h2 id="transcripts-title">모든 class의 Transcript</h2>
          <p>class별 공개 상태를 먼저 확인하고 선택한 timeline만 불러옵니다.</p>
        </div>
        <span className="badge">{items.length}개 class</span>
      </header>

      {items.length === 0 ? (
        <StatePanel
          kind="empty"
          title="표시할 Transcript가 없습니다"
          description="LIVE final 또는 후처리 결과가 생기면 이곳에 표시됩니다."
        />
      ) : (
        <ul className="course-transcript-archive">
          {items.map((item) => {
            const expanded = expandedSessionId === item.session.id
            return (
              <li className="panel" key={item.session.id}>
                <div className="course-transcript-archive__heading">
                  <div>
                    <span className="badge">{transcriptCopy(item)}</span>
                    <h3>{item.session.title}</h3>
                    <p>
                      {item.session.lecture_date} · 문장{' '}
                      {item.transcript.segment_count}개 · 누락 구간{' '}
                      {item.transcript.gap_count}개
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    aria-expanded={expanded}
                    aria-controls={`transcript-${item.session.id}`}
                    onClick={() =>
                      setExpandedSessionId(expanded ? null : item.session.id)
                    }
                  >
                    {expanded ? 'Transcript 접기' : 'Transcript 펼치기'}
                  </Button>
                </div>
                {expanded && (
                  <div id={`transcript-${item.session.id}`}>
                    <CourseTranscriptTimeline item={item} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {transcripts.isError && items.length > 0 && (
        <div className="course-archive-page__page-error" role="alert">
          <p>다음 class를 불러오지 못했습니다. 표시된 목록은 유지됩니다.</p>
          <Button
            variant="secondary"
            onClick={() => void transcripts.fetchNextPage()}
          >
            다시 시도
          </Button>
        </div>
      )}
      {transcripts.hasNextPage && !transcripts.isError && (
        <Button
          variant="secondary"
          disabled={transcripts.isFetchingNextPage}
          onClick={() => void transcripts.fetchNextPage()}
        >
          {transcripts.isFetchingNextPage ? '불러오는 중…' : 'class 더 보기'}
        </Button>
      )}
    </section>
  )
}

import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import { getRecordTranscriptTimeline } from '../records/api'
import { recordKeys } from '../records/queries'
import type { CourseTranscriptArchiveItem } from './api'

function formatTime(milliseconds: number) {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function CourseTranscriptTimeline({
  item,
}: {
  item: CourseTranscriptArchiveItem
}) {
  const versionId = item.transcript.selected_version_id
  const timeline = useInfiniteQuery({
    queryKey: recordKeys.timeline(item.session.id, versionId ?? 'none'),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      getRecordTranscriptTimeline(
        item.session.id,
        versionId!,
        pageParam,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: Boolean(versionId),
  })
  const entries = useMemo(() => {
    const loaded =
      timeline.data?.pages.flatMap((page) => [
        ...page.segments.map((segment) => ({
          kind: 'segment' as const,
          value: segment,
        })),
        ...page.gaps.map((gap) => ({ kind: 'gap' as const, value: gap })),
      ]) ?? []
    return loaded.sort((left, right) => {
      if (left.value.start_ms !== right.value.start_ms)
        return left.value.start_ms - right.value.start_ms
      if (left.kind !== right.kind) return left.kind === 'segment' ? -1 : 1
      return left.value.id.localeCompare(right.value.id)
    })
  }, [timeline.data])

  if (!versionId) {
    return (
      <StatePanel
        kind="empty"
        title="표시할 Transcript가 없습니다"
        description="처리 상태는 유지하며 임의 문장을 만들지 않습니다."
      />
    )
  }
  if (timeline.isPending) {
    return <p role="status">Transcript timeline을 불러오는 중…</p>
  }
  if (timeline.isError && entries.length === 0) {
    return (
      <StatePanel
        kind="error"
        title="Transcript를 불러오지 못했습니다"
        description="다른 class와 이미 불러온 archive는 유지됩니다."
        actionLabel="다시 시도"
        onAction={() => void timeline.refetch()}
      />
    )
  }

  return (
    <div className="course-transcript-timeline">
      {entries.length === 0 ? (
        <StatePanel kind="empty" title="표시할 Transcript 문장이 없습니다" />
      ) : (
        <ol aria-label={`${item.session.title} Transcript timeline`}>
          {entries.map((entry) => (
            <li
              key={`${entry.kind}-${entry.value.id}`}
              className={`course-transcript-timeline__${entry.kind}`}
            >
              <time>{formatTime(entry.value.start_ms)}</time>
              {entry.kind === 'segment' ? (
                <p>{entry.value.text}</p>
              ) : (
                <p>
                  {entry.value.end_ms === null
                    ? '이후 음성이 누락된 구간입니다.'
                    : `${formatTime(entry.value.end_ms)}까지 음성이 누락된 구간입니다.`}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
      {timeline.isError && entries.length > 0 && (
        <div role="alert" className="course-archive-page__page-error">
          <p>
            다음 Transcript를 불러오지 못했습니다. 표시된 문장은 유지됩니다.
          </p>
          <Button
            variant="secondary"
            onClick={() => void timeline.fetchNextPage()}
          >
            다시 시도
          </Button>
        </div>
      )}
      {timeline.hasNextPage && !timeline.isError && (
        <Button
          variant="secondary"
          disabled={timeline.isFetchingNextPage}
          onClick={() => void timeline.fetchNextPage()}
        >
          {timeline.isFetchingNextPage ? '불러오는 중…' : 'Transcript 더 보기'}
        </Button>
      )}
    </div>
  )
}

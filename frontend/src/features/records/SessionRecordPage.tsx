import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from 'react'

import { apiUrl } from '../../api/client'
import { ApiError } from '../../api/errors'
import { SessionStatusBadge } from '../../components/domain/LmsStatus'
import { PartialFailurePanel } from '../../components/feedback/PartialFailurePanel'
import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import { MaterialPanel } from '../materials/MaterialPanel'
import { PersonalAiPanel } from '../personal-ai/PersonalAiPanel'
import { courseKeys } from '../courses/queries'
import type { SessionRecording } from '../recordings/api'
import {
  getRecordTranscriptTimeline,
  listFinalSummaries,
  type SessionRecord,
} from './api'
import { FinalQuestionMindmap } from './FinalQuestionMindmap'
import { RecordAnswerPanel } from './RecordAnswerPanel'
import { RecordJobsPanel } from './RecordJobsPanel'
import { RecordQuestionPanel } from './RecordQuestionPanel'
import { recordKeys, recordManifestQueryOptions } from './queries'

interface SessionRecordPageProps {
  presentation?: 'default' | 'processing'
  sessionId: string
  professor: boolean
}

interface TranscriptRange {
  startSequence: number
  endSequence: number
}

function formatTime(value: number) {
  const seconds = Math.max(0, Math.floor(value / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function recordStatusCopy(status: 'PROCESSING' | 'COMPLETED') {
  return status === 'COMPLETED'
    ? [
        '완료 기록',
        '수업 기록이 확정되었습니다. 각 영역은 필요할 때 다시 불러올 수 있습니다.',
      ]
    : [
        '기록 정리 중',
        '녹음·Transcript·AI 결과를 정리하고 있습니다. 이미 준비된 기록은 먼저 확인할 수 있습니다.',
      ]
}

function processingCopy(record: SessionRecord) {
  const recording = record.recording
  const transcript = recordTranscriptState(record)
  const summary = record.summary.state
  return [
    [
      '원본 녹음',
      recording
        ? recording.status === 'UPLOADED'
          ? '서버 저장 완료'
          : recording.status === 'FAILED'
            ? '저장 실패'
            : '업로드 확인 중'
        : '브라우저 업로드 확인 중',
    ],
    [
      '고품질 Transcript',
      transcript?.status === 'FINALIZED'
        ? '확정 완료'
        : transcript?.status === 'EMPTY'
          ? '확정 문장 없음'
          : transcript?.status === 'FAILED'
            ? '처리 실패'
            : '처리 대기·진행 중',
    ],
    [
      'AI 수업 요약',
      summary.status === 'AVAILABLE'
        ? '준비 완료'
        : summary.status === 'NOT_APPLICABLE'
          ? '요약 대상 없음'
          : summary.status === 'FAILED' ||
              summary.status === 'DATA_INTEGRITY_ERROR'
            ? '상태 확인 필요'
            : '처리 대기·진행 중',
    ],
    ['독립 후처리', `${record.jobs.total_count}개 상태 확인`],
  ]
}

function recordTranscriptState(record: SessionRecord) {
  return 'state' in record.transcript ? (record.transcript.state ?? null) : null
}

function recordTranscriptVersionId(record: SessionRecord) {
  return 'selected_version_id' in record.transcript
    ? (record.transcript.selected_version_id ?? null)
    : null
}

function summaryCopy(record: SessionRecord) {
  const { status, reason } = record.summary.state
  if (status === 'PENDING')
    return '최종 Transcript를 기준으로 요약을 준비하고 있습니다.'
  if (status === 'NOT_APPLICABLE')
    return reason?.message ?? '요약할 확정 강의 내용이 없습니다.'
  if (status === 'FAILED')
    return reason?.message ?? 'Transcript 처리 문제로 요약을 만들지 못했습니다.'
  if (status === 'DATA_INTEGRITY_ERROR')
    return '요약 상태를 안전하게 확인할 수 없습니다. 다른 기록은 계속 확인할 수 있습니다.'
  return null
}

function RecordProcessingPanel({ record }: { record: SessionRecord }) {
  const completed = record.session.status === 'COMPLETED'
  return (
    <section
      className={`record-processing record-processing--${record.session.status.toLowerCase()}`}
      aria-live="polite"
      aria-label="수업 기록 처리 상태"
    >
      <div>
        <div className="record-processing__heading">
          <p className="eyebrow">Record status</p>
          <SessionStatusBadge status={record.session.status} />
        </div>
        <h2>
          {completed
            ? '수업 기록이 준비되었습니다'
            : '수업 기록을 정리하고 있습니다'}
        </h2>
        <p>
          {completed
            ? '이제 최종 Transcript와 복습 AI를 사용할 수 있습니다.'
            : '작업 개수로 완료 여부를 추측하지 않습니다. class 상태가 완료되면 자동으로 전환됩니다.'}
        </p>
      </div>
      <dl className="record-processing__steps">
        {processingCopy(record).map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function RecordOverview({ record }: { record: SessionRecord }) {
  const items = [
    ['강의자료', record.materials.total_count],
    ['Transcript', record.transcript.segment_count],
    ['누락 구간', record.transcript.gap_count],
    ['질문', record.questions.total_count],
    ['Answer', record.answers.total_count],
  ]
  return (
    <ul className="record-overview" aria-label="수업 기록 구성">
      {items.map(([label, count]) => (
        <li key={label}>
          <strong>{count}</strong>
          <span>{label}</span>
        </li>
      ))}
    </ul>
  )
}

function RecordRecordingPanel({
  recording,
  audioRef,
  sessionStatus,
}: {
  recording: SessionRecording | null
  audioRef: MutableRefObject<HTMLAudioElement | null>
  sessionStatus: 'PROCESSING' | 'COMPLETED'
}) {
  if (!recording)
    return (
      <section
        className="panel recording-playback"
        aria-labelledby="recording-playback-title"
      >
        <p className="eyebrow">Recording playback</p>
        <h2 id="recording-playback-title">수업 녹음</h2>
        {sessionStatus === 'PROCESSING' ? (
          <StatePanel
            kind="loading"
            title="원본 녹음 저장 상태를 확인하는 중"
            description="publisher 브라우저의 마감·업로드와 서버 저장은 독립적으로 진행됩니다. 다른 기록은 먼저 확인할 수 있습니다."
          />
        ) : (
          <p className="input-hint">
            이 수업에는 저장된 녹음이 없습니다. Transcript와 다른 기록은 계속
            확인할 수 있습니다.
          </p>
        )}
      </section>
    )

  if (!recording.playback_url)
    return (
      <section
        className="panel recording-playback"
        aria-labelledby="recording-playback-title"
      >
        <p className="eyebrow">Recording playback</p>
        <h2 id="recording-playback-title">수업 녹음</h2>
        {recording.status === 'FAILED' ? (
          <StatePanel
            kind="error"
            title="원본 녹음을 저장하지 못했습니다"
            description="저장된 Transcript·질문·Answer와 다른 처리 결과는 계속 확인할 수 있습니다."
          />
        ) : (
          <p className="input-hint" role="status">
            {recording.status === 'UPLOADED'
              ? '원본 녹음은 서버에 저장되었습니다. class 완료 뒤 권한을 다시 확인해 재생합니다.'
              : '원본 녹음을 서버에 저장하고 있습니다. 재생 준비와 다른 후처리 작업은 독립적으로 갱신됩니다.'}
          </p>
        )}
      </section>
    )

  return (
    <section
      className="panel recording-playback"
      aria-labelledby="recording-playback-title"
    >
      <header>
        <p className="eyebrow">Recording playback</p>
        <h2 id="recording-playback-title">수업 녹음</h2>
      </header>
      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={apiUrl(recording.playback_url)}
      />
      <p className="input-hint">
        Transcript 문장을 선택하면 서버가 확정한 녹음 위치로 이동합니다.
      </p>
    </section>
  )
}

function FinalSummaryPanel({ record }: { record: SessionRecord }) {
  const summary = useQuery({
    queryKey: recordKeys.summary(record.session.id),
    queryFn: ({ signal }) => listFinalSummaries(record.session.id, signal),
    enabled: record.summary.state.status === 'AVAILABLE',
  })
  const copy = summaryCopy(record)

  return (
    <section
      className="panel record-summary"
      aria-labelledby="record-summary-title"
    >
      <header>
        <p className="eyebrow">Final summary</p>
        <h2 id="record-summary-title">AI 수업 요약</h2>
      </header>
      {record.summary.state.status === 'AVAILABLE' && summary.isPending && (
        <p role="status">최종 요약을 불러오는 중…</p>
      )}
      {record.summary.state.status === 'AVAILABLE' && summary.isError && (
        <StatePanel
          kind="error"
          title="최종 요약을 불러오지 못했습니다"
          description="다른 수업 기록은 계속 확인할 수 있습니다."
          actionLabel="요약 다시 불러오기"
          onAction={() => void summary.refetch()}
        />
      )}
      {record.summary.state.status === 'AVAILABLE' &&
        summary.data?.items[0] && (
          <p className="record-summary__content">
            {summary.data.items[0].content}
          </p>
        )}
      {record.summary.state.status === 'AVAILABLE' &&
        summary.data &&
        summary.data.items.length === 0 && (
          <StatePanel
            kind="error"
            title="최종 요약 결과를 확인할 수 없습니다"
            description="요약 상태를 다시 확인해 주세요."
          />
        )}
      {copy && <p className="input-hint">{copy}</p>}
    </section>
  )
}

function RecordTranscriptPanel({
  record,
  onSeek,
  highlightRange,
}: {
  record: SessionRecord
  onSeek: (offset: number) => void
  highlightRange: TranscriptRange | null
}) {
  const timelineRef = useRef<HTMLOListElement | null>(null)
  const versionId = recordTranscriptVersionId(record)
  const timeline = useInfiniteQuery({
    queryKey: recordKeys.timeline(record.session.id, versionId ?? 'none'),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      getRecordTranscriptTimeline(
        record.session.id,
        versionId!,
        pageParam,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor,
    enabled: Boolean(versionId),
  })
  const items = useMemo(() => {
    const entries =
      timeline.data?.pages.flatMap((page) => [
        ...page.segments.map((segment) => ({
          kind: 'segment' as const,
          value: segment,
        })),
        ...page.gaps.map((gap) => ({ kind: 'gap' as const, value: gap })),
      ]) ?? []
    return entries.sort((left, right) => {
      if (left.value.start_ms !== right.value.start_ms)
        return left.value.start_ms - right.value.start_ms
      if (left.kind !== right.kind) return left.kind === 'segment' ? -1 : 1
      return left.value.id.localeCompare(right.value.id)
    })
  }, [timeline.data])

  useEffect(() => {
    if (!highlightRange || !timelineRef.current) return
    const item = items.find(
      (entry) =>
        entry.kind === 'segment' &&
        entry.value.sequence >= highlightRange.startSequence &&
        entry.value.sequence <= highlightRange.endSequence,
    )
    if (!item || item.kind !== 'segment') return
    const target = timelineRef.current.querySelector<HTMLElement>(
      `[data-segment-id="${item.value.id}"]`,
    )
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)')
      .matches
      ? 'auto'
      : 'smooth'
    target?.scrollIntoView({ block: 'center', behavior })
    target?.focus({ preventScroll: true })
  }, [highlightRange, items])

  const transcriptState = recordTranscriptState(record)
  if (!transcriptState)
    return (
      <section
        className="panel record-transcript"
        aria-labelledby="record-transcript-title"
      >
        <p className="eyebrow">Final transcript</p>
        <h2 id="record-transcript-title">강의 Transcript</h2>
        <StatePanel
          kind={record.session.status === 'PROCESSING' ? 'loading' : 'empty'}
          title={
            record.session.status === 'PROCESSING'
              ? '고품질 Transcript 처리를 기다리는 중'
              : '아직 확정된 Transcript가 없습니다'
          }
          description="현재 canonical 기록은 유지하며 새 version이 준비되면 이 영역만 갱신합니다."
        />
      </section>
    )

  return (
    <section
      className="panel record-transcript"
      aria-labelledby="record-transcript-title"
    >
      <header className="record-transcript__heading">
        <div>
          <p className="eyebrow">Final transcript</p>
          <h2 id="record-transcript-title">강의 Transcript</h2>
        </div>
        <span className="input-hint">{transcriptState.status}</span>
      </header>
      {transcriptState.status === 'FINALIZING' && (
        <p className="input-hint" role="status">
          고품질 Transcript와 녹음 위치를 정리하고 있습니다.
        </p>
      )}
      {transcriptState.status === 'FAILED' && (
        <StatePanel
          kind="error"
          title="Transcript 처리를 완료하지 못했습니다"
          description="누락된 내용을 추측해 표시하지 않습니다. 다른 기록은 계속 확인할 수 있습니다."
        />
      )}
      {transcriptState.status === 'EMPTY' && (
        <StatePanel
          kind="empty"
          title="확정할 강의 내용이 없습니다"
          description="녹음 또는 실시간 final Transcript가 남아 있지 않았습니다."
        />
      )}
      {versionId && timeline.isPending && (
        <p role="status">Transcript를 불러오는 중…</p>
      )}
      {versionId && timeline.isError && (
        <StatePanel
          kind="error"
          title="Transcript를 불러오지 못했습니다"
          description="다시 시도해도 다른 기록을 초기화하지 않습니다."
          actionLabel="Transcript 다시 불러오기"
          onAction={() => void timeline.refetch()}
        />
      )}
      {items.length > 0 && (
        <ol
          ref={timelineRef}
          className="record-transcript__timeline"
          aria-label="확정 Transcript 타임라인"
        >
          {items.map((item) => (
            <li
              key={item.value.id}
              data-segment-id={
                item.kind === 'segment' ? item.value.id : undefined
              }
              tabIndex={item.kind === 'segment' ? -1 : undefined}
              className={`record-transcript__${item.kind}${
                item.kind === 'segment' &&
                highlightRange &&
                item.value.sequence >= highlightRange.startSequence &&
                item.value.sequence <= highlightRange.endSequence
                  ? ' record-transcript__segment--highlighted'
                  : ''
              }`}
            >
              <time>{formatTime(item.value.start_ms)}</time>
              {item.kind === 'segment' ? (
                item.value.recording_start_ms === null ? (
                  <p>{item.value.text}</p>
                ) : (
                  <button
                    type="button"
                    onClick={() => onSeek(item.value.recording_start_ms!)}
                  >
                    {item.value.text}
                  </button>
                )
              ) : (
                <p>
                  {formatTime(item.value.start_ms)}
                  {item.value.end_ms === null
                    ? ' 이후'
                    : `–${formatTime(item.value.end_ms)}`}{' '}
                  · 음성이 누락된 구간입니다.
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
      {versionId &&
        timeline.data &&
        items.length === 0 &&
        transcriptState.status === 'FINALIZED' && (
          <StatePanel kind="empty" title="표시할 Transcript 문장이 없습니다" />
        )}
      {timeline.hasNextPage && (
        <Button
          variant="secondary"
          disabled={timeline.isFetchingNextPage}
          onClick={() => void timeline.fetchNextPage()}
        >
          {timeline.isFetchingNextPage
            ? '더 불러오는 중…'
            : '이전 Transcript 더 보기'}
        </Button>
      )}
    </section>
  )
}

export function SessionRecordPage({
  sessionId,
  professor,
  presentation = 'default',
}: SessionRecordPageProps) {
  const queryClient = useQueryClient()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const previousStatus = useRef<'PROCESSING' | 'COMPLETED' | null>(null)
  const [highlightRange, setHighlightRange] = useState<TranscriptRange | null>(
    null,
  )
  const record = useQuery({
    ...recordManifestQueryOptions(sessionId),
    refetchInterval: (query) =>
      query.state.data?.session.status === 'PROCESSING' ? 3_000 : false,
  })

  useEffect(() => {
    if (!record.data) return
    queryClient.setQueryData(courseKeys.session(sessionId), record.data.session)
    if (
      previousStatus.current !== 'COMPLETED' &&
      record.data.session.status === 'COMPLETED'
    ) {
      void queryClient.invalidateQueries({
        queryKey: courseKeys.detail(record.data.session.course_id),
      })
      void queryClient.invalidateQueries({
        queryKey: courseKeys.sessions(record.data.session.course_id),
      })
    }
    previousStatus.current = record.data.session.status as
      'PROCESSING' | 'COMPLETED'
    const versionId = recordTranscriptVersionId(record.data)
    if (versionId)
      void queryClient.invalidateQueries({
        queryKey: recordKeys.timeline(sessionId, versionId),
      })
  }, [queryClient, record.data, sessionId])

  if (record.isPending)
    return <StatePanel kind="loading" title="수업 기록을 준비하는 중" />
  if (record.error instanceof ApiError && record.error.status === 403)
    return (
      <StatePanel
        kind="forbidden"
        title="이 수업 기록에 접근할 권한이 없습니다"
      />
    )
  if (record.error instanceof ApiError && record.error.status === 404)
    return <StatePanel kind="not-found" title="수업 기록을 찾을 수 없습니다" />
  if (!record.data)
    return (
      <StatePanel
        kind="error"
        title="수업 기록을 불러오지 못했습니다"
        actionLabel="기록 다시 불러오기"
        onAction={() => void record.refetch()}
      />
    )

  const data = record.data
  const status = data.session.status as 'PROCESSING' | 'COMPLETED'
  const [title, description] = recordStatusCopy(status)
  const processing = status === 'PROCESSING'
  const refreshWarning = record.isRefetchError ? (
    <PartialFailurePanel
      title="최신 기록 상태를 확인하지 못했습니다"
      description="마지막으로 확인한 기록은 유지합니다. 다른 영역을 초기화하지 않고 manifest만 다시 확인합니다."
      actions={
        <Button
          variant="secondary"
          disabled={record.isFetching}
          onClick={() => void record.refetch()}
        >
          {record.isFetching ? '상태 확인 중…' : '기록 상태 다시 확인'}
        </Button>
      }
    />
  ) : null
  const seek = (offset: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = offset / 1000
    void audio.play().catch(() => undefined)
  }

  return (
    <section
      className={`record-page record-page--${presentation}`}
      aria-labelledby={
        presentation === 'default' ? 'record-page-title' : undefined
      }
    >
      {presentation === 'default' && (
        <header className="record-page__header">
          <div>
            <p className="eyebrow">Class record</p>
            <h1 id="record-page-title">{title}</h1>
            <p>{description}</p>
          </div>
          <SessionStatusBadge status={status} />
        </header>
      )}
      {refreshWarning}
      <RecordProcessingPanel record={data} />
      <RecordOverview record={data} />
      <div
        className={`record-page__content${
          processing ? ' record-page__content--processing' : ''
        }`}
      >
        <MaterialPanel
          sessionId={data.session.id}
          professor={professor}
          sessionStatus={data.session.status}
        />
        <RecordRecordingPanel
          recording={data.recording}
          audioRef={audioRef}
          sessionStatus={status}
        />
        <FinalSummaryPanel record={data} />
        <RecordTranscriptPanel
          record={data}
          onSeek={seek}
          highlightRange={highlightRange}
        />
        <RecordQuestionPanel
          sessionId={data.session.id}
          sessionStatus={status}
        />
        <FinalQuestionMindmap
          sessionId={data.session.id}
          sessionStatus={status}
        />
        <RecordAnswerPanel
          sessionId={data.session.id}
          professor={professor}
          sessionStatus={status}
          onFocusTranscriptRange={(startSequence, endSequence) =>
            setHighlightRange({ startSequence, endSequence })
          }
        />
        <RecordJobsPanel
          sessionId={data.session.id}
          professor={professor}
          sessionStatus={status}
        />
        {status === 'COMPLETED' && (
          <>
            <PersonalAiPanel sessionId={data.session.id} mode="REVIEW" />
          </>
        )}
      </div>
    </section>
  )
}

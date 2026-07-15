import type { LiveTranscriptState } from './live-state'

interface LiveTranscriptPanelProps {
  transcript: LiveTranscriptState
  connectionState:
    'connecting' | 'connected' | 'reconnecting' | 'resyncing' | 'stopped'
  loading?: boolean
  error?: boolean
  retrying?: boolean
  onRetry?: () => void
}

function timeCopy(value: number) {
  const seconds = Math.max(0, Math.floor(value / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export function LiveTranscriptPanel({
  transcript,
  connectionState,
  loading = false,
  error = false,
  retrying = false,
  onRetry,
}: LiveTranscriptPanelProps) {
  const partials = Object.values(transcript.partials).sort(
    (a, b) => a.startMs - b.startMs,
  )
  const timelineItems = [
    ...transcript.segments.map((item) => ({
      id: item.id,
      kind: 'segment' as const,
      startMs: item.start_ms,
      text: item.text,
    })),
    ...transcript.gaps.map((item) => ({
      id: item.id,
      kind: 'gap' as const,
      startMs: item.start_ms,
      text: '이 구간의 음성이 누락되었습니다. 내용을 추측해 채우지 않습니다.',
    })),
    ...partials.map((item) => ({
      id: item.utteranceId,
      kind: 'partial' as const,
      startMs: item.startMs,
      text: item.text,
    })),
  ].sort(
    (a, b) =>
      a.startMs - b.startMs ||
      { segment: 0, gap: 1, partial: 2 }[a.kind] -
        { segment: 0, gap: 1, partial: 2 }[b.kind] ||
      a.id.localeCompare(b.id),
  )
  const isDegraded = transcript.streamStatus === 'DEGRADED'
  return (
    <section
      className="panel live-transcript"
      aria-labelledby="live-transcript-title"
    >
      <header className="live-panel-heading">
        <div>
          <p className="eyebrow">Live transcript</p>
          <h2 id="live-transcript-title">실시간 강의 내용</h2>
        </div>
        <span className={`live-connection live-connection--${connectionState}`}>
          {connectionState === 'connected'
            ? '연결됨'
            : connectionState === 'resyncing'
              ? '내용 다시 불러오는 중'
              : connectionState === 'reconnecting'
                ? '재연결 중'
                : connectionState === 'stopped'
                  ? '연결 종료됨'
                  : '연결 준비 중'}
        </span>
      </header>
      {isDegraded && (
        <p className="live-notice live-notice--warning" role="status">
          실시간 음성 인식이 일시적으로 지연되고 있습니다. 수업과 질문 작성은
          계속할 수 있습니다.
        </p>
      )}
      {transcript.resyncing && (
        <p className="live-notice" role="status">
          확정된 Transcript를 다시 동기화하고 있습니다.
        </p>
      )}
      {loading && timelineItems.length === 0 && (
        <p className="live-notice" role="status">
          저장된 Transcript를 불러오는 중입니다.
        </p>
      )}
      {error && (
        <div className="live-notice live-notice--error" role="alert">
          <p>
            저장된 Transcript를 불러오지 못했습니다. 실시간 연결과 질문 기능은
            계속 사용할 수 있습니다.
          </p>
          {onRetry && (
            <button
              className="button button--secondary"
              type="button"
              disabled={retrying}
              onClick={onRetry}
            >
              {retrying ? '다시 불러오는 중…' : 'Transcript 다시 불러오기'}
            </button>
          )}
        </div>
      )}
      <ol
        className="live-transcript__items"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {timelineItems.map((item) => (
          <li
            key={`${item.kind}-${item.id}`}
            className={`live-transcript__${item.kind}`}
            aria-live={item.kind === 'partial' ? 'off' : undefined}
          >
            <time dateTime={`PT${item.startMs / 1000}S`}>
              {timeCopy(item.startMs)}
            </time>
            <div>
              {item.kind === 'partial' && (
                <span className="live-transcript__partial-label">
                  인식 중 · 저장되지 않음 · 답변 후보 제외
                </span>
              )}
              <p>{item.text}</p>
            </div>
          </li>
        ))}
      </ol>
      {!loading && !error && timelineItems.length === 0 && (
        <p className="input-hint">
          교수자의 음성 전송이 시작되면 여기에서 실시간으로 확인할 수 있습니다.
        </p>
      )}
    </section>
  )
}

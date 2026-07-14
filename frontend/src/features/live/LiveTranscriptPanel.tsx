import type { LiveTranscriptState } from './live-state'

interface LiveTranscriptPanelProps {
  transcript: LiveTranscriptState
  connectionState:
    'connecting' | 'connected' | 'reconnecting' | 'resyncing' | 'stopped'
}

function timeCopy(value: number) {
  const seconds = Math.max(0, Math.floor(value / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export function LiveTranscriptPanel({
  transcript,
  connectionState,
}: LiveTranscriptPanelProps) {
  const partials = Object.values(transcript.partials).sort(
    (a, b) => a.startMs - b.startMs,
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
      <ol
        className="live-transcript__items"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {transcript.segments.map((segment) => (
          <li key={segment.id} className="live-transcript__segment">
            <time dateTime={`PT${segment.start_ms / 1000}S`}>
              {timeCopy(segment.start_ms)}
            </time>
            <p>{segment.text}</p>
          </li>
        ))}
        {transcript.gaps.map((gap) => (
          <li key={gap.id} className="live-transcript__gap">
            <time>{timeCopy(gap.start_ms)}</time>
            <p>
              이 구간의 음성이 누락되었습니다. 내용을 추측해 채우지 않습니다.
            </p>
          </li>
        ))}
        {partials.map((partial) => (
          <li
            key={partial.utteranceId}
            className="live-transcript__partial"
            aria-live="off"
          >
            <time>{timeCopy(partial.startMs)}</time>
            <p>{partial.text}</p>
          </li>
        ))}
      </ol>
      {transcript.segments.length === 0 &&
        partials.length === 0 &&
        transcript.gaps.length === 0 && (
          <p className="input-hint">
            교수자의 음성 전송이 시작되면 여기에서 실시간으로 확인할 수
            있습니다.
          </p>
        )}
    </section>
  )
}

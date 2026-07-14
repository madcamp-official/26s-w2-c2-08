import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiUrl } from '../../api/client'
import { getLiveTranscript } from '../live/api'
import { getSessionRecording } from './api'

export function RecordingPlaybackPanel({ sessionId }: { sessionId: string }) {
  const player = useRef<HTMLAudioElement | null>(null)
  const recording = useQuery({
    queryKey: ['recordings', sessionId],
    queryFn: ({ signal }) => getSessionRecording(sessionId, signal),
  })
  const transcript = useQuery({
    queryKey: ['recordings', sessionId, 'timeline'],
    queryFn: ({ signal }) => getLiveTranscript(sessionId, signal),
  })
  if (recording.isPending)
    return (
      <section className="panel recording-playback">
        <p>녹음 정보를 불러오는 중…</p>
      </section>
    )
  if (recording.isError || !recording.data.playback_url)
    return (
      <section className="panel recording-playback">
        <h2>수업 녹음</h2>
        <p className="input-hint">
          아직 재생할 수 있는 저장 녹음이 없습니다. 다른 수업 기록은 계속 확인할
          수 있습니다.
        </p>
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
        ref={player}
        controls
        preload="metadata"
        src={apiUrl(recording.data.playback_url)}
      />
      <p className="input-hint">
        문장을 선택하면 서버가 확정한 녹음 위치로 이동합니다.
      </p>
      <ol className="recording-playback__segments">
        {transcript.data?.segments.map((segment) => {
          const offset = segment.recording_start_ms
          return (
            <li key={segment.id}>
              {offset === null ? (
                <span>{segment.text}</span>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    if (!player.current) return
                    player.current.currentTime = offset / 1000
                    void player.current.play()
                  }}
                >
                  {segment.text}
                </button>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

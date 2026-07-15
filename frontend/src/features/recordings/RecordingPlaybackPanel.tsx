import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiUrl } from '../../api/client'
import { ApiError } from '../../api/errors'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { getLiveTranscript } from '../live/api'
import { deleteSessionRecording, getSessionRecording } from './api'

export function RecordingPlaybackPanel({
  sessionId,
  professor,
}: {
  sessionId: string
  professor: boolean
}) {
  const player = useRef<HTMLAudioElement | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const recording = useQuery({
    queryKey: ['recordings', sessionId],
    queryFn: ({ signal }) => getSessionRecording(sessionId, signal),
  })
  const transcript = useQuery({
    queryKey: ['recordings', sessionId, 'timeline'],
    queryFn: ({ signal }) => getLiveTranscript(sessionId, signal),
  })
  const remove = useMutation({
    mutationFn: () => deleteSessionRecording(sessionId, crypto.randomUUID()),
    onSuccess: () => {
      setDeleteOpen(false)
      void queryClient.invalidateQueries({
        queryKey: ['recordings', sessionId],
      })
      showToast({ tone: 'success', message: '수업 녹음을 삭제했습니다.' })
    },
    onError: (error) => {
      showToast({
        tone: 'error',
        message:
          error instanceof ApiError && error.status === 409
            ? '완료된 수업의 업로드 완료 녹음만 삭제할 수 있습니다.'
            : '수업 녹음을 삭제하지 못했습니다.',
      })
    },
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
        crossOrigin="use-credentials"
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
      {professor && (
        <div className="recording-playback__danger">
          <p className="input-hint">
            녹음을 삭제하면 재생할 수 없고, Transcript와 질문·Answer 기록은
            유지됩니다.
          </p>
          <Button variant="ghost" onClick={() => setDeleteOpen(true)}>
            녹음 삭제
          </Button>
        </div>
      )}
      {professor && (
        <Dialog
          open={deleteOpen}
          title="수업 녹음을 삭제할까요?"
          description="원본 녹음은 복구할 수 없으며, Transcript와 다른 수업 기록은 유지됩니다."
          onOpenChange={setDeleteOpen}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={remove.isPending}
                onClick={() => setDeleteOpen(false)}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? '삭제 중…' : '녹음 삭제'}
              </Button>
            </>
          }
        >
          <p>
            삭제 요청이 확정되면 metadata와 playback은 즉시 숨기고, private
            파일은 별도 worker가 재시도하며 정리합니다.
          </p>
        </Dialog>
      )}
    </section>
  )
}

import { useCallback, useEffect, useReducer, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { useToast } from '../../components/feedback/toast-context'
import { AnswerPanel } from '../answers/AnswerPanel'
import type { AnswerTarget } from '../answers/api'
import { QuestionMindmap } from '../questions/QuestionMindmap'
import { QuestionPanel } from '../questions/QuestionPanel'
import { answerKeys } from '../answers/queries'
import { questionKeys } from '../questions/queries'
import { useSessionRealtime } from '../realtime/useSessionRealtime'
import type { RealtimeConnectionState, RealtimeEvent } from '../realtime/client'
import type { LectureSession } from '../courses/api'
import { courseKeys } from '../courses/queries'
import { getLiveTranscript } from './api'
import { LiveAudioPublisherControl } from './LiveAudioPublisherControl'
import { LiveTranscriptPanel } from './LiveTranscriptPanel'
import { initialLiveTranscriptState, liveTranscriptReducer } from './live-state'
import { PersonalAiPanel } from '../personal-ai/PersonalAiPanel'
import { LocalRecordingPanel } from '../recordings/LocalRecordingPanel'

interface Props {
  session: LectureSession
  professor: boolean
  onStartVoiceAnswer: (target: AnswerTarget) => void
  answerCapturePending: boolean
  onEnd: () => void
  endPending: boolean
}

export function LiveClassRoom({
  session,
  professor,
  onStartVoiceAnswer,
  answerCapturePending,
  onEnd,
  endPending,
}: Props) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [transcript, dispatch] = useReducer(
    liveTranscriptReducer,
    initialLiveTranscriptState,
  )
  const [connectionState, setConnectionState] = useState<
    RealtimeConnectionState | 'resyncing'
  >('connecting')
  const [refreshNonce, setRefreshNonce] = useState(0)
  const [endOpen, setEndOpen] = useState(false)
  const [recordingStream, setRecordingStream] = useState<MediaStream | null>(
    null,
  )
  const [recordingClientStreamId, setRecordingClientStreamId] = useState<
    string | null
  >(null)
  const timeline = useQuery({
    queryKey: ['sessions', session.id, 'live-transcript'],
    queryFn: ({ signal }) => getLiveTranscript(session.id, signal),
  })

  const timelineVersion = timeline.data?.selected_version.id
  useEffect(() => {
    if (timeline.data) dispatch({ type: 'hydrate', data: timeline.data })
    // REST hydrates initial state and only a version change/resync. Final events merge directly.
  }, [refreshNonce, timeline.data, timelineVersion])

  const onEvent = useCallback(
    (event: RealtimeEvent) => dispatch({ type: 'event', event }),
    [],
  )
  const onResync = useCallback(() => {
    setConnectionState('resyncing')
    dispatch({
      type: 'event',
      event: {
        event_id: crypto.randomUUID(),
        type: 'resync.required',
        session_id: session.id,
        cursor: null,
        resource_version: null,
        data: {},
      },
    })
    void queryClient
      .invalidateQueries({
        queryKey: ['sessions', session.id, 'live-transcript'],
      })
      .then(() => {
        setRefreshNonce((value) => value + 1)
        setConnectionState('connected')
      })
  }, [queryClient, session.id])
  const onConnection = useCallback((next: RealtimeConnectionState) => {
    setConnectionState((current) =>
      current === 'resyncing' && next === 'connected' ? 'resyncing' : next,
    )
  }, [])
  useSessionRealtime({
    sessionId: session.id,
    courseId: session.course_id,
    enabled: true,
    onEvent,
    onResyncRequired: onResync,
    onConnectionState: onConnection,
  })

  const invalidateQuestions = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: questionKeys.session(session.id),
    })
    void queryClient.invalidateQueries({
      queryKey: answerKeys.session(session.id),
    })
    void queryClient.invalidateQueries({
      queryKey: courseKeys.session(session.id),
    })
  }, [queryClient, session.id])

  useEffect(() => {
    return () => {
      invalidateQuestions()
    }
  }, [invalidateQuestions])

  return (
    <section className="live-class-room" aria-label="실시간 수업">
      <header className="live-class-room__header">
        <div>
          <p className="eyebrow">LIVE CLASS</p>
          <h2>{session.title}</h2>
          <p>질문과 확정 Transcript는 실시간으로 갱신됩니다.</p>
        </div>
        {professor && (
          <div className="live-class-room__controls">
            <LiveAudioPublisherControl
              sessionId={session.id}
              onMediaStream={(stream, clientStreamId) => {
                setRecordingStream(stream)
                setRecordingClientStreamId(clientStreamId)
              }}
            />
            <Button
              variant="danger"
              disabled={endPending}
              onClick={() => setEndOpen(true)}
            >
              {endPending ? '종료 중…' : '수업 종료'}
            </Button>
          </div>
        )}
      </header>
      {professor && (
        <LocalRecordingPanel
          sessionId={session.id}
          stream={recordingStream}
          clientStreamId={recordingClientStreamId}
          sessionStatus="LIVE"
        />
      )}
      <div className="live-class-room__grid">
        <LiveTranscriptPanel
          transcript={transcript}
          connectionState={connectionState}
        />
        <div className="live-class-room__questions">
          <QuestionPanel
            sessionId={session.id}
            student={!professor}
            onStartVoiceAnswer={professor ? onStartVoiceAnswer : undefined}
            answerCapturePending={answerCapturePending}
          />
          <QuestionMindmap
            sessionId={session.id}
            onStartVoiceAnswer={professor ? onStartVoiceAnswer : undefined}
            answerCapturePending={answerCapturePending}
          />
          {professor && (
            <AnswerPanel
              sessionId={session.id}
              professor
              sessionStatus="LIVE"
            />
          )}
          <PersonalAiPanel sessionId={session.id} mode="LIVE" />
        </div>
      </div>
      {timeline.isError && (
        <p className="form-error" role="alert">
          확정 Transcript를 불러오지 못했습니다. 연결이 복구되면 다시
          시도합니다.
        </p>
      )}
      {professor && (
        <Dialog
          open={endOpen}
          title="수업을 종료할까요?"
          description="마이크 전송을 멈추고 수업 기록 정리를 시작합니다."
          onOpenChange={setEndOpen}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={endPending}
                onClick={() => setEndOpen(false)}
              >
                계속 수업
              </Button>
              <Button
                variant="danger"
                disabled={endPending}
                onClick={() => {
                  onEnd()
                  setEndOpen(false)
                  showToast({
                    tone: 'success',
                    message: '수업 종료를 요청했습니다.',
                  })
                }}
              >
                수업 종료
              </Button>
            </>
          }
        >
          <p className="input-hint">
            브라우저 탭을 닫기 전에는 마이크 전송을 중지하는 것이 안전합니다.
          </p>
        </Dialog>
      )}
    </section>
  )
}

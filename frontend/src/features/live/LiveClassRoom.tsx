import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { AnswerPanel } from '../answers/AnswerPanel'
import type { AnswerTarget } from '../answers/api'
import { sessionAnswersQueryOptions } from '../answers/queries'
import type { LectureSession } from '../courses/api'
import { courseKeys } from '../courses/queries'
import { MaterialPanel } from '../materials/MaterialPanel'
import { PersonalAiPanel } from '../personal-ai/PersonalAiPanel'
import { purgeLivePersonalAiClientState } from '../personal-ai/client-state'
import { QuestionClusterList } from '../questions/QuestionClusterList'
import { QuestionPanel } from '../questions/QuestionPanel'
import type { RealtimeConnectionState, RealtimeEvent } from '../realtime/client'
import { useSessionRealtime } from '../realtime/useSessionRealtime'
import {
  LocalRecordingPanel,
  type LocalRecordingPanelHandle,
} from '../recordings/LocalRecordingPanel'
import {
  LiveAudioPublisherControl,
  type LiveAudioPublisherControlHandle,
} from './LiveAudioPublisherControl'
import { LiveNavigationGuard } from './LiveNavigationGuard'
import { clearAudioPublisherClientState } from './audio-publisher'
import {
  beginLiveClassEnd,
  startLiveClassEndReconciliation,
  type EndFailureResolution,
} from './live-end'
import { LiveTranscriptPanel } from './LiveTranscriptPanel'
import { initialLiveTranscriptState, liveTranscriptReducer } from './live-state'
import { liveTranscriptKeys, liveTranscriptQueryOptions } from './queries'

interface CommonLiveClassProps {
  session: LectureSession
  courseTitle: string
  refreshWarning?: ReactNode
}

interface ProfessorLiveClassProps extends CommonLiveClassProps {
  onStartVoiceAnswer: (target: AnswerTarget) => void
  answerCapturePending: boolean
  answerCaptureError?: string | null
  onEnd: () => Promise<unknown>
  resolveEndFailure: () => Promise<EndFailureResolution>
  endPending: boolean
  endError?: string | null
  onRename: (title: string) => Promise<unknown>
  renamePending: boolean
  renameError?: string | null
}

interface LiveClassRoomProps extends CommonLiveClassProps {
  professor: boolean
  onStartVoiceAnswer?: (target: AnswerTarget) => void
  answerCapturePending?: boolean
  answerCaptureError?: string | null
  onEnd?: () => Promise<unknown>
  resolveEndFailure?: () => Promise<EndFailureResolution>
  endPending?: boolean
  endError?: string | null
  onRename?: (title: string) => Promise<unknown>
  renamePending?: boolean
  renameError?: string | null
}

export function ProfessorLiveClassView(props: ProfessorLiveClassProps) {
  return <LiveClassRoom {...props} professor />
}

export function StudentLiveClassView(props: CommonLiveClassProps) {
  return <LiveClassRoom {...props} professor={false} />
}

function connectionCopy(state: RealtimeConnectionState | 'resyncing') {
  switch (state) {
    case 'connected':
      return '수업 변경 알림 연결됨'
    case 'resyncing':
      return '저장된 수업 내용 다시 확인 중'
    case 'reconnecting':
      return '수업 변경 알림 재연결 중'
    case 'stopped':
      return '수업 변경 알림 연결 종료됨'
    default:
      return '수업 변경 알림 연결 준비 중'
  }
}

function formatStartedAt(value: string | null) {
  return value
    ? new Intl.DateTimeFormat('ko-KR', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(value))
    : '시작 시각 확인 중'
}

function LiveClassRoom({
  session,
  courseTitle,
  professor,
  refreshWarning,
  onStartVoiceAnswer,
  answerCapturePending = false,
  answerCaptureError,
  onEnd,
  resolveEndFailure,
  endPending = false,
  endError,
  onRename,
  renamePending = false,
  renameError,
}: LiveClassRoomProps) {
  const queryClient = useQueryClient()
  const [transcript, dispatch] = useReducer(
    liveTranscriptReducer,
    initialLiveTranscriptState,
  )
  const [connectionState, setConnectionState] =
    useState<RealtimeConnectionState>('connecting')
  const [transcriptSyncing, setTranscriptSyncing] = useState(false)
  const [endOpen, setEndOpen] = useState(false)
  const [endSafetyChecking, setEndSafetyChecking] = useState(false)
  const [endSafetyError, setEndSafetyError] = useState(false)
  const [endLifecyclePending, setEndLifecyclePending] = useState(false)
  const [endResolutionPending, setEndResolutionPending] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [nextTitle, setNextTitle] = useState(session.title)
  const [captureFocusRequest, setCaptureFocusRequest] = useState(0)
  const [recordingStream, setRecordingStream] = useState<MediaStream | null>(
    null,
  )
  const [recordingClientStreamId, setRecordingClientStreamId] = useState<
    string | null
  >(null)
  const [audioActive, setAudioActive] = useState(false)
  const [recordingActive, setRecordingActive] = useState(false)
  const captureAlertRef = useRef<HTMLDivElement>(null)
  const audioControlRef = useRef<LiveAudioPublisherControlHandle>(null)
  const recordingControlRef = useRef<LocalRecordingPanelHandle>(null)
  const resolveEndFailureRef = useRef(resolveEndFailure)
  const syncGeneration = useRef(0)
  const timeline = useQuery(liveTranscriptQueryOptions(session.id))
  const answers = useQuery({
    ...sessionAnswersQueryOptions(session.id),
    enabled: professor,
  })

  useEffect(() => {
    resolveEndFailureRef.current = resolveEndFailure
  }, [resolveEndFailure])

  useEffect(() => {
    if (!endResolutionPending) return
    return startLiveClassEndReconciliation(
      () =>
        resolveEndFailureRef.current?.() ?? Promise.resolve('unknown' as const),
      () => audioControlRef.current,
      () => recordingControlRef.current,
      () => setEndResolutionPending(false),
    )
  }, [endResolutionPending, session.id])

  useEffect(() => {
    if (timeline.data) dispatch({ type: 'hydrate', data: timeline.data })
  }, [timeline.data])

  const syncTranscript = useCallback(async () => {
    const generation = ++syncGeneration.current
    setTranscriptSyncing(true)
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
    await queryClient.cancelQueries({
      queryKey: liveTranscriptKeys.session(session.id),
    })
    try {
      const restored = await queryClient.fetchQuery({
        ...liveTranscriptQueryOptions(session.id),
        staleTime: 0,
      })
      if (generation === syncGeneration.current) {
        dispatch({ type: 'hydrate', data: restored })
      }
    } catch {
      // Keep the durable timeline and the explicit resync/error presentation.
    } finally {
      if (generation === syncGeneration.current) setTranscriptSyncing(false)
    }
  }, [queryClient, session.id])

  const onEvent = useCallback(
    (event: RealtimeEvent) => {
      dispatch({ type: 'event', event })
      if (event.type === 'transcript.final') {
        void queryClient.invalidateQueries({
          queryKey: liveTranscriptKeys.session(session.id),
          refetchType: 'none',
        })
      }
      if (event.type === 'transcript.version.updated') {
        void syncTranscript()
      }
    },
    [queryClient, session.id, syncTranscript],
  )
  const onConnection = useCallback((next: RealtimeConnectionState) => {
    setConnectionState(next)
  }, [])

  useSessionRealtime({
    sessionId: session.id,
    courseId: session.course_id,
    enabled: true,
    onEvent,
    onResyncRequired: syncTranscript,
    onConnectionState: onConnection,
  })

  useEffect(() => {
    return () => {
      const canonical = queryClient.getQueryData<LectureSession>(
        courseKeys.session(session.id),
      )
      if (canonical && canonical.status !== 'LIVE') {
        clearAudioPublisherClientState(session.id)
        purgeLivePersonalAiClientState(queryClient, session.id)
      }
    }
  }, [queryClient, session.id])

  const capturingAnswer = answers.data?.items.find(
    (answer) => answer.status === 'CAPTURING',
  )
  const captureGate = !professor
    ? 'clear'
    : answers.isPending || answerCapturePending || endSafetyChecking
      ? 'checking'
      : answers.isError || endSafetyError
        ? 'error'
        : capturingAnswer
          ? 'active'
          : 'clear'
  const answerControlsBlocked =
    captureGate !== 'clear' ||
    answerCapturePending ||
    endPending ||
    endSafetyChecking
  const endDialogOpen = endOpen && captureGate === 'clear'
  const endInteractionPending = endLifecyclePending || endResolutionPending

  useEffect(() => {
    if (captureFocusRequest > 0) captureAlertRef.current?.focus()
  }, [captureFocusRequest])

  async function requestEndDialog() {
    if (captureGate === 'active' || captureGate === 'checking') {
      setCaptureFocusRequest((current) => current + 1)
      return
    }
    setEndSafetyChecking(true)
    setEndSafetyError(false)
    const result = await answers.refetch()
    setEndSafetyChecking(false)
    const active = result.data?.items.some(
      (answer) => answer.status === 'CAPTURING',
    )
    if (result.isError || active) {
      setEndSafetyError(result.isError)
      setCaptureFocusRequest((current) => current + 1)
      return
    }
    setEndOpen(true)
  }

  return (
    <section className="live-session-page" aria-labelledby="live-session-title">
      <header className="live-session-header">
        <div className="live-session-header__copy">
          <div className="live-session-header__topline">
            <span className="status-chip status-chip--live">LIVE</span>
            <span>{professor ? '교수자 수업 운영' : '학생 수업 참여'}</span>
          </div>
          <p className="eyebrow">{courseTitle}</p>
          <h1 id="live-session-title">{session.title}</h1>
          <p>확정 Transcript, 익명 질문과 개인 AI를 한 흐름에서 확인합니다.</p>
          <dl className="live-session-header__meta">
            <div>
              <dt>수업 날짜</dt>
              <dd>{session.lecture_date}</dd>
            </div>
            <div>
              <dt>시작</dt>
              <dd>{formatStartedAt(session.started_at)}</dd>
            </div>
          </dl>
        </div>
        <div className="live-session-header__actions">
          {professor && onRename && (
            <Button
              variant="secondary"
              onClick={() => {
                setNextTitle(session.title)
                setRenameOpen(true)
              }}
            >
              제목 수정
            </Button>
          )}
          {professor && onEnd && (
            <Button
              variant="danger"
              disabled={
                endPending ||
                endInteractionPending ||
                captureGate === 'checking'
              }
              onClick={() => void requestEndDialog()}
            >
              {endPending
                ? '종료 중…'
                : endInteractionPending
                  ? '종료 결과 확인 중…'
                  : captureGate === 'checking'
                    ? 'Answer 확인 중…'
                    : '수업 종료'}
            </Button>
          )}
          <Link
            className="button button--ghost live-session-header__back"
            to={`/courses/${session.course_id}`}
          >
            Course로 돌아가기
          </Link>
        </div>
      </header>

      {refreshWarning}

      <div
        className={`live-session-connection live-session-connection--${connectionState}`}
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <span aria-hidden="true" />
        <strong>{connectionCopy(connectionState)}</strong>
        <p>
          {transcriptSyncing
            ? '저장된 Transcript를 다시 확인 중입니다. 기존 확정 내용은 유지됩니다.'
            : '연결이 흔들려도 저장된 Transcript와 질문은 화면에 유지됩니다.'}
        </p>
      </div>

      {professor && (
        <section
          className="live-professor-operations"
          aria-label="교수자 음성 및 녹음 운영"
        >
          <div className="panel live-professor-operation">
            <div>
              <p className="eyebrow">Live audio</p>
              <h2>교수자 마이크</h2>
              <p>실시간 STT 전송 상태이며 로컬 원본 녹음과 독립적입니다.</p>
            </div>
            <LiveAudioPublisherControl
              ref={audioControlRef}
              sessionId={session.id}
              onActivityChange={setAudioActive}
              onMediaStream={(stream, clientStreamId) => {
                setRecordingStream(stream)
                setRecordingClientStreamId(clientStreamId)
              }}
            />
          </div>
          <LocalRecordingPanel
            ref={recordingControlRef}
            sessionId={session.id}
            stream={recordingStream}
            clientStreamId={recordingClientStreamId}
            sessionStatus="LIVE"
            onActivityChange={setRecordingActive}
          />
        </section>
      )}

      {professor && captureGate !== 'clear' && (
        <div
          ref={captureAlertRef}
          className="live-capture-gate"
          role="alert"
          tabIndex={-1}
        >
          <strong>
            {captureGate === 'active'
              ? '진행 중인 음성 Answer를 먼저 완료하거나 취소해 주세요.'
              : captureGate === 'checking'
                ? 'Answer 상태를 확인한 뒤 수업을 종료할 수 있습니다.'
                : 'Answer 상태를 확인하지 못해 안전하게 종료를 막았습니다.'}
          </strong>
          {captureGate === 'error' && (
            <Button
              variant="secondary"
              disabled={answers.isFetching || endSafetyChecking}
              onClick={() => void requestEndDialog()}
            >
              {answers.isFetching || endSafetyChecking
                ? '상태 확인 중…'
                : 'Answer 상태 다시 확인'}
            </Button>
          )}
        </div>
      )}

      {answerCaptureError && (
        <p className="form-error" role="alert">
          {answerCaptureError}
        </p>
      )}

      <div
        className={`live-workspace ${
          professor ? 'live-workspace--professor' : 'live-workspace--student'
        }`}
      >
        <LiveTranscriptPanel
          transcript={transcript}
          connectionState={connectionState}
          loading={timeline.isPending}
          error={timeline.isError}
          retrying={timeline.isFetching}
          onRetry={() => void syncTranscript()}
        />
        <div className="live-rail">
          <QuestionPanel
            sessionId={session.id}
            student={!professor}
            onStartVoiceAnswer={
              professor && onStartVoiceAnswer
                ? (target) => {
                    if (!answerControlsBlocked) onStartVoiceAnswer(target)
                  }
                : undefined
            }
            answerCapturePending={answerControlsBlocked}
          />
        </div>
        <div className="live-cluster-list-workspace">
          <QuestionClusterList
            sessionId={session.id}
            onStartVoiceAnswer={
              professor && onStartVoiceAnswer
                ? (target) => {
                    if (!answerControlsBlocked) onStartVoiceAnswer(target)
                  }
                : undefined
            }
            answerCapturePending={answerControlsBlocked}
          />
        </div>
        <div className="live-ai-workspace">
          <PersonalAiPanel sessionId={session.id} mode="LIVE" />
        </div>
        {professor && (
          <div className="live-professor-support">
            <AnswerPanel
              sessionId={session.id}
              professor
              sessionStatus="LIVE"
            />
            <MaterialPanel
              sessionId={session.id}
              professor
              sessionStatus="LIVE"
            />
          </div>
        )}
      </div>

      {professor && onRename && (
        <Dialog
          open={renameOpen}
          title="class 제목 수정"
          description="비워 저장하면 생성 시각 기준의 서버 자동 제목으로 돌아갑니다."
          onOpenChange={(open) => {
            if (!renamePending) setRenameOpen(open)
          }}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={renamePending}
                onClick={() => setRenameOpen(false)}
              >
                취소
              </Button>
              <Button
                disabled={renamePending}
                onClick={async () => {
                  try {
                    await onRename(nextTitle)
                    setRenameOpen(false)
                  } catch {
                    // The mutation error remains visible in this dialog.
                  }
                }}
              >
                {renamePending ? '저장 중…' : '제목 저장'}
              </Button>
            </>
          }
        >
          <label htmlFor="live-session-title-input">class 제목</label>
          <input
            id="live-session-title-input"
            value={nextTitle}
            disabled={renamePending}
            onChange={(event) => setNextTitle(event.target.value)}
          />
          {renameError && (
            <p className="form-error" role="alert">
              {renameError}
            </p>
          )}
        </Dialog>
      )}

      {professor && onEnd && (
        <Dialog
          title="수업을 종료할까요?"
          description="Session은 즉시 PROCESSING으로 바뀌고 기록 정리가 시작됩니다."
          open={endDialogOpen}
          onOpenChange={(open) => {
            if (!endPending && !endInteractionPending) setEndOpen(open)
          }}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={endPending || endInteractionPending}
                onClick={() => setEndOpen(false)}
              >
                계속 수업
              </Button>
              <Button
                variant="danger"
                disabled={
                  endPending || endInteractionPending || captureGate !== 'clear'
                }
                onClick={async () => {
                  let unresolved = false
                  setEndLifecyclePending(true)
                  try {
                    await beginLiveClassEnd(
                      onEnd,
                      audioControlRef.current,
                      recordingControlRef.current,
                      resolveEndFailure ?? (async () => 'unknown'),
                      () => {
                        unresolved = true
                        setEndResolutionPending(true)
                      },
                    )
                    setEndLifecyclePending(false)
                  } catch {
                    setEndLifecyclePending(false)
                    if (!unresolved) setEndResolutionPending(false)
                    // The parent keeps the dialog error and refreshes Answer
                    // state only for the documented capture conflict.
                  }
                }}
              >
                {endPending
                  ? '종료 중…'
                  : endInteractionPending
                    ? '종료 결과 확인 중…'
                    : '수업 종료'}
              </Button>
            </>
          }
        >
          <p className="input-hint">
            실시간 음성 전송과 로컬 녹음 마감은 서로 독립적으로 처리됩니다.
          </p>
          {endResolutionPending && (
            <p className="input-hint" role="status">
              종료 요청 결과를 확인할 때까지 음성과 녹음을 일시정지했습니다.
              Session이 LIVE면 자동으로 재개합니다.
            </p>
          )}
          {endError && (
            <p className="form-error" role="alert">
              {endError}
            </p>
          )}
        </Dialog>
      )}

      <LiveNavigationGuard active={audioActive || recordingActive} />
    </section>
  )
}

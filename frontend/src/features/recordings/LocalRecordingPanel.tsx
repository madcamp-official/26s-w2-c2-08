import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { Button } from '../../components/ui/Button'
import { ApiError } from '../../api/errors'
import {
  BrowserRecordingUnsupportedError,
  LocalRecorder,
  RecordingAlreadyFinalizedError,
  RecordingFailedMetaError,
  RecordingInterruptedMetaError,
  RecordingLeaseUnavailableError,
  RecordingStreamConflictError,
  recoverLocalRecording,
  type LocalRecordingRecoveryResult,
} from './local-recorder'
import { getRecordingMeta } from './local-db'
import { abandonRecordingUpload } from './api'
import { uploadLocalRecording } from './uploader'

interface Props {
  sessionId: string
  stream: MediaStream | null
  clientStreamId: string | null
  sessionStatus: 'LIVE' | 'PROCESSING'
  onActivityChange?: (active: boolean) => void
}

export interface LocalRecordingPanelHandle {
  quiesceForEnd: () => Promise<void>
  finalizeRecording: () => Promise<void>
  resumeAfterEndFailure: () => Promise<void>
}

type RecordingPanelState =
  | 'idle'
  | 'recording'
  | 'recording-elsewhere'
  | 'capture-interrupted'
  | 'finalizing'
  | 'finalization-delayed'
  | 'unsupported'
  | 'storage-failed'
  | 'not-recorded'
  | 'uploading'
  | 'uploaded'
  | 'upload-failed'
  | 'uploading-elsewhere'
  | 'expired'

const MAX_FINALIZATION_POLLS = 120

function panelStateForFailure(reason: string | null): RecordingPanelState {
  return reason === 'EMPTY_RECORDING'
    ? 'not-recorded'
    : reason === 'LOCAL_CAPTURE_INTERRUPTED'
      ? 'capture-interrupted'
      : 'storage-failed'
}

export const LocalRecordingPanel = forwardRef<LocalRecordingPanelHandle, Props>(
  function LocalRecordingPanel(
    { sessionId, stream, clientStreamId, sessionStatus, onActivityChange },
    ref,
  ) {
    const recorder = useRef<LocalRecorder | null>(null)
    const stopInitiated = useRef(false)
    const [consented, setConsented] = useState(false)
    const [state, setState] = useState<RecordingPanelState>('idle')
    const [offset, setOffset] = useState(0)
    const [total, setTotal] = useState(0)
    const [error, setError] = useState<string | null>(null)
    const [recordingClosed, setRecordingClosed] = useState(false)
    const [recoveryRun, setRecoveryRun] = useState(0)
    const active =
      state === 'recording' ||
      state === 'finalizing' ||
      state === 'uploading' ||
      state === 'upload-failed'

    useEffect(() => {
      onActivityChange?.(active)
    }, [active, onActivityChange])

    const reflectRecovery = useCallback(
      (result: LocalRecordingRecoveryResult) => {
        if (result.status === 'owned_elsewhere') {
          setState('finalizing')
          return false
        }
        if (result.status === 'missing') {
          setState('not-recorded')
          return false
        }
        if (result.status === 'failed') {
          setState(panelStateForFailure(result.meta.failedReason))
          return false
        }
        setTotal(result.meta.totalBytes)
        setState('idle')
        return true
      },
      [],
    )

    const resumeUpload = useCallback(() => {
      setError(null)
      return uploadLocalRecording(sessionId, (next, nextOffset) => {
        setOffset(nextOffset ?? 0)
        setState(
          next === 'completed'
            ? 'uploaded'
            : next === 'expired'
              ? 'expired'
              : next === 'owned_elsewhere'
                ? 'uploading-elsewhere'
                : next === 'failed'
                  ? 'upload-failed'
                  : 'uploading',
        )
      }).catch((reason) => {
        setState((current) =>
          current === 'expired' ? 'expired' : 'upload-failed',
        )
        setError(
          reason instanceof ApiError
            ? reason.message
            : '녹음 upload를 다시 시작하지 못했습니다.',
        )
      })
    }, [sessionId])

    const finalizeRecording = useCallback(async () => {
      if (stopInitiated.current) {
        await recorder.current?.stop()
        return
      }
      stopInitiated.current = true
      setRecordingClosed(true)
      const current = recorder.current
      setState('finalizing')
      try {
        if (!current) {
          reflectRecovery(await recoverLocalRecording(sessionId))
          return
        }
        const result = await current.stop()
        if (!result) {
          setState('not-recorded')
        } else if (result.failedReason) {
          setState(panelStateForFailure(result.failedReason))
        } else {
          setState('idle')
        }
      } catch {
        setState('storage-failed')
      }
    }, [reflectRecovery, sessionId])

    useImperativeHandle(
      ref,
      () => ({
        quiesceForEnd: async () => {
          await recorder.current?.quiesceForEnd()
        },
        finalizeRecording,
        resumeAfterEndFailure: async () => {
          const resumed = await recorder.current?.resumeAfterEndFailure()
          if (resumed === false) {
            setState('storage-failed')
            setError(
              '수업은 LIVE이지만 로컬 녹음을 재개하지 못했습니다. 실시간 Transcript는 계속 사용할 수 있습니다.',
            )
          }
        },
      }),
      [finalizeRecording],
    )

    useEffect(() => {
      if (sessionStatus !== 'LIVE') return
      void getRecordingMeta(sessionId)
        .then((meta) => {
          if (meta?.finalized) {
            setRecordingClosed(true)
            return
          }
          if (meta?.failedReason) {
            setRecordingClosed(true)
            setState(panelStateForFailure(meta.failedReason))
            return
          }
          if (meta && !meta.failedReason) setConsented(true)
        })
        .catch(() => setState('storage-failed'))
    }, [sessionId, sessionStatus])

    useEffect(() => {
      if (
        !consented ||
        !stream ||
        !clientStreamId ||
        sessionStatus !== 'LIVE' ||
        stopInitiated.current ||
        recorder.current
      )
        return
      const next = new LocalRecorder(() => setState('storage-failed'))
      const recordingStream = stream.clone()
      recorder.current = next
      void next
        .start(sessionId, recordingStream, clientStreamId)
        .then(() => {
          if (!stopInitiated.current) setState('recording')
        })
        .catch((reason) => {
          recorder.current = null
          if (reason instanceof RecordingAlreadyFinalizedError) {
            setRecordingClosed(true)
            setState('idle')
            return
          }
          if (reason instanceof RecordingFailedMetaError) {
            setRecordingClosed(true)
            setState(panelStateForFailure(reason.reason))
            return
          }
          if (reason instanceof RecordingInterruptedMetaError) {
            setRecordingClosed(true)
            setState('capture-interrupted')
            return
          }
          if (reason instanceof RecordingStreamConflictError) {
            setRecordingClosed(true)
            setState('recording-elsewhere')
            return
          }
          setState(
            reason instanceof BrowserRecordingUnsupportedError ||
              reason instanceof RecordingLeaseUnavailableError
              ? 'unsupported'
              : 'storage-failed',
          )
        })
    }, [clientStreamId, consented, sessionId, sessionStatus, stream])
    useEffect(
      () => () => {
        if (recorder.current) {
          void finalizeRecording()
        }
      },
      [finalizeRecording],
    )
    useEffect(() => {
      if (!active) return
      const warn = (event: BeforeUnloadEvent) => {
        event.preventDefault()
        event.returnValue = ''
      }
      window.addEventListener('beforeunload', warn)
      return () => window.removeEventListener('beforeunload', warn)
    }, [active])
    useEffect(() => {
      if (sessionStatus !== 'PROCESSING') return
      let cancelled = false
      let retry: ReturnType<typeof setTimeout> | undefined
      let ownedPolls = 0
      const begin = async () => {
        let result: LocalRecordingRecoveryResult
        try {
          result = await recoverLocalRecording(sessionId)
        } catch {
          if (!cancelled) setState('storage-failed')
          return
        }
        if (cancelled) return
        if (result.status === 'owned_elsewhere') {
          setState('finalizing')
          ownedPolls += 1
          if (ownedPolls >= MAX_FINALIZATION_POLLS) {
            setState('finalization-delayed')
            return
          }
          retry = setTimeout(() => void begin(), 500)
          return
        }
        if (reflectRecovery(result)) {
          void resumeUpload()
          return
        }
        if (result.status === 'missing' || result.status === 'failed') {
          try {
            await abandonRecordingUpload(sessionId)
          } catch (reason) {
            if (!cancelled) {
              setState('upload-failed')
              setError(
                reason instanceof ApiError
                  ? reason.message
                  : '녹음 원본 없음 상태를 서버에 반영하지 못했습니다.',
              )
            }
          }
        }
      }
      void begin()
      return () => {
        cancelled = true
        if (retry) clearTimeout(retry)
      }
    }, [recoveryRun, reflectRecovery, resumeUpload, sessionId, sessionStatus])

    useEffect(() => {
      if (sessionStatus !== 'PROCESSING' || state !== 'uploading-elsewhere')
        return
      let cancelled = false
      let retry: ReturnType<typeof setTimeout> | undefined
      const reacquire = async () => {
        await resumeUpload()
        if (!cancelled) retry = setTimeout(() => void reacquire(), 2_000)
      }
      retry = setTimeout(() => void reacquire(), 2_000)
      return () => {
        cancelled = true
        if (retry) clearTimeout(retry)
      }
    }, [resumeUpload, sessionStatus, state])

    const copy =
      recordingClosed && sessionStatus === 'LIVE' && state === 'idle'
        ? '이 기기의 녹음 원본은 이미 마감되었습니다. 수업 종료 후 업로드되며 같은 class에서 다시 녹음하지 않습니다.'
        : state === 'recording'
          ? '이 브라우저에 녹음 원본을 저장하고 있습니다.'
          : state === 'recording-elsewhere'
            ? '다른 탭이 이 기기의 수업 원본을 녹음하고 있습니다. 이 탭에서는 중복 녹음을 시작하지 않습니다.'
            : state === 'capture-interrupted'
              ? '브라우저 종료나 저장 중단으로 마지막 녹음 조각의 완결성을 확인할 수 없어 원본 업로드를 중단했습니다. 저장된 실시간 Transcript는 유지됩니다.'
              : state === 'finalizing'
                ? '녹음 조각을 마무리하고 있습니다.'
                : state === 'finalization-delayed'
                  ? '다른 탭의 녹음 마감 확인이 지연되고 있습니다. 해당 탭을 확인하거나 상태 확인을 다시 시도하세요.'
                  : state === 'uploading'
                    ? `녹음 원본을 업로드하고 있습니다${total ? ` (${offset}/${total} bytes)` : ''}.`
                    : state === 'uploaded'
                      ? '녹음 원본 업로드가 완료되어 고품질 Transcript 처리가 시작됩니다.'
                      : state === 'unsupported'
                        ? '이 브라우저는 저장 녹음을 지원하지 않습니다. 실시간 Transcript는 별도로 계속 사용할 수 있습니다.'
                        : state === 'storage-failed'
                          ? '로컬 녹음 저장에 실패했습니다. 실시간 Transcript와 질문은 계속 사용할 수 있습니다.'
                          : state === 'not-recorded'
                            ? '이 기기에 업로드할 녹음 원본이 생성되지 않았습니다. 저장된 실시간 Transcript로 후처리를 계속합니다.'
                            : state === 'uploading-elsewhere'
                              ? '다른 탭이 이 기기의 녹음 원본을 업로드하고 있습니다. 이 탭에서는 중복 전송하지 않습니다.'
                              : state === 'expired'
                                ? '녹음 upload 재개 시간이 만료되어 이 원본은 다시 업로드할 수 없습니다. 저장된 실시간 Transcript는 유지됩니다.'
                                : state === 'upload-failed'
                                  ? '네트워크 문제로 녹음 upload가 중단되었습니다. 연결되면 다시 시도하세요.'
                                  : '수업 원본 녹음을 이 브라우저에 저장할 수 있습니다.'
    return (
      <section className="live-local-recording" aria-label="수업 원본 녹음">
        <div>
          <strong>수업 원본 녹음</strong>
          <p role="status">{copy}</p>
        </div>
        {sessionStatus === 'LIVE' && state === 'idle' && !recordingClosed && (
          <label className="recording-consent">
            <input
              type="checkbox"
              checked={consented}
              onChange={(event) => setConsented(event.target.checked)}
            />{' '}
            녹음 원본을 이 기기에 저장하고 수업 종료 후 업로드하는 데
            동의합니다.
          </label>
        )}
        {sessionStatus === 'PROCESSING' && state === 'upload-failed' && (
          <Button
            variant="secondary"
            onClick={() => {
              void resumeUpload()
            }}
          >
            upload 다시 시도
          </Button>
        )}
        {sessionStatus === 'PROCESSING' && state === 'uploading-elsewhere' && (
          <Button
            variant="secondary"
            onClick={() => {
              void resumeUpload()
            }}
          >
            이 탭에서 upload 인계 확인
          </Button>
        )}
        {sessionStatus === 'PROCESSING' && state === 'finalization-delayed' && (
          <Button
            variant="secondary"
            onClick={() => {
              setRecoveryRun((current) => current + 1)
            }}
          >
            마감 상태 다시 확인
          </Button>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </section>
    )
  },
)

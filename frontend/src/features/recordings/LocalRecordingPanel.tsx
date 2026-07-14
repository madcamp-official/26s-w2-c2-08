import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { ApiError } from '../../api/errors'
import {
  BrowserRecordingUnsupportedError,
  LocalRecorder,
} from './local-recorder'
import { getRecordingMeta } from './local-db'
import { uploadLocalRecording } from './uploader'

interface Props {
  sessionId: string
  stream: MediaStream | null
  clientStreamId: string | null
  sessionStatus: 'LIVE' | 'PROCESSING'
}

export function LocalRecordingPanel({
  sessionId,
  stream,
  clientStreamId,
  sessionStatus,
}: Props) {
  const recorder = useRef<LocalRecorder | null>(null)
  const [consented, setConsented] = useState(false)
  const [state, setState] = useState<
    | 'idle'
    | 'recording'
    | 'finalizing'
    | 'unsupported'
    | 'storage-failed'
    | 'uploading'
    | 'uploaded'
    | 'upload-failed'
    | 'expired'
  >('idle')
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const resumeUpload = useCallback(() => {
    setError(null)
    setState('uploading')
    return uploadLocalRecording(sessionId, (next, nextOffset) => {
      setOffset(nextOffset ?? 0)
      setState(
        next === 'completed'
          ? 'uploaded'
          : next === 'expired'
            ? 'expired'
            : next === 'failed'
              ? 'upload-failed'
              : 'uploading',
      )
    }).catch((reason) =>
      setError(
        reason instanceof ApiError
          ? reason.message
          : '녹음 upload를 다시 시작하지 못했습니다.',
      ),
    )
  }, [sessionId])

  useEffect(() => {
    if (sessionStatus !== 'LIVE') return
    void getRecordingMeta(sessionId).then((meta) => {
      if (meta && !meta.finalized && !meta.failedReason) setConsented(true)
    })
  }, [sessionId, sessionStatus])

  useEffect(() => {
    if (
      !consented ||
      !stream ||
      !clientStreamId ||
      sessionStatus !== 'LIVE' ||
      recorder.current
    )
      return
    const next = new LocalRecorder(() => setState('storage-failed'))
    recorder.current = next
    void next
      .start(sessionId, stream, clientStreamId)
      .then(() => setState('recording'))
      .catch((reason) => {
        recorder.current = null
        setState(
          reason instanceof BrowserRecordingUnsupportedError
            ? 'unsupported'
            : 'storage-failed',
        )
      })
  }, [clientStreamId, consented, sessionId, sessionStatus, stream])
  useEffect(
    () => () => {
      if (recorder.current) {
        void recorder.current.stop()
      }
    },
    [],
  )
  useEffect(() => {
    if (sessionStatus !== 'PROCESSING') return
    let cancelled = false
    let retry: ReturnType<typeof setTimeout> | undefined
    const begin = async () => {
      const meta = await getRecordingMeta(sessionId)
      if (cancelled || !meta) return
      if (meta.failedReason) {
        setState('storage-failed')
        return
      }
      if (!meta.finalized) {
        setState('finalizing')
        retry = setTimeout(() => void begin(), 500)
        return
      }
      setTotal(meta.totalBytes)
      void resumeUpload()
    }
    void begin()
    return () => {
      cancelled = true
      if (retry) clearTimeout(retry)
    }
  }, [resumeUpload, sessionId, sessionStatus])
  const copy =
    state === 'recording'
      ? '이 브라우저에 녹음 원본을 저장하고 있습니다.'
      : state === 'finalizing'
        ? '녹음 조각을 마무리하고 있습니다.'
        : state === 'uploading'
          ? `녹음 원본을 업로드하고 있습니다${total ? ` (${offset}/${total} bytes)` : ''}.`
          : state === 'uploaded'
            ? '녹음 원본 업로드가 완료되어 고품질 Transcript 처리가 시작됩니다.'
            : state === 'unsupported'
              ? '이 브라우저는 저장 녹음을 지원하지 않습니다. 실시간 Transcript는 별도로 계속 사용할 수 있습니다.'
              : state === 'storage-failed'
                ? '로컬 녹음 저장에 실패했습니다. 실시간 Transcript와 질문은 계속 사용할 수 있습니다.'
                : state === 'expired'
                  ? '녹음 upload 재개 시간이 만료되었습니다.'
                  : state === 'upload-failed'
                    ? '네트워크 문제로 녹음 upload가 중단되었습니다. 연결되면 다시 시도하세요.'
                    : '수업 원본 녹음을 이 브라우저에 저장할 수 있습니다.'
  return (
    <section className="live-local-recording" aria-label="수업 원본 녹음">
      <div>
        <strong>수업 원본 녹음</strong>
        <p role="status">{copy}</p>
      </div>
      {sessionStatus === 'LIVE' && state === 'idle' && (
        <label className="recording-consent">
          <input
            type="checkbox"
            checked={consented}
            onChange={(event) => setConsented(event.target.checked)}
          />{' '}
          녹음 원본을 이 기기에 저장하고 수업 종료 후 업로드하는 데 동의합니다.
        </label>
      )}
      {sessionStatus === 'PROCESSING' &&
        (state === 'upload-failed' || state === 'expired') && (
          <Button
            variant="secondary"
            onClick={() => {
              void resumeUpload()
            }}
          >
            upload 다시 시도
          </Button>
        )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}

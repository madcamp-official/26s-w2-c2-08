import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { Button } from '../../components/ui/Button'
import { LiveAudioPublisher, type AudioPublisherState } from './audio-publisher'

interface Props {
  sessionId: string
  onMediaStream?: (
    stream: MediaStream | null,
    clientStreamId: string | null,
  ) => void
  onActivityChange?: (active: boolean) => void
}

export interface LiveAudioPublisherControlHandle {
  quiesceForEnd: () => Promise<void>
  commitEnd: () => Promise<void>
  resumeAfterEndFailure: () => Promise<void>
}

const copy: Record<AudioPublisherState, string> = {
  idle: '마이크 전송을 시작하세요.',
  requesting_permission: '마이크 권한을 요청하고 있습니다.',
  connecting: '음성 전송을 연결하고 있습니다.',
  active: '마이크 음성을 전송 중입니다.',
  reconnecting: '음성 전송을 다시 연결하고 있습니다.',
  denied: '마이크 권한이 거부되었습니다.',
  unavailable: '마이크를 사용할 수 없습니다.',
  conflict: '다른 탭에서 시작한 마이크 전송으로 돌아가세요.',
  resume_rejected:
    '이전 음성 전송 위치를 복구할 수 없습니다. 서버 기록을 확인해 주세요.',
  error: '음성 전송 연결에 문제가 있습니다.',
}

export const LiveAudioPublisherControl = forwardRef<
  LiveAudioPublisherControlHandle,
  Props
>(function LiveAudioPublisherControl(
  { sessionId, onMediaStream, onActivityChange },
  ref,
) {
  const publisher = useRef<LiveAudioPublisher | null>(null)
  const activeRef = useRef(false)
  const endWasActive = useRef(false)
  const endQuiescedRef = useRef(false)
  const endQuiescePromise = useRef<Promise<void> | null>(null)
  const [state, setState] = useState<AudioPublisherState>('idle')
  const [message, setMessage] = useState<string | undefined>()
  const [closed, setClosed] = useState(false)
  const [endQuiesced, setEndQuiesced] = useState(false)
  const busy =
    state === 'requesting_permission' ||
    state === 'connecting' ||
    state === 'reconnecting'
  const active = state === 'active' || busy
  useEffect(() => {
    activeRef.current = active
    onActivityChange?.(active)
  }, [active, onActivityChange])
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!activeRef.current) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
      void publisher.current?.destroy()
      publisher.current = null
    }
  }, [sessionId])
  useImperativeHandle(
    ref,
    () => ({
      quiesceForEnd: async () => {
        if (endQuiescedRef.current) {
          await endQuiescePromise.current
          return
        }
        if (activeRef.current) endWasActive.current = true
        if (!endWasActive.current) return
        endQuiescedRef.current = true
        setEndQuiesced(true)
        setMessage('종료 요청을 확인하는 동안 새 음성 전송을 멈췄습니다.')
        const quiescing = (async () => {
          const confirmed = await publisher.current?.stop({
            awaitServer: true,
          })
          if (confirmed === false) {
            setMessage(
              '음성 전송 마감 응답을 확인하지 못했습니다. Session 상태를 확인해 안전하게 재개합니다.',
            )
          }
          onMediaStream?.(null, null)
        })()
        endQuiescePromise.current = quiescing
        try {
          await quiescing
        } finally {
          if (endQuiescePromise.current === quiescing) {
            endQuiescePromise.current = null
          }
        }
      },
      commitEnd: async () => {
        await endQuiescePromise.current
        endWasActive.current = false
        endQuiescedRef.current = false
        setClosed(true)
        setEndQuiesced(false)
        setMessage('수업 종료 요청으로 이 탭의 음성 전송을 마감했습니다.')
        onMediaStream?.(null, null)
      },
      resumeAfterEndFailure: async () => {
        await endQuiescePromise.current
        if (!endWasActive.current || !publisher.current) return
        endWasActive.current = false
        endQuiescedRef.current = false
        setEndQuiesced(false)
        setMessage('Session이 LIVE여서 음성 전송을 다시 연결합니다.')
        await publisher.current.start()
      },
    }),
    [onMediaStream],
  )
  async function toggle() {
    if (closed) return
    if (active) {
      await publisher.current?.stop({ awaitServer: true })
      return
    }
    if (!publisher.current) {
      publisher.current = new LiveAudioPublisher({
        sessionId,
        onState: (value, detail) => {
          setState(value)
          setMessage(detail)
          if (
            value === 'idle' ||
            value === 'denied' ||
            value === 'unavailable' ||
            value === 'conflict' ||
            value === 'resume_rejected' ||
            value === 'error'
          ) {
            onMediaStream?.(null, null)
          }
        },
        onMediaStream: (stream, clientStreamId) =>
          onMediaStream?.(stream, clientStreamId),
      })
    }
    await publisher.current.start()
  }
  return (
    <section className="live-audio-control" aria-label="교수자 마이크 전송">
      <div>
        <strong>실시간 전송</strong>
        <p role="status">{message ?? copy[state]}</p>
      </div>
      <Button
        variant={active ? 'danger' : 'secondary'}
        disabled={
          state === 'requesting_permission' ||
          closed ||
          endQuiesced ||
          state === 'conflict' ||
          state === 'resume_rejected'
        }
        onClick={() => void toggle()}
      >
        {closed
          ? '음성 전송 마감됨'
          : endQuiesced
            ? '종료 상태 확인 중'
            : active
              ? '마이크 전송 중지'
              : state === 'conflict'
                ? '활성 탭에서 계속하기'
                : state === 'resume_rejected'
                  ? '전송 재개 불가'
                  : '마이크 전송 시작'}
      </Button>
    </section>
  )
})

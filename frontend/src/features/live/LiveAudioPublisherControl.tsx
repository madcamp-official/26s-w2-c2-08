import { useEffect, useRef, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { LiveAudioPublisher, type AudioPublisherState } from './audio-publisher'

interface Props {
  sessionId: string
  onMediaStream?: (stream: MediaStream, clientStreamId: string) => void
}

const copy: Record<AudioPublisherState, string> = {
  idle: '마이크 전송을 시작하세요.',
  requesting_permission: '마이크 권한을 요청하고 있습니다.',
  connecting: '음성 전송을 연결하고 있습니다.',
  active: '마이크 음성을 전송 중입니다.',
  reconnecting: '음성 전송을 다시 연결하고 있습니다.',
  denied: '마이크 권한이 거부되었습니다.',
  unavailable: '마이크를 사용할 수 없습니다.',
  conflict: '다른 탭이 마이크를 사용 중입니다.',
  error: '음성 전송 연결에 문제가 있습니다.',
}

export function LiveAudioPublisherControl({ sessionId, onMediaStream }: Props) {
  const publisher = useRef<LiveAudioPublisher | null>(null)
  const [state, setState] = useState<AudioPublisherState>('idle')
  const [message, setMessage] = useState<string | undefined>()
  const busy =
    state === 'requesting_permission' ||
    state === 'connecting' ||
    state === 'reconnecting'
  const active = state === 'active' || busy
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!active) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
      void publisher.current?.stop()
    }
  }, [active])
  async function toggle() {
    if (active) {
      await publisher.current?.stop()
      publisher.current = null
      return
    }
    const next = new LiveAudioPublisher({
      sessionId,
      onState: (value, detail) => {
        setState(value)
        setMessage(detail)
      },
      onMediaStream,
    })
    publisher.current = next
    await next.start()
  }
  return (
    <section className="live-audio-control" aria-label="교수자 마이크 전송">
      <div>
        <strong>교수자 마이크</strong>
        <p role="status">{message ?? copy[state]}</p>
      </div>
      <Button
        variant={active ? 'danger' : 'secondary'}
        disabled={busy}
        onClick={() => void toggle()}
      >
        {active
          ? '마이크 전송 중지'
          : state === 'conflict'
            ? '이 탭에서 다시 시도'
            : '마이크 전송 시작'}
      </Button>
    </section>
  )
}

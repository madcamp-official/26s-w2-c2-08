import { apiUrl } from '../../api/client'
import { createRealtimeTicket } from '../realtime/api'

const SAMPLE_RATE = 16_000
const CHUNK_MS = 500
const SAMPLES_PER_CHUNK = (SAMPLE_RATE * CHUNK_MS) / 1_000

const workletSource = `
class GoalPcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (channel) { const copy = channel.slice(); this.port.postMessage(copy, [copy.buffer]) }
    return true
  }
}
registerProcessor('goal-pcm-capture', GoalPcmCaptureProcessor)
`

async function createCaptureWorklet(context: AudioContext) {
  const source = new Blob([workletSource], { type: 'text/javascript' })
  const url = URL.createObjectURL(source)
  try {
    await context.audioWorklet.addModule(url)
  } finally {
    URL.revokeObjectURL(url)
  }
  return new AudioWorkletNode(context, 'goal-pcm-capture', {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    channelCount: 1,
  })
}

export type AudioPublisherState =
  | 'idle'
  | 'requesting_permission'
  | 'connecting'
  | 'active'
  | 'reconnecting'
  | 'denied'
  | 'unavailable'
  | 'conflict'
  | 'error'

interface AudioSocket {
  readyState: number
  close(): void
  send(data: string | ArrayBuffer): void
  onopen: (() => void) | null
  onclose: (() => void) | null
  onerror: (() => void) | null
  onmessage: ((event: MessageEvent<string>) => void) | null
}

export interface AudioPublisherOptions {
  sessionId: string
  onState: (state: AudioPublisherState, message?: string) => void
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>
  webSocketFactory?: (url: string) => AudioSocket
}

function audioWebSocketUrl(sessionId: string, ticket: string) {
  const url = new URL(
    `/api/v1/ws/sessions/${encodeURIComponent(sessionId)}/audio`,
    apiUrl('/'),
  )
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('ticket', ticket)
  return url.toString()
}

function floatToPcm(samples: Float32Array) {
  const buffer = new ArrayBuffer(samples.length * 2)
  const view = new DataView(buffer)
  samples.forEach((sample, index) => {
    const bounded = Math.max(-1, Math.min(1, sample))
    view.setInt16(
      index * 2,
      bounded < 0 ? bounded * 0x8000 : bounded * 0x7fff,
      true,
    )
  })
  return buffer
}

function audioFrame(
  sequence: number,
  capturedOffsetMs: number,
  pcm: ArrayBuffer,
) {
  const header = new ArrayBuffer(14)
  const view = new DataView(header)
  view.setUint8(0, 1)
  view.setUint8(1, 0)
  view.setUint32(2, sequence, false)
  view.setBigUint64(6, BigInt(capturedOffsetMs), false)
  const frame = new Uint8Array(14 + pcm.byteLength)
  frame.set(new Uint8Array(header))
  frame.set(new Uint8Array(pcm), 14)
  return frame.buffer
}

/** Browser-only PCM publisher. It intentionally keeps no recording bytes; upload is the recording flow's responsibility. */
export class LiveAudioPublisher {
  private context: AudioContext | null = null
  private processor: AudioWorkletNode | null = null
  private silence: GainNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private stream: MediaStream | null = null
  private socket: AudioSocket | null = null
  private sequence = 0
  private receivedThrough: number | null = null
  private startedAt = 0
  private samples: number[] = []
  private stopped = false
  private readonly clientStreamId: string

  constructor(private readonly options: AudioPublisherOptions) {
    const key = `goal:audio-stream:${options.sessionId}`
    const stored = window.sessionStorage.getItem(key)
    this.clientStreamId = stored || crypto.randomUUID()
    window.sessionStorage.setItem(key, this.clientStreamId)
  }

  async start() {
    this.stopped = false
    this.options.onState('requesting_permission')
    try {
      const getUserMedia =
        this.options.getUserMedia ??
        navigator.mediaDevices?.getUserMedia.bind(navigator.mediaDevices)
      if (!getUserMedia) {
        this.options.onState(
          'unavailable',
          '이 브라우저에서는 마이크를 사용할 수 없습니다.',
        )
        return
      }
      this.stream = await getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
    } catch (error) {
      const denied =
        error instanceof DOMException &&
        (error.name === 'NotAllowedError' || error.name === 'SecurityError')
      this.options.onState(
        denied ? 'denied' : 'unavailable',
        denied
          ? '마이크 권한이 거부되었습니다.'
          : '마이크를 사용할 수 없습니다.',
      )
      return
    }
    await this.openSocket()
  }

  async stop() {
    this.stopped = true
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({ type: 'audio.stop', request_id: crypto.randomUUID() }),
      )
    }
    this.socket?.close()
    this.stopCapture()
    this.options.onState('idle')
  }

  private async openSocket() {
    this.options.onState(this.sequence === 0 ? 'connecting' : 'reconnecting')
    try {
      const ticket = await createRealtimeTicket({
        session_id: this.options.sessionId,
        scope: 'SESSION_AUDIO_WRITE',
      })
      if (this.stopped) return
      const factory =
        this.options.webSocketFactory ??
        ((url: string) => new WebSocket(url) as unknown as AudioSocket)
      const socket = factory(
        audioWebSocketUrl(this.options.sessionId, ticket.ticket),
      )
      this.socket = socket
      socket.onopen = () =>
        socket.send(
          JSON.stringify({
            type: 'audio.start',
            request_id: crypto.randomUUID(),
            data: {
              client_stream_id: this.clientStreamId,
              format: {
                encoding: 'PCM_S16LE',
                sample_rate_hz: SAMPLE_RATE,
                channels: 1,
              },
              chunk_duration_ms: CHUNK_MS,
              resume_from_sequence: this.receivedThrough,
            },
          }),
        )
      socket.onmessage = (event) => this.receiveControl(event.data)
      socket.onerror = () => socket.close()
      socket.onclose = () => {
        if (!this.stopped && this.socket === socket) {
          this.stopCapture()
          this.options.onState(
            'error',
            '음성 전송 연결이 끊어졌습니다. 다시 시작해 주세요.',
          )
        }
      }
    } catch {
      this.options.onState(
        'error',
        '음성 전송을 시작하지 못했습니다. 네트워크를 확인해 주세요.',
      )
    }
  }

  private receiveControl(raw: string) {
    let message: Record<string, unknown>
    try {
      message = JSON.parse(raw) as Record<string, unknown>
    } catch {
      return
    }
    if (message.type === 'audio.ready') {
      this.receivedThrough =
        typeof message.last_received_sequence === 'number'
          ? message.last_received_sequence
          : null
      void this.startCapture()
      return
    }
    if (
      message.type === 'audio.ack' &&
      typeof message.received_through === 'number'
    ) {
      this.receivedThrough = message.received_through
      return
    }
    if (
      message.type === 'error' &&
      message.code === 'AUDIO_PUBLISHER_CONFLICT'
    ) {
      this.stopCapture()
      this.options.onState(
        'conflict',
        '다른 탭에서 이미 음성 전송을 사용하고 있습니다.',
      )
      return
    }
    if (message.type === 'audio.resume_rejected') {
      this.stopCapture()
      this.options.onState(
        'error',
        '음성 전송을 다시 연결할 수 없습니다. 새로 시작해 주세요.',
      )
    }
  }

  private async startCapture() {
    if (!this.stream) return
    this.context = new AudioContext({ sampleRate: SAMPLE_RATE })
    await this.context.resume()
    this.source = this.context.createMediaStreamSource(this.stream)
    if (!this.context.audioWorklet) {
      this.options.onState(
        'unavailable',
        '이 브라우저는 AudioWorklet을 지원하지 않습니다.',
      )
      this.stopCapture()
      return
    }
    this.processor = await createCaptureWorklet(this.context)
    this.processor.port.onmessage = (event: MessageEvent<Float32Array>) =>
      this.capture(event.data)
    this.silence = this.context.createGain()
    this.silence.gain.value = 0
    this.startedAt = performance.now()
    this.source.connect(this.processor)
    this.processor.connect(this.silence)
    this.silence.connect(this.context.destination)
    this.options.onState('active')
  }

  private capture(input: Float32Array) {
    if (this.socket?.readyState !== WebSocket.OPEN) return
    this.samples.push(...input)
    while (this.samples.length >= SAMPLES_PER_CHUNK) {
      const chunk = new Float32Array(this.samples.splice(0, SAMPLES_PER_CHUNK))
      const offset = Math.max(
        0,
        Math.round(performance.now() - this.startedAt) - CHUNK_MS,
      )
      this.socket.send(audioFrame(this.sequence++, offset, floatToPcm(chunk)))
    }
  }

  private stopCapture() {
    this.processor?.disconnect()
    this.source?.disconnect()
    this.silence?.disconnect()
    this.stream?.getTracks().forEach((track) => track.stop())
    void this.context?.close()
    this.processor = null
    this.source = null
    this.silence = null
    this.stream = null
    this.context = null
    this.samples = []
  }
}

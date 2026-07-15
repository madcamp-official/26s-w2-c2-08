import { apiUrl } from '../../api/client'
import { ApiError } from '../../api/errors'
import { createRealtimeTicket } from '../realtime/api'

const SAMPLE_RATE = 16_000
const CHUNK_MS = 500
const SAMPLES_PER_CHUNK = (SAMPLE_RATE * CHUNK_MS) / 1_000
const BUFFERED_CHUNK_COUNT = 5_000 / CHUNK_MS
const MAX_RECONNECT_ATTEMPTS = 5
const AUDIO_STOP_ACK_TIMEOUT_MS = 20_000

export class AudioPublisherLeaseUnavailableError extends Error {}

export async function acquireAudioPublisherLease(
  sessionId: string,
): Promise<(() => void) | null> {
  const manager = navigator.locks
  if (!manager) throw new AudioPublisherLeaseUnavailableError()
  return new Promise((resolve) => {
    let resolved = false
    const settle = (release: (() => void) | null) => {
      if (resolved) return
      resolved = true
      resolve(release)
    }
    void manager
      .request(
        `goal:audio-publisher:${sessionId}`,
        { mode: 'exclusive', ifAvailable: true },
        async (lock) => {
          if (!lock) {
            settle(null)
            return
          }
          let release!: () => void
          const held = new Promise<void>((done) => {
            release = done
          })
          let released = false
          settle(() => {
            if (released) return
            released = true
            release()
          })
          await held
        },
      )
      .catch(() => settle(null))
  })
}

function audioStreamStorageKey(sessionId: string) {
  return `goal:audio-stream:${sessionId}`
}

export function clearAudioPublisherClientState(sessionId: string) {
  if (typeof window !== 'undefined') {
    try {
      window.sessionStorage.removeItem(audioStreamStorageKey(sessionId))
    } catch {
      // A restricted storage context must not block the canonical Session transition.
    }
  }
}

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
  | 'resume_rejected'
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

interface BufferedFrame {
  sequence: number
  data: ArrayBuffer
}

/** Fixed five-second resend window required by the audio WebSocket contract. */
export class AudioFrameWindow {
  private frames: BufferedFrame[] = []

  push(frame: BufferedFrame) {
    this.frames.push(frame)
    if (this.frames.length > BUFFERED_CHUNK_COUNT) this.frames.shift()
  }

  acknowledge(receivedThrough: number) {
    this.frames = this.frames.filter(
      (frame) => frame.sequence > receivedThrough,
    )
  }

  pendingAfter(receivedThrough: number | null) {
    return this.frames.filter(
      (frame) => receivedThrough === null || frame.sequence > receivedThrough,
    )
  }

  clear() {
    this.frames = []
  }
}

type Ticket = Awaited<ReturnType<typeof createRealtimeTicket>>

export interface AudioPublisherOptions {
  sessionId: string
  onState: (state: AudioPublisherState, message?: string) => void
  onMediaStream?: (stream: MediaStream, clientStreamId: string) => void
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>
  webSocketFactory?: (url: string) => AudioSocket
  createTicket?: () => Promise<Ticket>
  acquireLease?: (sessionId: string) => Promise<(() => void) | null>
  stopAckTimeoutMs?: number
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

function isTerminalTicketError(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.status === 401 ||
      error.status === 403 ||
      error.status === 404 ||
      error.code === 'SESSION_NOT_LIVE' ||
      error.code === 'SESSION_ACCESS_DENIED')
  )
}

/**
 * Browser-only PCM publisher. A recording consumer must synchronously clone
 * the announced stream; terminal publisher states release the publisher-owned
 * tracks while the independent recording clone can continue.
 */
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
  private captureOffsetBaseMs = 0
  private nextCapturedOffsetMs = 0
  private samples: number[] = []
  private stopped = true
  private reconnectBlocked = false
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private lifecycleGeneration = 0
  private captureStartPromise: Promise<void> | null = null
  private maxInFlight = 1
  private mediaStreamAnnounced = false
  private leaseRelease: (() => void) | null = null
  private leasePromise: Promise<boolean> | null = null
  private destroyed = false
  private sentOnConnection = new Set<number>()
  private stopPromise: Promise<boolean> | null = null
  private stopWaiter: {
    socket: AudioSocket
    settle: (confirmed: boolean) => void
  } | null = null
  private readonly frames = new AudioFrameWindow()
  private readonly clientStreamId: string

  constructor(private readonly options: AudioPublisherOptions) {
    const fallback = crypto.randomUUID()
    let clientStreamId: string = fallback
    try {
      const stored = window.sessionStorage.getItem(
        audioStreamStorageKey(options.sessionId),
      )
      if (stored) {
        try {
          const parsed = JSON.parse(stored) as Record<string, unknown>
          if (typeof parsed.clientStreamId === 'string') {
            clientStreamId = parsed.clientStreamId
          }
          if (
            typeof parsed.nextSequence === 'number' &&
            Number.isSafeInteger(parsed.nextSequence) &&
            parsed.nextSequence >= 0
          ) {
            this.sequence = parsed.nextSequence
          }
          if (
            parsed.receivedThrough === null ||
            (typeof parsed.receivedThrough === 'number' &&
              Number.isSafeInteger(parsed.receivedThrough) &&
              parsed.receivedThrough >= 0)
          ) {
            this.receivedThrough = parsed.receivedThrough as number | null
          }
          if (
            typeof parsed.nextCapturedOffsetMs === 'number' &&
            Number.isSafeInteger(parsed.nextCapturedOffsetMs) &&
            parsed.nextCapturedOffsetMs >= 0
          ) {
            this.nextCapturedOffsetMs = parsed.nextCapturedOffsetMs
          }
        } catch {
          // Migrate the previous plain UUID tab-scoped format.
          clientStreamId = stored
        }
      }
    } catch {
      // sessionStorage can be unavailable in privacy-restricted contexts.
    }
    if (this.nextCapturedOffsetMs === 0 && this.sequence > 0) {
      this.nextCapturedOffsetMs = this.sequence * CHUNK_MS
    }
    this.clientStreamId = clientStreamId
    this.persistStreamState()
  }

  async start() {
    const generation = ++this.lifecycleGeneration
    this.destroyed = false
    this.stopped = false
    this.reconnectBlocked = false
    this.reconnectAttempts = 0
    try {
      if (!(await this.ensureLease())) {
        if (this.stopped || generation !== this.lifecycleGeneration) return
        this.stopped = true
        this.reconnectBlocked = true
        this.options.onState(
          'conflict',
          '다른 탭에서 이 수업의 음성 전송 또는 로컬 녹음을 사용하고 있습니다.',
        )
        return
      }
    } catch (error) {
      if (this.stopped || generation !== this.lifecycleGeneration) return
      this.stopped = true
      this.reconnectBlocked = true
      this.options.onState(
        'unavailable',
        error instanceof AudioPublisherLeaseUnavailableError
          ? '이 브라우저에서는 중복 탭으로부터 녹음을 안전하게 보호할 수 없습니다.'
          : '이 탭의 음성 전송 권한을 확인하지 못했습니다.',
      )
      return
    }
    if (this.stopped || generation !== this.lifecycleGeneration) return
    if (!this.stream) {
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
          this.stopped = true
          return
        }
        const acquired = await getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        })
        if (this.stopped || generation !== this.lifecycleGeneration) {
          acquired.getTracks().forEach((track) => track.stop())
          return
        }
        this.stream = acquired
      } catch (error) {
        if (this.stopped || generation !== this.lifecycleGeneration) return
        const denied =
          error instanceof DOMException &&
          (error.name === 'NotAllowedError' || error.name === 'SecurityError')
        this.options.onState(
          denied ? 'denied' : 'unavailable',
          denied
            ? '마이크 권한이 거부되었습니다.'
            : '마이크를 사용할 수 없습니다.',
        )
        this.stopped = true
        return
      }
    }
    await this.openSocket()
  }

  /**
   * Stops only live PCM publishing. The local recording branch keeps its stream.
   * Interactive/end flows request the server acknowledgement so a later LIVE
   * resume uses the exact durable watermark even when the final frame ACK raced.
   */
  stop({ awaitServer = false }: { awaitServer?: boolean } = {}) {
    if (this.stopPromise) return this.stopPromise
    const run = this.performStop(awaitServer)
    this.stopPromise = run
    return run.finally(() => {
      if (this.stopPromise === run) this.stopPromise = null
    })
  }

  private async performStop(awaitServer: boolean) {
    this.stopped = true
    this.reconnectBlocked = true
    this.clearReconnectTimer()
    const socket = this.socket
    this.stopLiveCapture()
    let serverConfirmed = this.sequence === 0
    if (socket?.readyState === WebSocket.OPEN) {
      serverConfirmed = await this.sendStop(socket, awaitServer)
    } else if (awaitServer && this.sequence > 0) {
      serverConfirmed = false
    }
    this.lifecycleGeneration += 1
    this.socket = null
    try {
      socket?.close()
    } catch {
      // A closing socket must not prevent capture or hardware cleanup.
    }
    this.releasePublisherStream()
    this.options.onState('idle')
    return serverConfirmed
  }

  private sendStop(socket: AudioSocket, awaitServer: boolean) {
    if (!awaitServer) {
      try {
        socket.send(
          JSON.stringify({
            type: 'audio.stop',
            request_id: crypto.randomUUID(),
          }),
        )
      } catch {
        return Promise.resolve(false)
      }
      return Promise.resolve(true)
    }
    return new Promise<boolean>((resolve) => {
      let settled = false
      const timeout = setTimeout(
        () => settle(false),
        this.options.stopAckTimeoutMs ?? AUDIO_STOP_ACK_TIMEOUT_MS,
      )
      const settle = (confirmed: boolean) => {
        if (settled) return
        settled = true
        clearTimeout(timeout)
        if (this.stopWaiter?.socket === socket) this.stopWaiter = null
        resolve(confirmed)
      }
      this.stopWaiter = { socket, settle }
      try {
        socket.send(
          JSON.stringify({
            type: 'audio.stop',
            request_id: crypto.randomUUID(),
          }),
        )
      } catch {
        settle(false)
      }
    })
  }

  /** Component teardown releases the shared hardware stream after recording unmounts. */
  async destroy() {
    this.destroyed = true
    await this.stop()
    await this.leasePromise?.catch(() => false)
    this.leaseRelease?.()
    this.leaseRelease = null
    this.frames.clear()
  }

  private ensureLease() {
    if (this.leaseRelease) return Promise.resolve(true)
    if (this.leasePromise) return this.leasePromise
    const acquire = this.options.acquireLease ?? acquireAudioPublisherLease
    const pending = acquire(this.options.sessionId).then((release) => {
      if (!release) return false
      if (this.destroyed) {
        release()
        return false
      }
      let released = false
      this.leaseRelease = () => {
        if (released) return
        released = true
        release()
      }
      return true
    })
    this.leasePromise = pending
    return pending.finally(() => {
      if (this.leasePromise === pending) this.leasePromise = null
    })
  }

  private async openSocket() {
    if (this.stopped || this.reconnectBlocked) return
    const generation = this.lifecycleGeneration
    this.options.onState(this.sequence === 0 ? 'connecting' : 'reconnecting')
    try {
      const ticket = this.options.createTicket
        ? await this.options.createTicket()
        : await createRealtimeTicket({
            session_id: this.options.sessionId,
            scope: 'SESSION_AUDIO_WRITE',
          })
      if (
        this.stopped ||
        this.reconnectBlocked ||
        generation !== this.lifecycleGeneration
      )
        return
      const factory =
        this.options.webSocketFactory ??
        ((url: string) => new WebSocket(url) as unknown as AudioSocket)
      const socket = factory(
        audioWebSocketUrl(this.options.sessionId, ticket.ticket),
      )
      this.socket = socket
      const isOwnedSocket = () =>
        generation === this.lifecycleGeneration && this.socket === socket
      const isCurrentSocket = () => !this.stopped && isOwnedSocket()
      socket.onopen = () => {
        if (!isCurrentSocket()) return
        try {
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
        } catch {
          try {
            socket.close()
          } catch {
            // The guarded close path will own reconnect scheduling.
          }
        }
      }
      socket.onmessage = (event) => {
        if (isOwnedSocket()) this.receiveControl(event.data)
      }
      socket.onerror = () => {
        if (!isCurrentSocket()) return
        try {
          socket.close()
        } catch {
          this.scheduleReconnect(
            '음성 전송 연결이 끊어졌습니다. 최근 5초 음성을 보관하며 다시 연결합니다.',
          )
        }
      }
      socket.onclose = () => {
        if (!isOwnedSocket()) return
        this.stopWaiter?.settle(false)
        this.socket = null
        if (!this.stopped && !this.reconnectBlocked) {
          this.scheduleReconnect(
            '음성 전송 연결이 끊어졌습니다. 최근 5초 음성을 보관하며 다시 연결합니다.',
          )
        }
      }
    } catch (error) {
      if (this.stopped || generation !== this.lifecycleGeneration) return
      if (isTerminalTicketError(error)) {
        this.reconnectBlocked = true
        this.stopLiveCapture()
        this.releasePublisherStream()
        this.options.onState(
          'error',
          '현재 수업에 음성을 전송할 수 없습니다. 수업 상태와 권한을 확인해 주세요.',
        )
        return
      }
      this.scheduleReconnect(
        '음성 전송 연결을 열지 못했습니다. 최근 음성을 보관하며 다시 시도합니다.',
      )
    }
  }

  private scheduleReconnect(message: string) {
    if (this.stopped || this.reconnectBlocked || this.reconnectTimer) return
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.stopLiveCapture()
      this.releasePublisherStream()
      this.options.onState(
        'error',
        '음성 전송을 다시 연결하지 못했습니다. 로컬 녹음은 별도로 확인해 주세요.',
      )
      return
    }
    this.options.onState('reconnecting', message)
    const delay = Math.min(4_000, 500 * 2 ** this.reconnectAttempts)
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      void this.openSocket()
    }, delay)
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
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
      this.persistStreamState()
      this.maxInFlight =
        typeof message.max_in_flight === 'number' &&
        Number.isSafeInteger(message.max_in_flight) &&
        message.max_in_flight >= 1
          ? message.max_in_flight
          : 1
      this.sentOnConnection.clear()
      if (this.receivedThrough !== null) {
        this.frames.acknowledge(this.receivedThrough)
      }
      if (this.stream && !this.mediaStreamAnnounced) {
        this.mediaStreamAnnounced = true
        this.options.onMediaStream?.(this.stream, this.clientStreamId)
      }
      this.reconnectAttempts = 0
      void this.startCapture()
      this.flushFrames()
      return
    }
    if (
      message.type === 'audio.ack' &&
      typeof message.received_through === 'number'
    ) {
      this.receivedThrough = message.received_through
      this.persistStreamState()
      this.frames.acknowledge(message.received_through)
      for (const sequence of this.sentOnConnection) {
        if (sequence <= message.received_through) {
          this.sentOnConnection.delete(sequence)
        }
      }
      if (this.context && !this.stopped) this.options.onState('active')
      this.flushFrames()
      return
    }
    if (message.type === 'audio.stopped') {
      this.receivedThrough =
        typeof message.last_received_sequence === 'number'
          ? message.last_received_sequence
          : null
      this.persistStreamState()
      if (this.receivedThrough !== null) {
        this.frames.acknowledge(this.receivedThrough)
      }
      this.stopWaiter?.settle(true)
      return
    }
    if (
      message.type === 'error' &&
      message.code === 'AUDIO_PUBLISHER_CONFLICT'
    ) {
      this.reconnectBlocked = true
      this.stopLiveCapture()
      this.releasePublisherStream()
      this.options.onState(
        'conflict',
        '다른 탭에서 이미 음성 전송을 사용하고 있습니다. 음성 전송을 시작한 탭으로 돌아가세요.',
      )
      this.socket?.close()
      return
    }
    if (message.type === 'audio.resume_rejected') {
      this.reconnectBlocked = true
      this.stopLiveCapture()
      this.releasePublisherStream()
      this.options.onState(
        'resume_rejected',
        '이전 음성 sequence를 복구할 수 없습니다. 누락 구간은 서버 기록에서 별도로 표시됩니다.',
      )
      this.socket?.close()
      return
    }
    if (message.type === 'error' && message.code === 'STT_UNAVAILABLE') {
      this.options.onState(
        'active',
        '실시간 음성 인식 전달이 지연되고 있습니다. 음성 연결과 로컬 녹음은 유지됩니다.',
      )
    }
  }

  private startCapture(): Promise<void> {
    const pending = this.captureStartPromise
    if (pending) {
      return pending.then(() => {
        if (!this.stopped && !this.context) return this.startCapture()
      })
    }
    const run = this.initializeCapture()
    this.captureStartPromise = run
    return run.finally(() => {
      if (this.captureStartPromise === run) this.captureStartPromise = null
    })
  }

  private async initializeCapture() {
    if (!this.stream || this.stopped) return
    if (this.context && this.processor) {
      this.options.onState('active')
      return
    }
    const generation = this.lifecycleGeneration
    const stream = this.stream
    let context: AudioContext | null = null
    let source: MediaStreamAudioSourceNode | null = null
    let processor: AudioWorkletNode | null = null
    let silence: GainNode | null = null
    try {
      context = new AudioContext({ sampleRate: SAMPLE_RATE })
      await context.resume()
      if (this.stopped || generation !== this.lifecycleGeneration) {
        await context.close()
        return
      }
      if (!context.audioWorklet) {
        this.reconnectBlocked = true
        const socket = this.socket
        this.socket = null
        try {
          socket?.close()
        } catch {
          // Capture failure state remains authoritative for the retry button.
        }
        this.options.onState(
          'unavailable',
          '이 브라우저는 AudioWorklet을 지원하지 않습니다.',
        )
        await context.close()
        this.releasePublisherStream()
        return
      }
      source = context.createMediaStreamSource(stream)
      processor = await createCaptureWorklet(context)
      if (this.stopped || generation !== this.lifecycleGeneration) {
        processor.disconnect()
        source.disconnect()
        await context.close()
        return
      }
      processor.port.onmessage = (event: MessageEvent<Float32Array>) =>
        this.capture(event.data)
      silence = context.createGain()
      silence.gain.value = 0
      if (this.startedAt === 0) {
        this.startedAt = performance.now()
        this.captureOffsetBaseMs = this.nextCapturedOffsetMs
      }
      source.connect(processor)
      processor.connect(silence)
      silence.connect(context.destination)
      this.context = context
      this.source = source
      this.processor = processor
      this.silence = silence
      this.options.onState('active')
    } catch {
      processor?.disconnect()
      source?.disconnect()
      silence?.disconnect()
      if (context) void context.close()
      if (this.stopped || generation !== this.lifecycleGeneration) return
      this.reconnectBlocked = true
      const socket = this.socket
      this.socket = null
      try {
        socket?.close()
      } catch {
        // The unavailable state remains actionable even if close throws.
      }
      this.stopLiveCapture()
      this.releasePublisherStream()
      this.options.onState(
        'unavailable',
        '브라우저 음성 처리기를 시작하지 못했습니다. 로컬 녹음 상태를 별도로 확인해 주세요.',
      )
    }
  }

  private capture(input: Float32Array) {
    this.samples.push(...input)
    while (this.samples.length >= SAMPLES_PER_CHUNK) {
      const chunk = new Float32Array(this.samples.splice(0, SAMPLES_PER_CHUNK))
      const offset = Math.max(
        this.nextCapturedOffsetMs,
        this.captureOffsetBaseMs +
          Math.round(performance.now() - this.startedAt) -
          CHUNK_MS,
      )
      const sequence = this.sequence++
      this.nextCapturedOffsetMs = offset + CHUNK_MS
      this.persistStreamState()
      this.frames.push({
        sequence,
        data: audioFrame(sequence, offset, floatToPcm(chunk)),
      })
    }
    this.flushFrames()
  }

  private flushFrames() {
    const socket = this.socket
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    const available = Math.max(0, this.maxInFlight - this.sentOnConnection.size)
    const frames = this.frames
      .pendingAfter(this.receivedThrough)
      .filter((frame) => !this.sentOnConnection.has(frame.sequence))
      .slice(0, available)
    try {
      for (const frame of frames) {
        socket.send(frame.data)
        this.sentOnConnection.add(frame.sequence)
      }
    } catch {
      socket.close()
    }
  }

  private stopLiveCapture() {
    this.processor?.disconnect()
    this.source?.disconnect()
    this.silence?.disconnect()
    void this.context?.close()
    this.processor = null
    this.source = null
    this.silence = null
    this.context = null
    this.samples = []
    this.sentOnConnection.clear()
  }

  private releasePublisherStream() {
    if (!this.stream) return
    this.stream.getTracks().forEach((track) => track.stop())
    this.stream = null
    this.mediaStreamAnnounced = false
  }

  private persistStreamState() {
    try {
      window.sessionStorage.setItem(
        audioStreamStorageKey(this.options.sessionId),
        JSON.stringify({
          clientStreamId: this.clientStreamId,
          nextSequence: this.sequence,
          receivedThrough: this.receivedThrough,
          nextCapturedOffsetMs: this.nextCapturedOffsetMs,
        }),
      )
    } catch {
      // In-memory reconnect remains available when storage is blocked.
    }
  }
}

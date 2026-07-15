import { apiUrl } from '../../api/client'
import { ApiError } from '../../api/errors'

import type { RealtimeTicket } from './api'

const reconnectDelays = [0, 1_000, 2_000, 5_000, 10_000, 30_000]
const maxSeenEventIds = 200

export interface RealtimeEvent {
  event_id: string
  type: string
  session_id: string
  cursor: string | null
  resource_version: number | null
  data: Record<string, unknown>
}

interface WebSocketLike {
  close(): void
  onclose: (() => void) | null
  onerror: (() => void) | null
  onmessage: ((event: MessageEvent<string>) => void) | null
  onopen: (() => void) | null
}

export type WebSocketFactory = (url: string) => WebSocketLike
export type RealtimeConnectionState =
  'connecting' | 'connected' | 'reconnecting' | 'stopped'

export function realtimeWebSocketUrl(
  sessionId: string,
  ticket: string,
): string {
  const url = new URL(
    `/api/v1/ws/sessions/${encodeURIComponent(sessionId)}`,
    apiUrl('/'),
  )
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('ticket', ticket)
  return url.toString()
}

function isRealtimeEvent(value: unknown): value is RealtimeEvent {
  if (!value || typeof value !== 'object') return false
  const event = value as Partial<RealtimeEvent>
  return (
    typeof event.event_id === 'string' &&
    typeof event.type === 'string' &&
    typeof event.session_id === 'string' &&
    (typeof event.cursor === 'string' || event.cursor === null) &&
    !!event.data &&
    typeof event.data === 'object'
  )
}

export interface RealtimeSessionClientOptions {
  sessionId: string
  createTicket: (resumeCursor: string | null) => Promise<RealtimeTicket>
  onEvent: (event: RealtimeEvent) => void
  onResyncRequired: () => void
  onConnectionState?: (state: RealtimeConnectionState) => void
  webSocketFactory?: WebSocketFactory
}

export class RealtimeSessionClient {
  private readonly seenEventIds = new Set<string>()
  private readonly webSocketFactory: WebSocketFactory
  private attempt = 0
  private cursor: string | null = null
  private reconnectTimer: number | null = null
  private socket: WebSocketLike | null = null
  private stopped = false

  constructor(private readonly options: RealtimeSessionClientOptions) {
    this.webSocketFactory =
      options.webSocketFactory ?? ((url) => new WebSocket(url) as WebSocketLike)
  }

  start() {
    this.stopped = false
    this.options.onConnectionState?.('connecting')
    this.scheduleReconnect()
  }

  stop() {
    this.stopped = true
    this.options.onConnectionState?.('stopped')
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.socket?.close()
    this.socket = null
  }

  private scheduleReconnect() {
    if (this.stopped || this.reconnectTimer !== null) return
    const delay =
      reconnectDelays[Math.min(this.attempt, reconnectDelays.length - 1)]
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      void this.connect()
    }, delay)
  }

  private async connect() {
    if (this.stopped) return
    try {
      this.options.onConnectionState?.(
        this.attempt === 0 ? 'connecting' : 'reconnecting',
      )
      const ticket = await this.options.createTicket(this.cursor)
      if (this.stopped) return
      const socket = this.webSocketFactory(
        realtimeWebSocketUrl(this.options.sessionId, ticket.ticket),
      )
      this.socket = socket
      socket.onopen = () => {
        this.attempt = 0
        this.options.onConnectionState?.('connected')
      }
      socket.onmessage = (message) => this.receive(message.data)
      socket.onerror = () => socket.close()
      socket.onclose = () => {
        if (this.socket === socket) this.socket = null
        if (!this.stopped) {
          this.attempt += 1
          this.options.onConnectionState?.('reconnecting')
          this.scheduleReconnect()
        }
      }
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403 || error.status === 404)
      ) {
        this.stopped = true
        this.options.onConnectionState?.('stopped')
        return
      }
      this.attempt += 1
      this.scheduleReconnect()
    }
  }

  private receive(rawMessage: string) {
    let parsed: unknown
    try {
      parsed = JSON.parse(rawMessage)
    } catch {
      return
    }
    if (
      !isRealtimeEvent(parsed) ||
      parsed.session_id !== this.options.sessionId
    )
      return
    if (this.seenEventIds.has(parsed.event_id)) return
    this.seenEventIds.add(parsed.event_id)
    if (this.seenEventIds.size > maxSeenEventIds) {
      const oldest = this.seenEventIds.values().next().value
      if (oldest) this.seenEventIds.delete(oldest)
    }
    if (parsed.cursor) this.cursor = parsed.cursor
    if (parsed.type === 'resync.required') {
      this.cursor = null
      this.options.onResyncRequired()
      return
    }
    this.options.onEvent(parsed)
  }
}

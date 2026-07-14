import { afterEach, describe, expect, it, vi } from 'vitest'

import { RealtimeSessionClient, type WebSocketFactory } from './client'

class FakeWebSocket {
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onopen: (() => void) | null = null

  close() {
    this.onclose?.()
  }

  open() {
    this.onopen?.()
  }

  receive(event: object) {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>)
  }
}

afterEach(() => vi.useRealTimers())

describe('RealtimeSessionClient', () => {
  it('deduplicates events, resumes from the latest cursor, and clears it after resync', async () => {
    vi.useFakeTimers()
    const sockets: FakeWebSocket[] = []
    const requestedCursors: Array<string | null> = []
    const received: string[] = []
    const resync = vi.fn()
    const factory: WebSocketFactory = () => {
      const socket = new FakeWebSocket()
      sockets.push(socket)
      return socket
    }
    const client = new RealtimeSessionClient({
      sessionId: 'session-1',
      createTicket: async (resumeCursor) => {
        requestedCursors.push(resumeCursor)
        return {
          ticket: `ticket-${requestedCursors.length}`,
          session_id: 'session-1',
          scope: 'SESSION_EVENTS_READ',
          expires_at: '2026-07-14T00:01:00Z',
        }
      },
      onEvent: (event) => received.push(event.event_id),
      onResyncRequired: resync,
      webSocketFactory: factory,
    })

    client.start()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0]?.open()
    sockets[0]?.receive({
      event_id: 'event-1',
      type: 'session.updated',
      session_id: 'session-1',
      cursor: 'cursor-1',
      resource_version: 2,
      data: {},
    })
    sockets[0]?.receive({
      event_id: 'event-1',
      type: 'session.updated',
      session_id: 'session-1',
      cursor: 'cursor-1',
      resource_version: 2,
      data: {},
    })
    expect(received).toEqual(['event-1'])

    sockets[0]?.close()
    await vi.advanceTimersByTimeAsync(1_000)
    expect(requestedCursors).toEqual([null, 'cursor-1'])
    sockets[1]?.open()
    sockets[1]?.receive({
      event_id: 'event-resync',
      type: 'resync.required',
      session_id: 'session-1',
      cursor: null,
      resource_version: null,
      data: { reason: 'CURSOR_UNKNOWN' },
    })
    expect(resync).toHaveBeenCalledOnce()

    sockets[1]?.close()
    await vi.advanceTimersByTimeAsync(1_000)
    expect(requestedCursors).toEqual([null, 'cursor-1', null])
    client.stop()
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../api/errors'
import {
  AudioFrameWindow,
  LiveAudioPublisher,
  type AudioPublisherState,
} from './audio-publisher'

function frame(sequence: number) {
  return { sequence, data: new ArrayBuffer(1) }
}

describe('AudioFrameWindow', () => {
  it('keeps only the contract five-second resend window', () => {
    const window = new AudioFrameWindow()
    for (let sequence = 0; sequence < 12; sequence += 1) {
      window.push(frame(sequence))
    }

    expect(window.pendingAfter(null).map((item) => item.sequence)).toEqual([
      2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
    ])
  })

  it('removes acknowledged frames and returns only later sequences', () => {
    const window = new AudioFrameWindow()
    for (let sequence = 0; sequence < 5; sequence += 1) {
      window.push(frame(sequence))
    }
    window.acknowledge(2)

    expect(window.pendingAfter(2).map((item) => item.sequence)).toEqual([3, 4])
  })
})

describe('LiveAudioPublisher reconnect lifecycle', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: {
        request: vi.fn(
          async (
            _name: string,
            _options: LockOptions,
            callback: (lock: Lock | null) => Promise<void>,
          ) => callback({ name: 'test-lock', mode: 'exclusive' } as Lock),
        ),
      } as unknown as LockManager,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    window.sessionStorage.clear()
  })

  it('reconnects without stopping the stream shared with local recording', async () => {
    vi.useFakeTimers()
    const stopTrack = vi.fn()
    const stream = {
      getTracks: () => [{ stop: stopTrack }],
    } as unknown as MediaStream
    const sockets: Array<{
      readyState: number
      close: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    }> = []
    const createTicket = vi.fn(
      async () =>
        ({
          ticket: 'ticket',
        }) as never,
    )
    const states: AudioPublisherState[] = []
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket,
      webSocketFactory: () => {
        const socket = {
          readyState: WebSocket.OPEN,
          close: vi.fn(),
          send: vi.fn(),
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
        }
        sockets.push(socket)
        return socket
      },
      onState: (state) => states.push(state),
    })

    await publisher.start()
    expect(sockets).toHaveLength(1)
    sockets[0]?.onclose?.()
    expect(states.at(-1)).toBe('reconnecting')
    expect(stopTrack).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(500)
    expect(createTicket).toHaveBeenCalledTimes(2)
    expect(sockets).toHaveLength(2)
    expect(stopTrack).not.toHaveBeenCalled()

    await publisher.stop()
    expect(stopTrack).toHaveBeenCalledTimes(1)
    await publisher.destroy()
    expect(stopTrack).toHaveBeenCalledTimes(1)
  })

  it('releases a late permission result after the LIVE component is destroyed', async () => {
    const stopTrack = vi.fn()
    const stream = {
      getTracks: () => [{ stop: stopTrack }],
    } as unknown as MediaStream
    let resolvePermission: ((stream: MediaStream) => void) | undefined
    const permission = new Promise<MediaStream>((resolve) => {
      resolvePermission = resolve
    })
    const getUserMedia = vi.fn(() => permission)
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia,
      createTicket: vi.fn(),
      onState: vi.fn(),
    })

    const starting = publisher.start()
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1))
    await publisher.destroy()
    resolvePermission?.(stream)
    await starting

    expect(stopTrack).toHaveBeenCalledTimes(1)
  })

  it('keeps stop cleanup best-effort when the socket send races with close', async () => {
    const stopTrack = vi.fn()
    const stream = {
      getTracks: () => [{ stop: stopTrack }],
    } as unknown as MediaStream
    const socket = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(() => {
        throw new Error('socket closed')
      }),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null,
    }
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      onState: vi.fn(),
    })

    await publisher.start()
    await expect(publisher.stop()).resolves.toBe(false)
    await publisher.destroy()

    expect(socket.close).toHaveBeenCalled()
    expect(stopTrack).toHaveBeenCalledTimes(1)
  })

  it('waits for audio.stopped and resumes from its durable watermark when the final ACK was lost', async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const sockets: Array<{
      readyState: number
      close: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    }> = []
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => {
        const socket = {
          readyState: WebSocket.OPEN,
          close: vi.fn(),
          send: vi.fn(),
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
        }
        sockets.push(socket)
        return socket
      },
      onState: vi.fn(),
    })

    await publisher.start()
    sockets[0]?.onopen?.()
    const internal = publisher as unknown as {
      sequence: number
      receivedThrough: number | null
    }
    internal.sequence = 1
    internal.receivedThrough = null

    const stopping = publisher.stop({ awaitServer: true })
    expect(
      sockets[0]?.send.mock.calls.some(([payload]) => {
        if (typeof payload !== 'string') return false
        return (JSON.parse(payload) as { type?: string }).type === 'audio.stop'
      }),
    ).toBe(true)
    sockets[0]?.onmessage?.({
      data: JSON.stringify({
        type: 'audio.stopped',
        last_received_sequence: 0,
        last_processed_sequence: 0,
        last_final_transcript_sequence: null,
      }),
    } as MessageEvent<string>)
    await expect(stopping).resolves.toBe(true)

    await publisher.start()
    sockets[1]?.onopen?.()
    const restart = JSON.parse(
      sockets[1]?.send.mock.calls.find(
        ([payload]) => typeof payload === 'string',
      )?.[0] as string,
    ) as { data: { resume_from_sequence: number | null } }
    expect(restart.data.resume_from_sequence).toBe(0)
    await publisher.destroy()
  })

  it('stops and resumes before the first frame with the public null watermark', async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const sockets: Array<{
      readyState: number
      close: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    }> = []
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => {
        const socket = {
          readyState: WebSocket.OPEN,
          close: vi.fn(),
          send: vi.fn(),
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
        }
        sockets.push(socket)
        return socket
      },
      onState: vi.fn(),
    })

    await publisher.start()
    sockets[0]?.onopen?.()
    const stopping = publisher.stop({ awaitServer: true })
    sockets[0]?.onmessage?.({
      data: JSON.stringify({
        type: 'audio.stopped',
        last_received_sequence: null,
        last_processed_sequence: null,
        last_final_transcript_sequence: null,
      }),
    } as MessageEvent<string>)
    await expect(stopping).resolves.toBe(true)

    await publisher.start()
    sockets[1]?.onopen?.()
    const restart = JSON.parse(
      sockets[1]?.send.mock.calls.find(
        ([payload]) => typeof payload === 'string',
      )?.[0] as string,
    ) as { data: { resume_from_sequence: number | null } }
    expect(restart.data.resume_from_sequence).toBeNull()
    await publisher.destroy()
  })

  it('fails a graceful stop safely when audio.stopped times out and ignores a late reply', async () => {
    vi.useFakeTimers()
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const socket: {
      readyState: number
      close: () => void
      send: (data: string | ArrayBuffer) => void
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    } = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      stopAckTimeoutMs: 10,
      onState: vi.fn(),
    })

    await publisher.start()
    socket.onopen?.()
    const internal = publisher as unknown as {
      sequence: number
      receivedThrough: number | null
    }
    internal.sequence = 1
    internal.receivedThrough = null
    const stopping = publisher.stop({ awaitServer: true })
    await vi.advanceTimersByTimeAsync(10)

    await expect(stopping).resolves.toBe(false)
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'audio.stopped',
        last_received_sequence: 0,
      }),
    } as MessageEvent<string>)
    expect(internal.receivedThrough).toBeNull()
    await publisher.destroy()
  })

  it('fails a graceful stop safely when the owned socket closes before audio.stopped', async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const socket: {
      readyState: number
      close: () => void
      send: (data: string | ArrayBuffer) => void
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    } = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      onState: vi.fn(),
    })

    await publisher.start()
    socket.onopen?.()
    ;(publisher as unknown as { sequence: number }).sequence = 1
    const stopping = publisher.stop({ awaitServer: true })
    socket.onclose?.()

    await expect(stopping).resolves.toBe(false)
    await publisher.destroy()
  })

  it('shares the stream with local recording only after audio.ready claims publisher', async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const socket = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const onMediaStream = vi.fn()
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      onMediaStream,
      onState: vi.fn(),
    })

    await publisher.start()
    expect(onMediaStream).not.toHaveBeenCalled()
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'audio.ready',
        last_received_sequence: null,
        max_in_flight: 1,
      }),
    } as MessageEvent<string>)

    expect(onMediaStream).toHaveBeenCalledTimes(1)
    await publisher.destroy()
  })

  it('releases only the publisher track while an announced recording clone remains active', async () => {
    const stopPublisherTrack = vi.fn()
    const stopRecordingTrack = vi.fn()
    const recordingClone = {
      getTracks: () => [{ stop: stopRecordingTrack }],
    } as unknown as MediaStream
    const stream = {
      getTracks: () => [{ stop: stopPublisherTrack }],
      clone: () => recordingClone,
    } as unknown as MediaStream
    const socket = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const ownedRecordingStream = { current: null as MediaStream | null }
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      onMediaStream: (announced) => {
        ownedRecordingStream.current = announced.clone()
      },
      onState: vi.fn(),
    })

    await publisher.start()
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'audio.ready',
        last_received_sequence: null,
        max_in_flight: 1,
      }),
    } as MessageEvent<string>)
    await publisher.stop()

    expect(ownedRecordingStream.current).toBe(recordingClone)
    expect(stopPublisherTrack).toHaveBeenCalledTimes(1)
    expect(stopRecordingTrack).not.toHaveBeenCalled()
    ownedRecordingStream.current
      ?.getTracks()
      .forEach((track: MediaStreamTrack) => track.stop())
    expect(stopRecordingTrack).toHaveBeenCalledTimes(1)
  })

  it('ignores a queued audio.ready after the publisher was stopped', async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const socket = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const onMediaStream = vi.fn()
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      onMediaStream,
      onState: vi.fn(),
    })

    await publisher.start()
    await publisher.stop()
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'audio.ready',
        last_received_sequence: null,
        max_in_flight: 1,
      }),
    } as MessageEvent<string>)

    expect(onMediaStream).not.toHaveBeenCalled()
    await publisher.destroy()
  })

  it('treats a rejected resume watermark as terminal for the current stream', async () => {
    const stopTrack = vi.fn()
    const stream = {
      getTracks: () => [{ stop: stopTrack }],
    } as unknown as MediaStream
    const socket = {
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const states: AudioPublisherState[] = []
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => socket,
      onState: (state) => states.push(state),
    })

    await publisher.start()
    socket.onmessage?.({
      data: JSON.stringify({ type: 'audio.resume_rejected' }),
    } as MessageEvent<string>)

    expect(states.at(-1)).toBe('resume_rejected')
    expect(socket.close).toHaveBeenCalled()
    expect(stopTrack).toHaveBeenCalledTimes(1)
    await publisher.destroy()
  })

  it('keeps stream identity, sequence watermark and offset monotonic across a remount', async () => {
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const sockets: Array<{
      readyState: number
      close: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    }> = []
    const makePublisher = () =>
      new LiveAudioPublisher({
        sessionId: 'session-1',
        getUserMedia: async () => stream,
        createTicket: async () => ({ ticket: 'ticket' }) as never,
        webSocketFactory: () => {
          const socket = {
            readyState: WebSocket.OPEN,
            close: vi.fn(),
            send: vi.fn(),
            onopen: null,
            onclose: null,
            onerror: null,
            onmessage: null,
          }
          sockets.push(socket)
          return socket
        },
        onState: vi.fn(),
      })
    const capture = (publisher: LiveAudioPublisher) =>
      (
        publisher as unknown as {
          capture: (input: Float32Array) => void
        }
      ).capture(new Float32Array(8_000))
    const startMessage = (socketIndex: number) =>
      JSON.parse(
        sockets[socketIndex]?.send.mock.calls.find(
          ([payload]) => typeof payload === 'string',
        )?.[0] as string,
      ) as {
        data: {
          client_stream_id: string
          resume_from_sequence: number | null
        }
      }
    const frameMessage = (socketIndex: number) =>
      sockets[socketIndex]?.send.mock.calls.find(
        ([payload]) => payload instanceof ArrayBuffer,
      )?.[0] as ArrayBuffer

    const first = makePublisher()
    await first.start()
    sockets[0]?.onopen?.()
    capture(first)
    const firstFrame = new DataView(frameMessage(0))
    sockets[0]?.onmessage?.({
      data: JSON.stringify({ type: 'audio.ack', received_through: 0 }),
    } as MessageEvent<string>)
    const firstStart = startMessage(0)
    await first.destroy()

    const second = makePublisher()
    await second.start()
    sockets[1]?.onopen?.()
    capture(second)
    const secondFrame = new DataView(frameMessage(1))
    const secondStart = startMessage(1)

    expect(secondStart.data.client_stream_id).toBe(
      firstStart.data.client_stream_id,
    )
    expect(secondStart.data.resume_from_sequence).toBe(0)
    expect(secondFrame.getUint32(2, false)).toBe(1)
    expect(Number(secondFrame.getBigUint64(6, false))).toBeGreaterThanOrEqual(
      Number(firstFrame.getBigUint64(6, false)) + 500,
    )
    await second.destroy()
  })

  it('does not let a stale socket close schedule another connection', async () => {
    vi.useFakeTimers()
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    const sockets: Array<{
      readyState: number
      close: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      onopen: (() => void) | null
      onclose: (() => void) | null
      onerror: (() => void) | null
      onmessage: ((event: MessageEvent<string>) => void) | null
    }> = []
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia: async () => stream,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => {
        const socket = {
          readyState: WebSocket.OPEN,
          close: vi.fn(),
          send: vi.fn(),
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
        }
        sockets.push(socket)
        return socket
      },
      onState: vi.fn(),
    })

    await publisher.start()
    await publisher.stop()
    await publisher.start()
    sockets[0]?.onclose?.()
    await vi.advanceTimersByTimeAsync(10_000)

    expect(sockets).toHaveLength(2)
    await publisher.destroy()
  })

  it('ignores a stale permission rejection after a new start succeeds', async () => {
    const states: AudioPublisherState[] = []
    const stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    let rejectFirst: ((reason: unknown) => void) | undefined
    const firstPermission = new Promise<MediaStream>((_, reject) => {
      rejectFirst = reject
    })
    const getUserMedia = vi
      .fn()
      .mockImplementationOnce(() => firstPermission)
      .mockResolvedValueOnce(stream)
    const sockets: Array<{ close: ReturnType<typeof vi.fn> }> = []
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: () => {
        const socket = {
          readyState: WebSocket.OPEN,
          close: vi.fn(),
          send: vi.fn(),
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
        }
        sockets.push(socket)
        return socket
      },
      onState: (state) => states.push(state),
    })

    const firstStart = publisher.start()
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1))
    await publisher.stop()
    await publisher.start()
    rejectFirst?.(new DOMException('denied', 'NotAllowedError'))
    await firstStart

    expect(sockets).toHaveLength(1)
    expect(states.at(-1)).toBe('connecting')
    expect(states).not.toContain('denied')
    await publisher.destroy()
  })

  it('ignores a stale ticket rejection without releasing the new stream', async () => {
    const stopFirstTrack = vi.fn()
    const stopSecondTrack = vi.fn()
    const firstStream = {
      getTracks: () => [{ stop: stopFirstTrack }],
    } as unknown as MediaStream
    const secondStream = {
      getTracks: () => [{ stop: stopSecondTrack }],
    } as unknown as MediaStream
    let rejectFirst: ((reason: unknown) => void) | undefined
    const firstTicket = new Promise<never>((_, reject) => {
      rejectFirst = reject
    })
    const createTicket = vi
      .fn()
      .mockImplementationOnce(() => firstTicket)
      .mockResolvedValueOnce({ ticket: 'ticket' } as never)
    const sockets: Array<{ close: ReturnType<typeof vi.fn> }> = []
    const getUserMedia = vi
      .fn()
      .mockResolvedValueOnce(firstStream)
      .mockResolvedValueOnce(secondStream)
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      getUserMedia,
      createTicket,
      webSocketFactory: () => {
        const socket = {
          readyState: WebSocket.OPEN,
          close: vi.fn(),
          send: vi.fn(),
          onopen: null,
          onclose: null,
          onerror: null,
          onmessage: null,
        }
        sockets.push(socket)
        return socket
      },
      onState: vi.fn(),
    })

    const firstStart = publisher.start()
    await vi.waitFor(() => expect(createTicket).toHaveBeenCalledTimes(1))
    await publisher.stop()
    expect(stopFirstTrack).toHaveBeenCalledTimes(1)
    await publisher.start()
    rejectFirst?.(
      new ApiError('forbidden', {
        status: 403,
        code: 'SESSION_ACCESS_DENIED',
      }),
    )
    await firstStart

    expect(sockets).toHaveLength(1)
    expect(stopSecondTrack).not.toHaveBeenCalled()
    await publisher.destroy()
    expect(stopSecondTrack).toHaveBeenCalledTimes(1)
  })

  it('holds one session lease until destroy and blocks a duplicated tab before permission', async () => {
    let held = false
    const acquireLease = vi.fn(async () => {
      if (held) return null
      held = true
      return () => {
        held = false
      }
    })
    const firstMedia = vi.fn(
      async () =>
        ({ getTracks: () => [{ stop: vi.fn() }] }) as unknown as MediaStream,
    )
    const secondMedia = vi.fn(
      async () =>
        ({ getTracks: () => [{ stop: vi.fn() }] }) as unknown as MediaStream,
    )
    const socket = () => ({
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null,
    })
    const secondState = vi.fn()
    const first = new LiveAudioPublisher({
      sessionId: 'session-1',
      acquireLease,
      getUserMedia: firstMedia,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: socket,
      onState: vi.fn(),
    })
    const second = new LiveAudioPublisher({
      sessionId: 'session-1',
      acquireLease,
      getUserMedia: secondMedia,
      createTicket: async () => ({ ticket: 'ticket' }) as never,
      webSocketFactory: socket,
      onState: secondState,
    })

    await first.start()
    await second.start()
    expect(firstMedia).toHaveBeenCalledTimes(1)
    expect(secondMedia).not.toHaveBeenCalled()
    expect(secondState).toHaveBeenLastCalledWith('conflict', expect.any(String))

    await first.stop()
    await second.start()
    expect(secondMedia).not.toHaveBeenCalled()

    await first.destroy()
    await second.start()
    expect(secondMedia).toHaveBeenCalledTimes(1)
    await second.destroy()
  })

  it('does not let stale capture initialization close the current socket', async () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext')
    let rejectResume: ((reason: unknown) => void) | undefined
    const resume = new Promise<void>((_, reject) => {
      rejectResume = reject
    })
    const closeContext = vi.fn(async () => undefined)
    class DeferredAudioContext {
      audioWorklet = {}
      destination = {}
      resume = () => resume
      close = closeContext
    }
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      value: DeferredAudioContext,
    })
    const closeSocket = vi.fn()
    const onState = vi.fn()
    const publisher = new LiveAudioPublisher({
      sessionId: 'session-1',
      onState,
    })
    const internal = publisher as unknown as {
      stream: MediaStream
      stopped: boolean
      lifecycleGeneration: number
      socket: { close: () => void }
      initializeCapture: () => Promise<void>
    }
    internal.stream = {
      getTracks: () => [{ stop: vi.fn() }],
    } as unknown as MediaStream
    internal.stopped = false
    internal.lifecycleGeneration = 1
    internal.socket = { close: closeSocket }

    try {
      const initialization = internal.initializeCapture()
      internal.lifecycleGeneration = 2
      rejectResume?.(new Error('old worklet failed'))
      await initialization

      expect(closeSocket).not.toHaveBeenCalled()
      expect(onState).not.toHaveBeenCalledWith(
        'unavailable',
        expect.any(String),
      )
    } finally {
      if (original) Object.defineProperty(globalThis, 'AudioContext', original)
      else Reflect.deleteProperty(globalThis, 'AudioContext')
    }
  })
})

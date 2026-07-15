import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  beginLiveClassEnd,
  reconcileLiveClassEndControls,
  startLiveClassEndReconciliation,
} from './live-end'

describe('beginLiveClassEnd', () => {
  afterEach(() => vi.useRealTimers())

  function controls() {
    return {
      audio: {
        quiesceForEnd: vi.fn(async () => undefined),
        commitEnd: vi.fn(async () => undefined),
        resumeAfterEndFailure: vi.fn(async () => undefined),
      },
      recording: {
        quiesceForEnd: vi.fn(async () => undefined),
        finalizeRecording: vi.fn(async () => undefined),
        resumeAfterEndFailure: vi.fn(async () => undefined),
      },
    }
  }

  it('quiesces immediately and finalizes after the server accepts PROCESSING', async () => {
    let finishEnd: (() => void) | undefined
    const onEnd = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finishEnd = resolve
        }),
    )
    const { audio, recording } = controls()

    const ending = beginLiveClassEnd(onEnd, audio, recording)

    expect(onEnd).toHaveBeenCalledTimes(1)
    expect(audio.quiesceForEnd).toHaveBeenCalledTimes(1)
    expect(recording.quiesceForEnd).toHaveBeenCalledTimes(1)
    expect(audio.commitEnd).not.toHaveBeenCalled()
    expect(recording.finalizeRecording).not.toHaveBeenCalled()

    finishEnd?.()
    await ending
    expect(audio.commitEnd).toHaveBeenCalledTimes(1)
    expect(recording.finalizeRecording).toHaveBeenCalledTimes(1)
    expect(audio.resumeAfterEndFailure).not.toHaveBeenCalled()
  })

  it('resumes both capture paths only after REST confirms LIVE', async () => {
    const onEnd = vi.fn(async () => {
      throw new Error('SESSION_STATE_CONFLICT')
    })
    const resolveFailure = vi.fn(async () => 'live' as const)
    const { audio, recording } = controls()

    await expect(
      beginLiveClassEnd(onEnd, audio, recording, resolveFailure),
    ).rejects.toThrow('SESSION_STATE_CONFLICT')

    expect(resolveFailure).toHaveBeenCalledTimes(1)
    expect(audio.resumeAfterEndFailure).toHaveBeenCalledTimes(1)
    expect(recording.resumeAfterEndFailure).toHaveBeenCalledTimes(1)
    expect(audio.commitEnd).not.toHaveBeenCalled()
    expect(recording.finalizeRecording).not.toHaveBeenCalled()
  })

  it('finalizes an ambiguously failed request when REST already shows ended', async () => {
    const onEnd = vi.fn(async () => {
      throw new Error('response lost')
    })
    const { audio, recording } = controls()

    await expect(
      beginLiveClassEnd(onEnd, audio, recording, async () => 'ended'),
    ).rejects.toThrow('response lost')

    expect(audio.commitEnd).toHaveBeenCalledTimes(1)
    expect(recording.finalizeRecording).toHaveBeenCalledTimes(1)
    expect(audio.resumeAfterEndFailure).not.toHaveBeenCalled()
  })

  it('keeps controls quiesced and delegates later reconciliation when status is unknown', async () => {
    const onEnd = vi.fn(async () => {
      throw new Error('network unavailable')
    })
    const onUnresolved = vi.fn()
    const { audio, recording } = controls()

    await expect(
      beginLiveClassEnd(
        onEnd,
        audio,
        recording,
        async () => 'unknown',
        onUnresolved,
      ),
    ).rejects.toThrow('network unavailable')

    expect(onUnresolved).toHaveBeenCalledTimes(1)
    expect(audio.resumeAfterEndFailure).not.toHaveBeenCalled()
    expect(recording.resumeAfterEndFailure).not.toHaveBeenCalled()

    await expect(
      reconcileLiveClassEndControls('live', audio, recording),
    ).resolves.toBe(true)
    expect(audio.resumeAfterEndFailure).toHaveBeenCalledTimes(1)
    expect(recording.resumeAfterEndFailure).toHaveBeenCalledTimes(1)
  })

  it('polls an unknown end result every five seconds until REST confirms LIVE', async () => {
    vi.useFakeTimers()
    const resolveFailure = vi
      .fn<() => Promise<'unknown' | 'live'>>()
      .mockResolvedValueOnce('unknown')
      .mockResolvedValueOnce('live')
    const onSettled = vi.fn()
    const { audio, recording } = controls()

    const cancel = startLiveClassEndReconciliation(
      resolveFailure,
      () => audio,
      () => recording,
      onSettled,
    )

    await vi.advanceTimersByTimeAsync(5_000)
    expect(resolveFailure).toHaveBeenCalledTimes(1)
    expect(onSettled).not.toHaveBeenCalled()
    expect(audio.resumeAfterEndFailure).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(5_000)
    expect(resolveFailure).toHaveBeenCalledTimes(2)
    expect(audio.resumeAfterEndFailure).toHaveBeenCalledTimes(1)
    expect(recording.resumeAfterEndFailure).toHaveBeenCalledTimes(1)
    expect(onSettled).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(5_000)
    expect(resolveFailure).toHaveBeenCalledTimes(2)
    cancel()
  })
})

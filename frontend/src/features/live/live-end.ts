import type { LocalRecordingPanelHandle } from '../recordings/LocalRecordingPanel'
import type { LiveAudioPublisherControlHandle } from './LiveAudioPublisherControl'

export type EndFailureResolution = 'live' | 'ended' | 'unknown'

export async function reconcileLiveClassEndControls(
  resolution: EndFailureResolution,
  audioControl: LiveAudioPublisherControlHandle | null,
  recordingControl: LocalRecordingPanelHandle | null,
) {
  if (resolution === 'live') {
    await Promise.allSettled([
      audioControl?.resumeAfterEndFailure(),
      recordingControl?.resumeAfterEndFailure(),
    ])
    return true
  }
  if (resolution === 'ended') {
    await Promise.allSettled([
      audioControl?.commitEnd(),
      recordingControl?.finalizeRecording(),
    ])
    return true
  }
  return false
}

export function startLiveClassEndReconciliation(
  resolveFailure: () => Promise<EndFailureResolution>,
  getAudioControl: () => LiveAudioPublisherControlHandle | null,
  getRecordingControl: () => LocalRecordingPanelHandle | null,
  onSettled: () => void,
  intervalMs = 5_000,
) {
  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const reconcile = async () => {
    const resolution = await resolveFailure().catch(() => 'unknown' as const)
    if (cancelled) return
    const settled = await reconcileLiveClassEndControls(
      resolution,
      getAudioControl(),
      getRecordingControl(),
    )
    if (cancelled) return
    if (settled) {
      onSettled()
      return
    }
    timer = setTimeout(() => void reconcile(), intervalMs)
  }
  timer = setTimeout(() => void reconcile(), intervalMs)
  return () => {
    cancelled = true
    if (timer) clearTimeout(timer)
  }
}

export async function beginLiveClassEnd(
  onEnd: () => Promise<unknown>,
  audioControl: LiveAudioPublisherControlHandle | null,
  recordingControl: LocalRecordingPanelHandle | null,
  resolveFailure: () => Promise<EndFailureResolution> = async () => 'live',
  onUnresolved?: () => void,
) {
  const quiescing = Promise.allSettled([
    audioControl?.quiesceForEnd(),
    recordingControl?.quiesceForEnd(),
  ])
  try {
    const result = await onEnd()
    await quiescing
    await Promise.allSettled([
      audioControl?.commitEnd(),
      recordingControl?.finalizeRecording(),
    ])
    return result
  } catch (error) {
    await quiescing
    const resolution = await resolveFailure().catch(() => 'unknown' as const)
    const settled = await reconcileLiveClassEndControls(
      resolution,
      audioControl,
      recordingControl,
    )
    if (!settled) onUnresolved?.()
    throw error
  }
}

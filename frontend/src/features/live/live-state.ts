import type { components } from '../../api/generated/schema'
import type { RealtimeEvent } from '../realtime/client'

type Segment = components['schemas']['TranscriptSegment']
type Gap = components['schemas']['TranscriptGap']

export interface LivePartial {
  utteranceId: string
  revision: number
  startMs: number
  endMs: number
  text: string
}

export interface LiveTranscriptState {
  segments: Segment[]
  gaps: Gap[]
  partials: Record<string, LivePartial>
  streamStatus:
    'LISTENING' | 'DEGRADED' | 'FINALIZING' | 'FINALIZED' | 'STOPPED' | null
  resyncing: boolean
}

export const initialLiveTranscriptState: LiveTranscriptState = {
  segments: [],
  gaps: [],
  partials: {},
  streamStatus: null,
  resyncing: false,
}

export type LiveTranscriptAction =
  | { type: 'hydrate'; data: { segments: Segment[]; gaps: Gap[] } }
  | { type: 'event'; event: RealtimeEvent }

function sortedSegments(segments: Segment[]) {
  return [...segments].sort(
    (a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id),
  )
}

function eventData<T>(event: RealtimeEvent): T {
  return event.data as T
}

export function hydrateTranscript(
  state: LiveTranscriptState,
  data: { segments: Segment[]; gaps: Gap[] },
): LiveTranscriptState {
  return {
    ...state,
    segments: sortedSegments(data.segments),
    gaps: [...data.gaps].sort(
      (a, b) => a.start_ms - b.start_ms || a.id.localeCompare(b.id),
    ),
    partials: {},
    resyncing: false,
  }
}

/** Merge only ordered, transient partials; final DB events always win. */
export function mergeLiveTranscriptEvent(
  state: LiveTranscriptState,
  event: RealtimeEvent,
): LiveTranscriptState {
  if (event.type === 'resync.required') {
    return { ...state, partials: {}, resyncing: true }
  }
  if (event.type === 'transcript.partial') {
    const data = eventData<{
      utterance_id: string
      revision: number
      start_ms: number
      end_ms: number
      text: string
    }>(event)
    if (!data.utterance_id || typeof data.revision !== 'number') return state
    const previous = state.partials[data.utterance_id]
    if (previous && previous.revision >= data.revision) return state
    return {
      ...state,
      partials: {
        ...state.partials,
        [data.utterance_id]: {
          utteranceId: data.utterance_id,
          revision: data.revision,
          startMs: data.start_ms,
          endMs: data.end_ms,
          text: data.text,
        },
      },
    }
  }
  if (event.type === 'transcript.final') {
    const data = eventData<{ utterance_id: string; segment: Segment }>(event)
    if (!data.segment?.id) return state
    const existing = state.segments.find((item) => item.id === data.segment.id)
    const segments = existing
      ? state.segments.map((item) =>
          item.id === data.segment.id ? data.segment : item,
        )
      : [...state.segments, data.segment]
    const partials = { ...state.partials }
    delete partials[data.utterance_id]
    return { ...state, segments: sortedSegments(segments), partials }
  }
  if (event.type === 'transcript.status') {
    const data = eventData<{
      stream_status?: LiveTranscriptState['streamStatus']
    }>(event)
    return { ...state, streamStatus: data.stream_status ?? state.streamStatus }
  }
  if (event.type === 'transcript.version.updated') {
    return { ...state, partials: {}, resyncing: true }
  }
  return state
}

export function liveTranscriptReducer(
  state: LiveTranscriptState,
  action: LiveTranscriptAction,
): LiveTranscriptState {
  return action.type === 'hydrate'
    ? hydrateTranscript(state, action.data)
    : mergeLiveTranscriptEvent(state, action.event)
}

import { describe, expect, it } from 'vitest'

import {
  hydrateTranscript,
  initialLiveTranscriptState,
  mergeLiveTranscriptEvent,
} from './live-state'

const sessionId = '10000000-0000-0000-0000-000000000001'
const versionId = '20000000-0000-0000-0000-000000000001'

function event(type: string, data: Record<string, unknown>) {
  return {
    event_id: crypto.randomUUID(),
    type,
    session_id: sessionId,
    cursor: null,
    resource_version: 1,
    data,
  }
}

function segment(id: string, version = versionId, sequence = 1) {
  return {
    id,
    session_id: sessionId,
    transcript_version_id: version,
    item_type: 'SEGMENT' as const,
    sequence,
    start_ms: sequence * 500,
    end_ms: sequence * 500 + 400,
    recording_start_ms: null,
    recording_end_ms: null,
    text: id,
    created_at: '2026-07-14T00:00:00Z',
  }
}

function timeline(version: string, segments: ReturnType<typeof segment>[]) {
  return {
    transcript: {},
    selected_version: { id: version },
    segments,
    gaps: [],
    next_cursor: null,
  } as never
}

describe('mergeLiveTranscriptEvent', () => {
  it('does not replace a newer partial with an out-of-order revision', () => {
    const newer = mergeLiveTranscriptEvent(
      initialLiveTranscriptState,
      event('transcript.partial', {
        utterance_id: 'utterance-1',
        revision: 2,
        start_ms: 0,
        end_ms: 500,
        text: 'new',
      }),
    )
    const state = mergeLiveTranscriptEvent(
      newer,
      event('transcript.partial', {
        utterance_id: 'utterance-1',
        revision: 1,
        start_ms: 0,
        end_ms: 500,
        text: 'old',
      }),
    )
    expect(state.partials['utterance-1']?.text).toBe('new')
  })

  it('replaces a transient partial with its persisted final segment', () => {
    const partial = mergeLiveTranscriptEvent(
      initialLiveTranscriptState,
      event('transcript.partial', {
        utterance_id: 'utterance-1',
        revision: 1,
        start_ms: 0,
        end_ms: 500,
        text: 'temporary',
      }),
    )
    const state = mergeLiveTranscriptEvent(
      partial,
      event('transcript.final', {
        utterance_id: 'utterance-1',
        segment: {
          id: 'segment-1',
          session_id: sessionId,
          transcript_version_id: versionId,
          item_type: 'SEGMENT',
          sequence: 1,
          start_ms: 0,
          end_ms: 500,
          recording_start_ms: null,
          recording_end_ms: null,
          text: 'final',
          created_at: '2026-07-14T00:00:00Z',
        },
      }),
    )
    expect(state.partials).toEqual({})
    expect(state.segments[0]?.text).toBe('final')
  })

  it('drops all transient text when REST resync is required', () => {
    const partial = mergeLiveTranscriptEvent(
      initialLiveTranscriptState,
      event('transcript.partial', {
        utterance_id: 'utterance-1',
        revision: 1,
        start_ms: 0,
        end_ms: 500,
        text: 'temporary',
      }),
    )
    const state = mergeLiveTranscriptEvent(
      partial,
      event('resync.required', {}),
    )
    expect(state.partials).toEqual({})
    expect(state.resyncing).toBe(true)
  })

  it('preserves a newer WebSocket final when same-version REST finishes late', () => {
    const live = mergeLiveTranscriptEvent(
      {
        ...initialLiveTranscriptState,
        selectedVersionId: versionId,
      },
      event('transcript.final', {
        utterance_id: 'utterance-2',
        segment: segment('segment-2', versionId, 2),
      }),
    )

    const state = hydrateTranscript(
      live,
      timeline(versionId, [segment('segment-1')]),
    )

    expect(state.segments.map((item) => item.id)).toEqual([
      'segment-1',
      'segment-2',
    ])
  })

  it('replaces the durable timeline when the canonical version changes', () => {
    const state = hydrateTranscript(
      {
        ...initialLiveTranscriptState,
        selectedVersionId: versionId,
        segments: [segment('old-segment')],
      },
      timeline('version-b', [segment('new-segment', 'version-b')]),
    )

    expect(state.selectedVersionId).toBe('version-b')
    expect(state.segments.map((item) => item.id)).toEqual(['new-segment'])
  })

  it('ignores an old-version final while canonical REST hydration is pending', () => {
    const waiting = mergeLiveTranscriptEvent(
      {
        ...initialLiveTranscriptState,
        selectedVersionId: versionId,
        segments: [segment('old-segment')],
      },
      event('transcript.version.updated', {}),
    )
    const state = mergeLiveTranscriptEvent(
      waiting,
      event('transcript.final', {
        utterance_id: 'late-old',
        segment: segment('late-old'),
      }),
    )

    expect(state.segments.map((item) => item.id)).toEqual(['old-segment'])
    expect(state.awaitingVersionHydration).toBe(true)
  })
})

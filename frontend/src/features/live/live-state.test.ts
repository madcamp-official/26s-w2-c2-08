import { describe, expect, it } from 'vitest'

import {
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
})

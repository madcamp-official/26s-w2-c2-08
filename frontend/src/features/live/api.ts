import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type TranscriptTimeline = components['schemas']['TranscriptTimelinePage']

async function getLiveTranscriptPage(
  sessionId: string,
  cursor: string | null,
  transcriptVersionId: string | null,
  signal?: AbortSignal,
): Promise<TranscriptTimeline> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/sessions/{session_id}/transcript',
      {
        params: {
          path: { session_id: sessionId },
          query: {
            cursor: cursor ?? undefined,
            limit: 100,
            transcript_version_id: transcriptVersionId ?? undefined,
          },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('Transcript 응답이 비어 있습니다.')
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/**
 * Restore the complete persisted LIVE timeline. The first page chooses the
 * canonical version; every following cursor is pinned to that same version so
 * a concurrent canonical switch cannot mix two timelines.
 */
export async function getLiveTranscript(
  sessionId: string,
  signal?: AbortSignal,
): Promise<TranscriptTimeline> {
  const firstPage = await getLiveTranscriptPage(sessionId, null, null, signal)
  const segments = [...firstPage.segments]
  const gaps = [...firstPage.gaps]
  const selectedVersionId = firstPage.selected_version.id
  const seenCursors = new Set<string>()
  let cursor = firstPage.next_cursor

  while (cursor) {
    if (seenCursors.has(cursor)) {
      throw new Error('Transcript cursor가 반복되어 복구를 중단했습니다.')
    }
    seenCursors.add(cursor)
    const page = await getLiveTranscriptPage(
      sessionId,
      cursor,
      selectedVersionId,
      signal,
    )
    if (page.selected_version.id !== selectedVersionId) {
      throw new Error('Transcript version이 페이지 조회 중 변경되었습니다.')
    }
    segments.push(...page.segments)
    gaps.push(...page.gaps)
    cursor = page.next_cursor
  }

  return {
    ...firstPage,
    segments,
    gaps,
    next_cursor: null,
  }
}

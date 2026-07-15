import type { QueryClient } from '@tanstack/react-query'

import { personalAiKeys } from './queries'

export function liveSummaryJobStorageKey(sessionId: string) {
  return `goal:live-summary-job:${sessionId}`
}

export function readLiveSummaryJobId(sessionId: string) {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage.getItem(liveSummaryJobStorageKey(sessionId))
  } catch {
    return null
  }
}

export function writeLiveSummaryJobId(sessionId: string, jobId: string) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(liveSummaryJobStorageKey(sessionId), jobId)
  } catch {
    // Polling continues from in-memory state when tab storage is unavailable.
  }
}

export function clearLiveSummaryJobId(sessionId: string) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.removeItem(liveSummaryJobStorageKey(sessionId))
  } catch {
    // Canonical Session state is authoritative; cleanup remains best-effort.
  }
}

export function purgeLivePersonalAiClientState(
  queryClient: QueryClient,
  sessionId: string,
) {
  void queryClient.cancelQueries({
    queryKey: personalAiKeys.session(sessionId),
  })
  queryClient.removeQueries({
    queryKey: personalAiKeys.session(sessionId),
  })
  clearLiveSummaryJobId(sessionId)
}

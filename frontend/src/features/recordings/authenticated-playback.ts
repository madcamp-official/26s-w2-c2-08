import { apiUrl } from '../../api/client'

/**
 * Load a protected recording through the same credentialed fetch boundary as
 * the authorization probe, then hand the media element a same-origin Blob URL.
 *
 * This is a recovery path only: normal playback continues to use HTTP Range
 * requests directly, avoiding a full recording download before first play.
 */
export async function fetchAuthenticatedPlaybackUrl(
  playbackUrl: string,
): Promise<string> {
  const response = await fetch(apiUrl(playbackUrl), {
    credentials: 'include',
    headers: { Accept: 'audio/webm,audio/mp4;q=0.9,*/*;q=0.1' },
  })
  if (!response.ok) {
    throw new Error(`recording playback request failed: ${response.status}`)
  }

  const blob = await response.blob()
  if (blob.size === 0) throw new Error('recording playback response was empty')

  return URL.createObjectURL(blob)
}

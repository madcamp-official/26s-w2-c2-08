export async function seekRecordingPlayback(
  audio: HTMLAudioElement,
  offsetMs: number,
) {
  if (audio.readyState < HTMLMediaElement.HAVE_METADATA) {
    await new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        audio.removeEventListener('loadedmetadata', handleLoadedMetadata)
        audio.removeEventListener('error', handleError)
      }
      const handleLoadedMetadata = () => {
        cleanup()
        resolve()
      }
      const handleError = () => {
        cleanup()
        reject(new Error('recording metadata failed to load'))
      }
      audio.addEventListener('loadedmetadata', handleLoadedMetadata, {
        once: true,
      })
      audio.addEventListener('error', handleError, { once: true })
    })
  }
  audio.currentTime = offsetMs / 1000
}

export async function seekAndPlayRecording(
  audio: HTMLAudioElement,
  offsetMs: number,
): Promise<'playing' | 'positioned'> {
  await seekRecordingPlayback(audio, offsetMs)
  try {
    await audio.play()
    return 'playing'
  } catch {
    // Browsers can reject play() after the asynchronous authorization request
    // consumes the original user activation. The seek itself must still succeed.
    return 'positioned'
  }
}

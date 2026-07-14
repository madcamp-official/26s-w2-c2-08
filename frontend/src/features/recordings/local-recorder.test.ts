import { describe, expect, it } from 'vitest'

import {
  BrowserRecordingUnsupportedError,
  LocalRecorder,
} from './local-recorder'

describe('LocalRecorder', () => {
  it('does not fall back to localStorage when MediaRecorder is unavailable', async () => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'MediaRecorder',
    )
    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      value: undefined,
    })

    try {
      await expect(
        new LocalRecorder().start('session-1', {} as MediaStream, 'stream-1'),
      ).rejects.toBeInstanceOf(BrowserRecordingUnsupportedError)
    } finally {
      if (original) Object.defineProperty(globalThis, 'MediaRecorder', original)
      else Reflect.deleteProperty(globalThis, 'MediaRecorder')
    }
  })
})

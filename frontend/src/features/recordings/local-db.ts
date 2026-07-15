const DB_NAME = 'goal-local-recordings'
const DB_VERSION = 1

export interface RecordingMeta {
  sessionId: string
  clientStreamId: string
  contentType: 'audio/webm' | 'audio/mp4'
  durationMs: number
  totalBytes: number
  nextSequence: number
  finalSha256: string | null
  finalized: boolean
  uploadId: string | null
  acknowledgedOffset: number
  failedReason: string | null
  /** Local-only recovery fields. Optional values migrate rows written by older builds. */
  uploadCreateKey?: string | null
  uploadCompleteKey?: string | null
  uploadState?: 'NOT_STARTED' | 'ACTIVE' | 'COMPLETED' | 'EXPIRED'
  /** True only after MediaRecorder stopped and every final fragment committed. */
  finalizationReady?: boolean
}

interface Fragment {
  id: string
  sessionId: string
  sequence: number
  start: number
  end: number
  blob: Blob
}

function open() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains('meta'))
        db.createObjectStore('meta', { keyPath: 'sessionId' })
      if (!db.objectStoreNames.contains('fragments')) {
        const store = db.createObjectStore('fragments', { keyPath: 'id' })
        store.createIndex('by-session', 'sessionId')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () =>
      reject(request.error ?? new Error('IndexedDB를 열 수 없습니다.'))
  })
}

async function transaction<T>(
  stores: string[],
  mode: IDBTransactionMode,
  work: (transaction: IDBTransaction) => IDBRequest<T> | void,
): Promise<T | undefined> {
  const db = await open()
  try {
    return await new Promise<T | undefined>((resolve, reject) => {
      const tx = db.transaction(stores, mode)
      const request = work(tx)
      let result: T | undefined
      if (request) request.onsuccess = () => (result = request.result)
      tx.oncomplete = () => resolve(result)
      tx.onerror = () =>
        reject(tx.error ?? new Error('IndexedDB 저장에 실패했습니다.'))
      tx.onabort = () =>
        reject(tx.error ?? new Error('IndexedDB 작업이 중단되었습니다.'))
    })
  } finally {
    db.close()
  }
}

export async function getRecordingMeta(sessionId: string) {
  const meta =
    (await transaction<RecordingMeta>(['meta'], 'readonly', (tx) =>
      tx.objectStore('meta').get(sessionId),
    )) ?? null
  if (!meta) return null
  return {
    ...meta,
    uploadCreateKey: meta.uploadCreateKey ?? null,
    uploadCompleteKey: meta.uploadCompleteKey ?? null,
    uploadState: meta.uploadState ?? (meta.uploadId ? 'ACTIVE' : 'NOT_STARTED'),
    finalizationReady: meta.finalizationReady ?? false,
  }
}

export async function putRecordingMeta(meta: RecordingMeta) {
  await transaction(['meta'], 'readwrite', (tx) =>
    tx.objectStore('meta').put(meta),
  )
}

export async function appendFragment(
  meta: RecordingMeta,
  blob: Blob,
  durationMs = meta.durationMs,
) {
  const start = meta.totalBytes
  const next = {
    ...meta,
    durationMs: Math.max(meta.durationMs, durationMs),
    totalBytes: start + blob.size,
    nextSequence: meta.nextSequence + 1,
  }
  const fragment: Fragment = {
    id: `${meta.sessionId}:${meta.nextSequence}`,
    sessionId: meta.sessionId,
    sequence: meta.nextSequence,
    start,
    end: start + blob.size,
    blob,
  }
  await transaction(['meta', 'fragments'], 'readwrite', (tx) => {
    tx.objectStore('fragments').put(fragment)
    tx.objectStore('meta').put(next)
  })
  return next
}

async function fragments(sessionId: string) {
  const db = await open()
  try {
    return await new Promise<Fragment[]>((resolve, reject) => {
      const tx = db.transaction('fragments', 'readonly')
      const request = tx
        .objectStore('fragments')
        .index('by-session')
        .getAll(sessionId)
      request.onsuccess = () =>
        resolve(
          (request.result as Fragment[]).sort(
            (a, b) => a.sequence - b.sequence,
          ),
        )
      request.onerror = () => reject(request.error)
    })
  } finally {
    db.close()
  }
}

export async function blobFrom(
  sessionId: string,
  offset: number,
  maxBytes: number,
  contentType: string,
) {
  const selected: Blob[] = []
  let remaining = maxBytes
  for (const item of await fragments(sessionId)) {
    if (item.end <= offset || remaining <= 0) continue
    const start = Math.max(0, offset - item.start)
    const end = Math.min(item.blob.size, start + remaining)
    const part = item.blob.slice(start, end)
    selected.push(part)
    remaining -= part.size
  }
  return new Blob(selected, { type: contentType })
}

export async function wholeBlob(sessionId: string, contentType: string) {
  return new Blob(
    (await fragments(sessionId)).map((item) => item.blob),
    { type: contentType },
  )
}

/** Delete only fragments wholly covered by a server-confirmed contiguous offset. */
export async function deleteAcknowledgedFragments(
  sessionId: string,
  acknowledgedOffset: number,
) {
  const items = await fragments(sessionId)
  await transaction(['meta', 'fragments'], 'readwrite', (tx) => {
    items
      .filter((item) => item.end <= acknowledgedOffset)
      .forEach((item) => tx.objectStore('fragments').delete(item.id))
    const metaStore = tx.objectStore('meta')
    const request = metaStore.get(sessionId)
    request.onsuccess = () => {
      if (request.result)
        metaStore.put({ ...request.result, acknowledgedOffset })
    }
  })
}

export async function clearRecording(sessionId: string) {
  const items = await fragments(sessionId)
  await transaction(['meta', 'fragments'], 'readwrite', (tx) => {
    tx.objectStore('meta').delete(sessionId)
    items.forEach((item) => tx.objectStore('fragments').delete(item.id))
  })
}

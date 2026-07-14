export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

export interface MergedCursorPage<T> {
  items: T[]
  nextCursor: string | null
}

export function mergeCursorPages<T>(
  pages: CursorPage<T>[],
  getKey: (item: T) => string,
): MergedCursorPage<T> {
  const seen = new Set<string>()
  const items: T[] = []

  for (const page of pages) {
    for (const item of page.items) {
      const key = getKey(item)
      if (!seen.has(key)) {
        seen.add(key)
        items.push(item)
      }
    }
  }

  return {
    items,
    nextCursor: pages.at(-1)?.next_cursor ?? null,
  }
}

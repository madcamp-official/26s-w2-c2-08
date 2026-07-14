export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/'
  if (value === '/api' || value.startsWith('/api/')) return '/'
  if (value === '/login' || value.startsWith('/login?')) return '/'
  if (
    value.includes('\\') ||
    Array.from(value).some((character) => character.charCodeAt(0) < 32)
  )
    return '/'
  return value
}

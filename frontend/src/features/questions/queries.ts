export const questionKeys = {
  all: ['questions'] as const,
  session: (sessionId: string) => ['questions', 'session', sessionId] as const,
  list: (sessionId: string, sort: 'POPULAR' | 'RECENT') =>
    ['questions', 'session', sessionId, 'OPEN', sort] as const,
}

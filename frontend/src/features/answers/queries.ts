export const answerKeys = {
  all: ['answers'] as const,
  session: (sessionId: string) => ['answers', 'session', sessionId] as const,
}

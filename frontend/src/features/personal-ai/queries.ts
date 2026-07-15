export const personalAiKeys = {
  all: ['personal-ai'] as const,
  session: (sessionId: string) =>
    ['personal-ai', 'session', sessionId] as const,
  summaries: (sessionId: string) =>
    [...personalAiKeys.session(sessionId), 'summaries'] as const,
  chats: (sessionId: string) =>
    [...personalAiKeys.session(sessionId), 'chats'] as const,
  messages: (sessionId: string, chatId: string) =>
    [...personalAiKeys.session(sessionId), 'messages', chatId] as const,
  job: (sessionId: string, jobId: string) =>
    [...personalAiKeys.session(sessionId), 'job', jobId] as const,
}

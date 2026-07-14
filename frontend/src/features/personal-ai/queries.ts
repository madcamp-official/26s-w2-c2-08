export const personalAiKeys = {
  all: ['personal-ai'] as const,
  summaries: (sessionId: string) =>
    ['personal-ai', 'summaries', sessionId] as const,
  chats: (sessionId: string) => ['personal-ai', 'chats', sessionId] as const,
  messages: (chatId: string) => ['personal-ai', 'messages', chatId] as const,
  job: (jobId: string) => ['personal-ai', 'job', jobId] as const,
}

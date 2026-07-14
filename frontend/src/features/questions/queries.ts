export const questionKeys = {
  all: ['questions'] as const,
  session: (sessionId: string) => ['questions', 'session', sessionId] as const,
  list: (sessionId: string, sort: 'POPULAR' | 'RECENT') =>
    ['questions', 'session', sessionId, 'OPEN', sort] as const,
  clusters: (sessionId: string) =>
    ['questions', 'session', sessionId, 'clusters', 'CURRENT'] as const,
  clusterMembers: (sessionId: string, clusterId: string) =>
    [
      'questions',
      'session',
      sessionId,
      'clusters',
      clusterId,
      'members',
    ] as const,
}

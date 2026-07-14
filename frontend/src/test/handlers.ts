import { http, HttpResponse } from 'msw'

export const handlers = [
  http.get('*/api/health', () => HttpResponse.json({ status: 'ok' as const })),
  http.get('*/api/v1/me', () =>
    HttpResponse.json(
      {
        error: {
          code: 'AUTHENTICATION_REQUIRED',
          message: '로그인이 필요합니다.',
          request_id: 'req_test',
          details: null,
        },
      },
      { status: 401 },
    ),
  ),
  http.get('*/api/v1/sessions/:sessionId/materials', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/courses/:courseId/sessions', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/courses/:courseId/materials', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/courses/:courseId/transcripts', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/courses/:courseId/qna', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/courses/:courseId/summaries', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/sessions/:sessionId/questions', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/sessions/:sessionId/jobs', () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get('*/api/v1/sessions/:sessionId/summaries', () =>
    HttpResponse.json({
      summary_status: 'NOT_STARTED' as const,
      summary_reason: null,
      items: [],
      next_cursor: null,
    }),
  ),
  http.post('*/api/v1/realtime-tickets', () =>
    HttpResponse.json(
      {
        error: {
          code: 'COURSE_ACCESS_DENIED',
          message: '이 class에 접근할 권한이 없습니다.',
          request_id: 'req_test',
          details: null,
        },
      },
      { status: 403 },
    ),
  ),
]

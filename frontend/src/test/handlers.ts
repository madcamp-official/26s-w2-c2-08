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
]

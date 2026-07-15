import type { Page, Route } from '@playwright/test'

import {
  completedSession,
  failedMaterial,
  failedMaterialJob,
  professorCourse,
  professorDraftCourse,
  liveProfessorSession,
  liveQuestions,
  liveStudentSession,
  liveTimeline,
  readyMaterial,
  readySession,
  studentCourse,
  studentLiveCourse,
  studentWorkspaceCourse,
  visualUser,
} from './entities'

export type VisualAuth = 'signed-in' | 'signed-out'

interface ApiFixtureResult {
  requested: string[]
  unhandled: string[]
}

const jsonHeaders = {
  'cache-control': 'no-store',
  'content-type': 'application/json; charset=utf-8',
}

export async function installRealtimeSocketFixture(page: Page) {
  await page.addInitScript(() => {
    class VisualWebSocket {
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null
      onmessage: ((event: MessageEvent<string>) => void) | null = null
      onopen: (() => void) | null = null

      constructor() {
        queueMicrotask(() => this.onopen?.())
      }

      close() {
        this.onclose?.()
      }
    }

    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      value: VisualWebSocket,
    })
  })
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    body: JSON.stringify(body),
    headers: jsonHeaders,
    status,
  })
}

function authenticationRequired() {
  return {
    error: {
      code: 'AUTHENTICATION_REQUIRED',
      message: '로그인이 필요합니다.',
      request_id: 'req_visual',
      details: null,
    },
  }
}

export async function installApiFixture(
  page: Page,
  auth: VisualAuth,
): Promise<ApiFixtureResult> {
  const requested: string[] = []
  const unhandled: string[] = []

  await page.route(/\/api\/(?:health|v1\/.*)(?:\?.*)?$/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const key = `${request.method()} ${url.pathname}${url.search}`
    requested.push(key)

    if (request.method() === 'GET' && url.pathname === '/api/health') {
      await fulfillJson(route, { status: 'ok' })
      return
    }

    if (request.method() === 'GET' && url.pathname === '/api/v1/me') {
      await fulfillJson(
        route,
        auth === 'signed-in' ? visualUser : authenticationRequired(),
        auth === 'signed-in' ? 200 : 401,
      )
      return
    }

    if (
      request.method() === 'POST' &&
      url.pathname === '/api/v1/realtime-tickets'
    ) {
      const body = request.postDataJSON() as {
        session_id: string
        scope: 'SESSION_EVENTS_READ' | 'SESSION_AUDIO_WRITE'
      }
      await fulfillJson(route, {
        ticket: 'visual-session-events-ticket',
        session_id: body.session_id,
        scope: body.scope,
        expires_at: '2026-07-15T07:01:00Z',
      })
      return
    }

    if (request.method() === 'GET' && url.pathname === '/api/v1/courses') {
      const role = url.searchParams.get('role')
      const items =
        role === 'PROFESSOR'
          ? [professorCourse]
          : role === 'STUDENT'
            ? [studentCourse]
            : [professorCourse, studentCourse]
      await fulfillJson(route, { items, next_cursor: null })
      return
    }

    const courseDetailMatch = url.pathname.match(
      /^\/api\/v1\/courses\/([^/]+)$/,
    )
    if (request.method() === 'GET' && courseDetailMatch) {
      await fulfillJson(
        route,
        courseDetailMatch[1] === studentCourse.id
          ? studentWorkspaceCourse
          : courseDetailMatch[1] === studentLiveCourse.id
            ? studentLiveCourse
            : courseDetailMatch[1] === professorDraftCourse.id
              ? professorDraftCourse
              : professorCourse,
      )
      return
    }

    const courseSessionsMatch = url.pathname.match(
      /^\/api\/v1\/courses\/([^/]+)\/sessions$/,
    )
    if (request.method() === 'GET' && courseSessionsMatch) {
      await fulfillJson(route, {
        items:
          url.searchParams.get('status') === 'COMPLETED'
            ? [
                {
                  ...completedSession,
                  course_id: courseSessionsMatch[1],
                },
              ]
            : [
                {
                  ...completedSession,
                  course_id: courseSessionsMatch[1],
                },
              ],
        next_cursor: null,
      })
      return
    }

    if (request.method() === 'POST' && courseSessionsMatch) {
      await fulfillJson(
        route,
        { ...readySession, course_id: courseSessionsMatch[1] },
        201,
      )
      return
    }

    const sessionDetailMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)$/,
    )
    if (request.method() === 'GET' && sessionDetailMatch) {
      const sessionId = sessionDetailMatch[1]
      await fulfillJson(
        route,
        sessionId === liveProfessorSession.id
          ? liveProfessorSession
          : sessionId === liveStudentSession.id
            ? liveStudentSession
            : readySession,
      )
      return
    }

    const transcriptMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/transcript$/,
    )
    if (request.method() === 'GET' && transcriptMatch) {
      const sessionId = transcriptMatch[1]
      const session =
        sessionId === liveProfessorSession.id
          ? liveProfessorSession
          : liveStudentSession
      await fulfillJson(
        route,
        liveTimeline(
          session.id,
          session.canonical_transcript_version_id ?? 'missing-version',
        ),
      )
      return
    }

    const sessionQuestionsMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/questions$/,
    )
    if (request.method() === 'GET' && sessionQuestionsMatch) {
      await fulfillJson(route, {
        items: liveQuestions(sessionQuestionsMatch[1] ?? ''),
        next_cursor: null,
      })
      return
    }

    const sessionClustersMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/question-clusters$/,
    )
    if (request.method() === 'GET' && sessionClustersMatch) {
      await fulfillJson(route, {
        scope: 'CURRENT',
        generation: null,
        clustering_state: {
          pending: true,
          requested_through_sequence: 3,
          applied_through_sequence: 0,
          current_revision: 0,
          current_generation: null,
          final_generation: null,
          active_job_id: null,
          retry_job_id: null,
          last_job: null,
        },
        items: [],
        next_cursor: null,
      })
      return
    }

    const sessionAnswersMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/answers$/,
    )
    if (request.method() === 'GET' && sessionAnswersMatch) {
      await fulfillJson(route, { items: [], next_cursor: null })
      return
    }

    const sessionSummariesMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/summaries$/,
    )
    if (request.method() === 'GET' && sessionSummariesMatch) {
      await fulfillJson(route, {
        summary_status: 'NOT_STARTED',
        summary_reason: null,
        items: [],
        next_cursor: null,
      })
      return
    }

    const sessionChatsMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/chats$/,
    )
    if (request.method() === 'GET' && sessionChatsMatch) {
      await fulfillJson(route, { items: [], next_cursor: null })
      return
    }

    const sessionMaterialsMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/materials$/,
    )
    if (request.method() === 'GET' && sessionMaterialsMatch) {
      await fulfillJson(route, {
        items:
          sessionMaterialsMatch[1] === readySession.id
            ? [readyMaterial, failedMaterial]
            : [],
        next_cursor: null,
      })
      return
    }

    const sessionJobsMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/jobs$/,
    )
    if (request.method() === 'GET' && sessionJobsMatch) {
      await fulfillJson(route, {
        items:
          sessionJobsMatch[1] === readySession.id ? [failedMaterialJob] : [],
        next_cursor: null,
      })
      return
    }

    if (request.method() === 'POST' && url.pathname === '/api/v1/courses') {
      await fulfillJson(route, professorCourse, 201)
      return
    }

    if (
      request.method() === 'POST' &&
      url.pathname === '/api/v1/courses/join'
    ) {
      await fulfillJson(route, studentCourse, 201)
      return
    }

    unhandled.push(key)
    await fulfillJson(
      route,
      {
        error: {
          code: 'VISUAL_FIXTURE_MISSING',
          message: '시각 검증 fixture에 등록되지 않은 요청입니다.',
          request_id: 'req_visual',
          details: { method: request.method(), path: url.pathname },
        },
      },
      501,
    )
  })

  return { requested, unhandled }
}

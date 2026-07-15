import type { Page, Route } from '@playwright/test'

import {
  completedAnswer,
  completedJobs,
  completedMaterials,
  completedQuestions,
  completedRecord,
  completedSession,
  completedSummary,
  completedTimeline,
  failedMaterial,
  failedMaterialJob,
  professorCourse,
  professorDraftCourse,
  professorEndedCourse,
  professorEndedSession,
  professorProcessingCourse,
  liveProfessorSession,
  liveQuestions,
  liveStudentSession,
  liveTimeline,
  processingAnswer,
  processingJobs,
  processingProfessorSession,
  processingQuestions,
  processingRecord,
  processingStudentSession,
  processingTimeline,
  readyMaterial,
  readySession,
  studentCourse,
  studentEndedCourse,
  studentEndedSession,
  studentLiveCourse,
  studentProcessingCourse,
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

function endedSessionForId(sessionId: string) {
  if (sessionId === professorEndedSession.id) return professorEndedSession
  if (sessionId === studentEndedSession.id) return studentEndedSession
  return null
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
          : courseDetailMatch[1] === studentEndedCourse.id
            ? studentEndedCourse
            : courseDetailMatch[1] === professorEndedCourse.id
              ? professorEndedCourse
              : courseDetailMatch[1] === studentProcessingCourse.id
                ? studentProcessingCourse
                : courseDetailMatch[1] === professorProcessingCourse.id
                  ? professorProcessingCourse
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
      const endedSession = endedSessionForId(sessionId)
      await fulfillJson(
        route,
        endedSession ??
          (sessionId === liveProfessorSession.id
            ? liveProfessorSession
            : sessionId === liveStudentSession.id
              ? liveStudentSession
              : sessionId === processingProfessorSession.id
                ? processingProfessorSession
                : sessionId === processingStudentSession.id
                  ? processingStudentSession
                  : readySession),
      )
      return
    }

    const sessionRecordMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/record$/,
    )
    if (request.method() === 'GET' && sessionRecordMatch) {
      const endedSession = endedSessionForId(sessionRecordMatch[1])
      if (endedSession) {
        await fulfillJson(route, completedRecord(endedSession))
        return
      }
      const session =
        sessionRecordMatch[1] === processingStudentSession.id
          ? processingStudentSession
          : processingProfessorSession
      await fulfillJson(route, processingRecord(session))
      return
    }

    const transcriptMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/transcript$/,
    )
    if (request.method() === 'GET' && transcriptMatch) {
      const sessionId = transcriptMatch[1]
      const endedSession = endedSessionForId(sessionId)
      if (endedSession) {
        await fulfillJson(route, completedTimeline(endedSession))
        return
      }
      const session =
        sessionId === liveProfessorSession.id
          ? liveProfessorSession
          : sessionId === liveStudentSession.id
            ? liveStudentSession
            : sessionId === processingStudentSession.id
              ? processingStudentSession
              : processingProfessorSession
      await fulfillJson(
        route,
        session.status === 'PROCESSING'
          ? processingTimeline(session)
          : liveTimeline(
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
      const endedSession = endedSessionForId(sessionQuestionsMatch[1])
      if (endedSession) {
        const questions = completedQuestions(endedSession)
        await fulfillJson(route, {
          items:
            url.searchParams.get('status') === 'OPEN'
              ? questions.filter((question) => question.status === 'OPEN')
              : questions,
          next_cursor: null,
        })
        return
      }
      const processingSession =
        sessionQuestionsMatch[1] === processingProfessorSession.id
          ? processingProfessorSession
          : sessionQuestionsMatch[1] === processingStudentSession.id
            ? processingStudentSession
            : null
      await fulfillJson(route, {
        items: processingSession
          ? processingQuestions(processingSession)
          : liveQuestions(sessionQuestionsMatch[1] ?? ''),
        next_cursor: null,
      })
      return
    }

    const sessionClustersMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/question-clusters$/,
    )
    if (request.method() === 'GET' && sessionClustersMatch) {
      const endedSession = endedSessionForId(sessionClustersMatch[1])
      if (endedSession) {
        await fulfillJson(route, {
          scope: 'FINAL',
          clustering_state:
            completedRecord(endedSession).question_clusters.state,
          generation: 3,
          items: [],
          next_cursor: null,
        })
        return
      }
      const processingSession =
        sessionClustersMatch[1] === processingProfessorSession.id
          ? processingProfessorSession
          : sessionClustersMatch[1] === processingStudentSession.id
            ? processingStudentSession
            : null
      if (processingSession) {
        await fulfillJson(route, {
          scope: 'FINAL',
          clustering_state:
            processingRecord(processingSession).question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        })
        return
      }
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
      const endedSession = endedSessionForId(sessionAnswersMatch[1])
      if (endedSession) {
        await fulfillJson(route, {
          items: [completedAnswer(endedSession)],
          next_cursor: null,
        })
        return
      }
      const processingSession =
        sessionAnswersMatch[1] === processingProfessorSession.id
          ? processingProfessorSession
          : sessionAnswersMatch[1] === processingStudentSession.id
            ? processingStudentSession
            : null
      await fulfillJson(route, {
        items: processingSession ? [processingAnswer(processingSession)] : [],
        next_cursor: null,
      })
      return
    }

    const sessionSummariesMatch = url.pathname.match(
      /^\/api\/v1\/sessions\/([^/]+)\/summaries$/,
    )
    if (request.method() === 'GET' && sessionSummariesMatch) {
      const endedSession = endedSessionForId(sessionSummariesMatch[1])
      if (endedSession) {
        await fulfillJson(route, completedSummary(endedSession))
        return
      }
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
      const endedSession = endedSessionForId(sessionMaterialsMatch[1])
      await fulfillJson(route, {
        items: endedSession
          ? completedMaterials(endedSession)
          : sessionMaterialsMatch[1] === readySession.id
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
      const endedSession = endedSessionForId(sessionJobsMatch[1])
      const processingSession =
        sessionJobsMatch[1] === processingProfessorSession.id
          ? processingProfessorSession
          : sessionJobsMatch[1] === processingStudentSession.id
            ? processingStudentSession
            : null
      const requestedJobType = url.searchParams.get('job_type')
      const processingItems = processingSession
        ? processingJobs(processingSession).filter(
            (job) => !requestedJobType || job.job_type === requestedJobType,
          )
        : []
      const completedItems = endedSession
        ? completedJobs(endedSession).filter(
            (job) => !requestedJobType || job.job_type === requestedJobType,
          )
        : []
      await fulfillJson(route, {
        items: endedSession
          ? completedItems
          : processingSession
            ? processingItems
            : sessionJobsMatch[1] === readySession.id
              ? [failedMaterialJob]
              : [],
        next_cursor: null,
      })
      return
    }

    const recordingPlaybackMatch = url.pathname.match(
      /^\/api\/v1\/recordings\/([^/]+)\/playback$/,
    )
    if (request.method() === 'GET' && recordingPlaybackMatch) {
      await route.fulfill({
        body: '',
        headers: {
          'accept-ranges': 'bytes',
          'cache-control': 'no-store',
          'content-length': '0',
          'content-type': 'audio/webm',
        },
        status: 200,
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

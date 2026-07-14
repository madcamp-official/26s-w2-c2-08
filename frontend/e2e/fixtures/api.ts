import type { Page, Route } from '@playwright/test'

import { professorCourse, studentCourse, visualUser } from './entities'

export type VisualAuth = 'signed-in' | 'signed-out'

interface ApiFixtureResult {
  requested: string[]
  unhandled: string[]
}

const jsonHeaders = {
  'cache-control': 'no-store',
  'content-type': 'application/json; charset=utf-8',
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

    if (request.method() === 'POST' && url.pathname === '/api/v1/courses') {
      await fulfillJson(route, professorCourse, 201)
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

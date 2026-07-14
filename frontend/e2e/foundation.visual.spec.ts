import { expect, test } from '@playwright/test'

import { installApiFixture, type VisualAuth } from './fixtures/api'
import {
  collectRuntimeErrors,
  settleVisualPage,
  verifyVisualPage,
} from './support/visual-checks'

interface FoundationScenario {
  auth: VisualAuth
  checkpoint?: {
    level: number
    name: string
  }
  heading: string
  path: string
  requiredRequests: string[]
  screenId: string
}

const scenarios: FoundationScenario[] = [
  {
    screenId: 'MAIN_PAGE',
    path: '/',
    auth: 'signed-out',
    heading: '강의의 흐름을 놓치지 않도록',
    checkpoint: { level: 3, name: '실시간 Transcript' },
    requiredRequests: ['GET /api/v1/me'],
  },
  {
    screenId: 'LOGIN_PAGE',
    path: '/login',
    auth: 'signed-out',
    heading: '강의의 흐름으로 다시 들어오세요.',
    checkpoint: { level: 2, name: '로그인' },
    requiredRequests: ['GET /api/v1/me'],
  },
  {
    screenId: 'EMAIL_SIGNUP_PAGE',
    path: '/signup',
    auth: 'signed-out',
    heading: '나만의 강의 흐름을 시작하세요.',
    requiredRequests: ['GET /api/v1/me'],
  },
  {
    screenId: 'MAIN_PAGE_AUTH',
    path: '/',
    auth: 'signed-in',
    heading: '김도현님, 오늘의 강의를 이어가세요.',
    requiredRequests: [
      'GET /api/v1/me',
      'GET /api/v1/courses?role=PROFESSOR&limit=100',
      'GET /api/v1/courses?role=STUDENT&limit=100',
    ],
  },
  {
    screenId: 'MY_INFO_PAGE',
    path: '/account',
    auth: 'signed-in',
    heading: '내 정보',
    requiredRequests: ['GET /api/v1/me'],
  },
  {
    screenId: 'COURSE_CREATE_PAGE',
    path: '/courses/new',
    auth: 'signed-in',
    heading: '한 학기 Course 만들기',
    requiredRequests: ['GET /api/v1/me'],
  },
  {
    screenId: 'COURSE_JOIN_PAGE',
    path: '/courses/join',
    auth: 'signed-in',
    heading: '참여 코드로 들어가기',
    requiredRequests: ['GET /api/v1/me'],
  },
]

for (const scenario of scenarios) {
  test(`${scenario.screenId} renders from its production route`, async ({
    page,
  }, testInfo) => {
    const runtimeErrors = collectRuntimeErrors(
      page,
      scenario.auth === 'signed-out' ? [/401 \(Unauthorized\)/] : [],
    )
    const api = await installApiFixture(page, scenario.auth)

    await page.goto(scenario.path)
    await expect(
      page.getByRole('heading', { level: 1, name: scenario.heading }),
    ).toBeVisible()
    if (scenario.checkpoint) {
      await expect(page.getByRole('heading', scenario.checkpoint)).toBeVisible()
    }
    await settleVisualPage(page)
    await verifyVisualPage(page, testInfo, runtimeErrors, {
      requiredRequests: scenario.requiredRequests,
      screenId: scenario.screenId,
      unhandledRequests: api.unhandled,
      requested: api.requested,
    })
  })
}

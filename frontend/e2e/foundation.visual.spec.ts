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
    checkpoint: { level: 2, name: '이메일 계정 만들기' },
    requiredRequests: ['GET /api/v1/me'],
  },
  {
    screenId: 'MAIN_PAGE_AUTH',
    path: '/',
    auth: 'signed-in',
    heading: '김도현님, 오늘의 강의를 이어가세요.',
    checkpoint: { level: 2, name: '그래프 탐색과 최단 경로' },
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
    checkpoint: { level: 2, name: 'Course별 역할' },
    requiredRequests: [
      'GET /api/v1/me',
      'GET /api/v1/courses?role=PROFESSOR&limit=100',
      'GET /api/v1/courses?role=STUDENT&limit=100',
    ],
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

test('COURSE_CREATE_PAGE success renders from its production mutation', async ({
  page,
}, testInfo) => {
  const runtimeErrors = collectRuntimeErrors(page)
  const api = await installApiFixture(page, 'signed-in')

  await page.goto('/courses/new')
  await page.getByLabel('과목명').fill('데이터 구조와 알고리즘')
  await page.getByLabel('학기').fill('2026 여름학기')
  await page.getByRole('button', { name: 'Course 만들기' }).click()
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: '데이터 구조와 알고리즘 Course를 만들었습니다',
    }),
  ).toBeFocused()
  await page.evaluate(() => window.scrollTo(0, 0))
  await settleVisualPage(page)
  await verifyVisualPage(page, testInfo, runtimeErrors, {
    requiredRequests: ['GET /api/v1/me', 'POST /api/v1/courses'],
    screenId: 'COURSE_CREATE_PAGE_SUCCESS',
    unhandledRequests: api.unhandled,
    requested: api.requested,
  })
})

test('MY_INFO_PAGE keeps keyboard focus inside the logout dialog and returns it', async ({
  page,
}) => {
  const api = await installApiFixture(page, 'signed-in')
  await page.goto('/account')
  await expect(
    page.getByRole('heading', { level: 1, name: '내 정보' }),
  ).toBeVisible()

  const trigger = page.getByRole('button', { name: '로그아웃' })
  await trigger.click()
  const dialog = page.getByRole('dialog', {
    name: 'GOAL에서 로그아웃할까요?',
  })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator(':focus')).toHaveCount(1)

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
  expect(api.unhandled).toEqual([])
})

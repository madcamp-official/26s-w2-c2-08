import { expect, test } from '@playwright/test'

import {
  installApiFixture,
  installRealtimeSocketFixture,
  type VisualAuth,
} from './fixtures/api'
import {
  professorCourse,
  professorDraftCourse,
  professorProcessingCourse,
  liveProfessorSession,
  liveStudentSession,
  processingProfessorSession,
  processingStudentSession,
  readySession,
  studentCourse,
  studentLiveCourse,
  studentProcessingCourse,
} from './fixtures/entities'
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
  realtime?: boolean
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
  {
    screenId: 'COURSE_PAGE_PROF',
    path: `/courses/${professorCourse.id}`,
    auth: 'signed-in',
    heading: '데이터 구조와 알고리즘',
    checkpoint: { level: 2, name: '수업 운영 개요' },
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/courses/${professorCourse.id}`,
      `GET /api/v1/courses/${professorCourse.id}/sessions?status=COMPLETED&limit=20`,
    ],
  },
  {
    screenId: 'COURSE_PAGE_STUD',
    path: `/courses/${studentCourse.id}`,
    auth: 'signed-in',
    heading: '운영체제',
    checkpoint: { level: 2, name: '학생 학습 공간' },
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/courses/${studentCourse.id}`,
      `GET /api/v1/courses/${studentCourse.id}/sessions?status=COMPLETED&limit=20`,
    ],
  },
  {
    screenId: 'CLASS_CREATE_PAGE',
    path: `/courses/${professorDraftCourse.id}/sessions/new`,
    auth: 'signed-in',
    heading: '오늘의 class 준비',
    checkpoint: { level: 2, name: '기본 정보 입력' },
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/courses/${professorDraftCourse.id}`,
    ],
  },
  {
    screenId: 'LIVE_CLASS_PAGE_PROF',
    path: `/sessions/${liveProfessorSession.id}`,
    auth: 'signed-in',
    heading: liveProfessorSession.title,
    checkpoint: { level: 2, name: '실시간 강의 내용' },
    realtime: true,
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/sessions/${liveProfessorSession.id}`,
      `GET /api/v1/courses/${professorCourse.id}`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/transcript?limit=100`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/answers?limit=100`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/questions?sort=POPULAR&limit=20`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/question-clusters?scope=CURRENT&limit=20`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/summaries?summary_type=LIVE&limit=20`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/chats?limit=20`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/materials?limit=100`,
      `GET /api/v1/sessions/${liveProfessorSession.id}/jobs?job_type=MATERIAL_PROCESSING&limit=100`,
      'POST /api/v1/realtime-tickets',
    ],
  },
  {
    screenId: 'LIVE_CLASS_PAGE_STUD',
    path: `/sessions/${liveStudentSession.id}`,
    auth: 'signed-in',
    heading: liveStudentSession.title,
    checkpoint: { level: 2, name: '실시간 강의 내용' },
    realtime: true,
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/sessions/${liveStudentSession.id}`,
      `GET /api/v1/courses/${studentLiveCourse.id}`,
      `GET /api/v1/sessions/${liveStudentSession.id}/transcript?limit=100`,
      `GET /api/v1/sessions/${liveStudentSession.id}/questions?sort=POPULAR&limit=20`,
      `GET /api/v1/sessions/${liveStudentSession.id}/question-clusters?scope=CURRENT&limit=20`,
      `GET /api/v1/sessions/${liveStudentSession.id}/summaries?summary_type=LIVE&limit=20`,
      `GET /api/v1/sessions/${liveStudentSession.id}/chats?limit=20`,
      'POST /api/v1/realtime-tickets',
    ],
  },
  {
    screenId: 'CLASS_PROCESSING_STATE_PROF',
    path: `/sessions/${processingProfessorSession.id}`,
    auth: 'signed-in',
    heading: processingProfessorSession.title,
    checkpoint: { level: 2, name: '수업 후처리 작업' },
    realtime: true,
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/sessions/${processingProfessorSession.id}`,
      `GET /api/v1/courses/${professorProcessingCourse.id}`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/record`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/materials?limit=100`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/jobs?job_type=MATERIAL_PROCESSING&limit=100`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/transcript?transcript_version_id=${processingProfessorSession.canonical_transcript_version_id}&limit=100`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/questions?sort=RECENT&limit=20`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/question-clusters?scope=FINAL&limit=20`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/answers?limit=20`,
      `GET /api/v1/sessions/${processingProfessorSession.id}/jobs?limit=20`,
      'POST /api/v1/realtime-tickets',
    ],
  },
  {
    screenId: 'CLASS_PROCESSING_STATE_STUD',
    path: `/sessions/${processingStudentSession.id}`,
    auth: 'signed-in',
    heading: processingStudentSession.title,
    checkpoint: { level: 2, name: '수업 후처리 작업' },
    realtime: true,
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/sessions/${processingStudentSession.id}`,
      `GET /api/v1/courses/${studentProcessingCourse.id}`,
      `GET /api/v1/sessions/${processingStudentSession.id}/record`,
      `GET /api/v1/sessions/${processingStudentSession.id}/materials?limit=100`,
      `GET /api/v1/sessions/${processingStudentSession.id}/transcript?transcript_version_id=${processingStudentSession.canonical_transcript_version_id}&limit=100`,
      `GET /api/v1/sessions/${processingStudentSession.id}/questions?sort=RECENT&limit=20`,
      `GET /api/v1/sessions/${processingStudentSession.id}/question-clusters?scope=FINAL&limit=20`,
      `GET /api/v1/sessions/${processingStudentSession.id}/answers?limit=20`,
      `GET /api/v1/sessions/${processingStudentSession.id}/jobs?limit=20`,
      'POST /api/v1/realtime-tickets',
    ],
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
    if (scenario.realtime) await installRealtimeSocketFixture(page)
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

test('COURSE_JOIN_PAGE success renders from its production mutation', async ({
  page,
}, testInfo) => {
  const runtimeErrors = collectRuntimeErrors(page)
  const api = await installApiFixture(page, 'signed-in')

  await page.goto('/courses/join')
  await page.getByLabel('참여 코드').fill('GOALAB')
  await page.getByRole('button', { name: 'Course 참여하기' }).click()
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: '운영체제 Course에 참여했습니다',
    }),
  ).toBeFocused()
  await page.evaluate(() => window.scrollTo(0, 0))
  await settleVisualPage(page)
  await verifyVisualPage(page, testInfo, runtimeErrors, {
    requiredRequests: ['GET /api/v1/me', 'POST /api/v1/courses/join'],
    screenId: 'COURSE_JOIN_PAGE_SUCCESS',
    unhandledRequests: api.unhandled,
    requested: api.requested,
  })
})

test('CLASS_CREATE_PAGE READY state renders from its production mutation', async ({
  page,
}, testInfo) => {
  const runtimeErrors = collectRuntimeErrors(page)
  await installRealtimeSocketFixture(page)
  const api = await installApiFixture(page, 'signed-in')

  await page.goto(`/courses/${professorDraftCourse.id}/sessions/new`)
  await page.getByLabel('class 제목 (선택)').fill(readySession.title)
  await page.getByLabel(/^수업 날짜/).fill(readySession.lecture_date)
  await page.getByRole('button', { name: 'class 만들기' }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: readySession.title }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { level: 2, name: '수업 시작 준비' }),
  ).toBeVisible()
  await settleVisualPage(page)
  await verifyVisualPage(page, testInfo, runtimeErrors, {
    requiredRequests: [
      'GET /api/v1/me',
      `GET /api/v1/courses/${professorDraftCourse.id}`,
      `POST /api/v1/courses/${professorDraftCourse.id}/sessions`,
      `GET /api/v1/sessions/${readySession.id}`,
      `GET /api/v1/sessions/${readySession.id}/materials?limit=100`,
      `GET /api/v1/sessions/${readySession.id}/jobs?job_type=MATERIAL_PROCESSING&limit=100`,
      'POST /api/v1/realtime-tickets',
    ],
    screenId: 'CLASS_CREATE_PAGE_READY',
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

test('COURSE_PAGE_PROF keeps the mobile class rail disclosure keyboard-operable', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== '375')
  const api = await installApiFixture(page, 'signed-in')
  await page.goto(`/courses/${professorCourse.id}`)

  const trigger = page.getByText('class 목록 열기·닫기', { exact: true })
  await expect(trigger).toBeVisible()
  await expect(page.getByRole('link', { name: 'class 보기' })).toBeHidden()
  await trigger.click()
  await expect(page.getByRole('link', { name: 'class 보기' })).toBeVisible()
  await trigger.click()
  await expect(trigger).toBeFocused()
  expect(api.unhandled).toEqual([])
})

test('COURSE_PAGE_PROF returns focus after cancelling join-code rotation', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== '1440')
  const api = await installApiFixture(page, 'signed-in')
  await page.goto(`/courses/${professorCourse.id}`)

  const trigger = page.getByRole('button', { name: '새 코드로 교체' })
  await trigger.click()
  const dialog = page.getByRole('dialog', {
    name: '참여 코드를 새로 만들까요?',
  })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator(':focus')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
  expect(api.unhandled).toEqual([])
})

test('CLASS_CREATE_PAGE READY delete dialog traps and returns keyboard focus', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== '1440')
  const runtimeErrors = collectRuntimeErrors(page)
  await installRealtimeSocketFixture(page)
  const api = await installApiFixture(page, 'signed-in')
  await page.goto(`/sessions/${readySession.id}`)
  await expect(
    page.getByRole('heading', { level: 1, name: readySession.title }),
  ).toBeVisible()

  const trigger = page.getByRole('button', { name: 'class 삭제' })
  await trigger.click()
  const dialog = page.getByRole('dialog', {
    name: 'READY class를 삭제할까요?',
  })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator(':focus')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
  expect(api.unhandled).toEqual([])
  expect(runtimeErrors).toEqual([])
})

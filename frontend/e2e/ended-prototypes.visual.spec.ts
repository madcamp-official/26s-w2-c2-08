import { expect, test, type Page, type TestInfo } from '@playwright/test'

const prototypes = [
  {
    screenId: 'ENDED_CLASS_PAGE_PROF',
    path: '/class-ended-professor.html',
    title: '그래프 탐색과 최단 경로',
  },
  {
    screenId: 'ENDED_CLASS_PAGE_STUD',
    path: '/class-ended-student.html',
    title: 'CNN과 이미지 분류',
  },
]

async function verifyPrototypePage(
  page: Page,
  testInfo: TestInfo,
  screenId: string,
) {
  await expect(
    page.getByRole('heading', {
      level: 2,
      name: '복습할 수업 기록이 준비되었습니다',
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('navigation', { name: '완료 기록 목차' }),
  ).toHaveCount(1)
  await expect(
    page.getByRole('navigation', { name: '완료 기록 목차' }).getByRole('link'),
  ).toHaveCount(9)

  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1)

  const undersized = await page
    .locator(
      '.button, .record-toc a, input:not(.sr-only), select, textarea, .icon-button',
    )
    .evaluateAll((elements) =>
      elements
        .filter((element) => {
          const htmlElement = element as HTMLElement
          return !htmlElement.hidden && htmlElement.offsetParent !== null
        })
        .map((element) => {
          const box = element.getBoundingClientRect()
          return {
            label:
              element.getAttribute('aria-label') ||
              element.textContent?.trim().slice(0, 60) ||
              element.tagName,
            height: box.height,
            width: box.width,
          }
        })
        .filter(({ height, width }) => height < 44 || width < 44),
    )
  expect(undersized).toEqual([])

  const screenshotPath = testInfo.outputPath(
    'visual',
    `${screenId}--${testInfo.project.name}.png`,
  )
  await page.screenshot({
    animations: 'disabled',
    fullPage: true,
    path: screenshotPath,
  })
}

for (const prototype of prototypes) {
  test(`${prototype.screenId} static prototype matches the production design system`, async ({
    page,
  }, testInfo) => {
    await page.goto(prototype.path)
    await expect(
      page.getByRole('heading', { level: 1, name: prototype.title }),
    ).toBeVisible()
    await verifyPrototypePage(page, testInfo, prototype.screenId)
  })
}

test('professor prototype keeps completed-record controls accessible', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== '1440')
  await page.goto(
    '/class-ended-professor.html?transcript=failed&summary=source-unavailable&jobs=partial-failure',
  )

  const retry = page.getByRole('button', {
    name: '고품질 Transcript 재시도',
  })
  await expect(retry).toBeVisible()
  await retry.click()
  await expect(page.locator('[data-recording-job-status]')).toHaveText(
    'PENDING',
  )

  const composer = page.locator('#textAnswerForm')
  await composer.getByRole('button', { name: '텍스트 Answer 등록' }).click()
  await expect(composer.getByRole('alert')).toHaveText('답변을 입력해 주세요.')
  await composer
    .getByLabel('교수자 답변')
    .fill('배열은 최소 원소 선택이 선형 탐색이 되어 전체 복잡도가 커집니다.')
  await expect(composer.locator('[data-text-answer-count]')).toContainText(
    '/ 2,000자',
  )
  await expect(composer.locator('[data-text-answer-count]')).not.toHaveText(
    '0 / 2,000자',
  )
  await composer.getByRole('button', { name: '텍스트 Answer 등록' }).click()
  await expect(
    page.getByRole('heading', {
      level: 3,
      name: '힙 대신 배열을 쓰면 얼마나 느려지나요?',
    }),
  ).toBeVisible()

  const deleteTrigger = page.getByRole('button', { name: '완료 녹음 삭제' })
  await deleteTrigger.click()
  const dialog = page.getByRole('dialog', { name: '완료 녹음을 삭제할까요?' })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator(':focus')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(deleteTrigger).toBeFocused()
  await deleteTrigger.click()
  await dialog.getByRole('button', { name: '완료 녹음 삭제' }).click()
  await expect(page.locator('[data-recording-player]')).toBeHidden()
  await expect(page.getByRole('heading', { name: '수업 녹음' })).toBeFocused()
  await expect(
    page.getByRole('heading', { name: 'Final Transcript' }),
  ).toBeVisible()
})

test('student prototype never exposes professor retry controls', async ({
  page,
}) => {
  await page.goto(
    '/class-ended-student.html?transcript=failed&summary=source-unavailable&jobs=partial-failure',
  )
  await expect(
    page.getByRole('button', { name: '고품질 Transcript 재시도' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: '완료 녹음 삭제' }),
  ).toHaveCount(0)
})

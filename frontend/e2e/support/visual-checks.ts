import { expect, type Page, type TestInfo } from '@playwright/test'

interface VisualCheckOptions {
  requiredRequests: string[]
  screenId: string
  unhandledRequests: string[]
  requested: string[]
}

export function collectRuntimeErrors(
  page: Page,
  ignoredConsolePatterns: RegExp[] = [],
) {
  const errors: string[] = []
  page.on('console', (message) => {
    const text = message.text()
    if (
      message.type() === 'error' &&
      !ignoredConsolePatterns.some((pattern) => pattern.test(text))
    ) {
      errors.push(text)
    }
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

export async function settleVisualPage(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    )
  })
}

export async function verifyVisualPage(
  page: Page,
  testInfo: TestInfo,
  runtimeErrors: string[],
  options: VisualCheckOptions,
) {
  const layout = await page.evaluate(() => {
    const root = document.documentElement
    const selectors = [
      'button',
      '.button',
      'nav a',
      'input:not([type="checkbox"]):not([type="radio"])',
      'select',
      'textarea',
    ]
    const smallControls = Array.from(
      document.querySelectorAll<HTMLElement>(selectors.join(',')),
    )
      .filter((element) => {
        const style = getComputedStyle(element)
        const rect = element.getBoundingClientRect()
        return (
          style.display !== 'none' &&
          style.visibility !== 'hidden' &&
          rect.width > 0 &&
          rect.height > 0 &&
          (rect.width < 44 || rect.height < 44)
        )
      })
      .map((element) => ({
        label:
          element.getAttribute('aria-label') ??
          element.textContent?.trim().slice(0, 80) ??
          element.tagName,
        rect: {
          width: Math.round(element.getBoundingClientRect().width),
          height: Math.round(element.getBoundingClientRect().height),
        },
      }))

    return {
      clientWidth: root.clientWidth,
      scrollWidth: root.scrollWidth,
      smallControls,
    }
  })

  expect(
    layout.scrollWidth,
    `horizontal overflow: ${JSON.stringify(layout)}`,
  ).toBeLessThanOrEqual(layout.clientWidth + 1)
  expect(
    layout.smallControls,
    'visible primary controls smaller than 44px',
  ).toEqual([])
  expect(
    options.unhandledRequests,
    'unhandled visual fixture requests',
  ).toEqual([])
  for (const required of options.requiredRequests) {
    expect(
      options.requested,
      `missing contract request: ${required}`,
    ).toContain(required)
  }
  expect(runtimeErrors, 'browser console or page errors').toEqual([])

  const screenshotPath = testInfo.outputPath(
    'visual',
    `${options.screenId}--${testInfo.project.name}.png`,
  )
  await page.screenshot({
    animations: 'disabled',
    caret: 'hide',
    fullPage: true,
    path: screenshotPath,
  })
  await testInfo.attach(`${options.screenId}-${testInfo.project.name}`, {
    contentType: 'image/png',
    path: screenshotPath,
  })
}

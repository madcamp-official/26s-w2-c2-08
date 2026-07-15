import { defineConfig } from '@playwright/test'

const port = 4173
const baseURL = `http://127.0.0.1:${port}`
const ci = Boolean(process.env.CI)

export default defineConfig({
  testDir: './e2e',
  testMatch: 'ended-prototypes.visual.spec.ts',
  outputDir: 'test-results/prototypes',
  fullyParallel: true,
  forbidOnly: ci,
  retries: ci ? 1 : 0,
  workers: ci ? 1 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: [['line']],
  use: {
    baseURL,
    browserName: 'chromium',
    colorScheme: 'light',
    contextOptions: { reducedMotion: 'reduce' },
    locale: 'ko-KR',
    serviceWorkers: 'block',
    timezoneId: 'Asia/Seoul',
    trace: 'retain-on-failure',
    video: 'off',
  },
  projects: [
    { name: '1440', use: { viewport: { width: 1440, height: 1_000 } } },
    { name: '768', use: { viewport: { width: 768, height: 1_024 } } },
    { name: '375', use: { viewport: { width: 375, height: 812 } } },
  ],
  webServer: {
    command: `python3 -m http.server ${port} --directory ../docs/prototypes`,
    url: baseURL,
    reuseExistingServer: !ci,
    timeout: 120_000,
  },
})

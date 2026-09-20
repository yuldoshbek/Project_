/**
 * Playwright: проверки на живой системе и снимки экранов.
 *
 * Снимки — не украшение отчёта, а способ увидеть то, что не ловится ни одним другим
 * тестом: нижняя панель под жест-полосой, горизонтальная прокрутка на 390 px, серый текст
 * на сером фоне в приглушённой теме. Поэтому они делаются на трёх размерах и в двух темах
 * и прикладываются к отчёту блока.
 *
 * Сервер не поднимается отсюда: и backend, и интерфейс уже подняты — командой `make dev`
 * на машине разработчика, отдельным шагом в конвейере. Так проверяется то же, что видит
 * человек, а не собранная по случаю копия.
 */

import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.ORBITA_E2E_URL ?? 'http://localhost:5173';

export default defineConfig({
  testDir: './e2e',
  // Снимки складываются рядом с отчётом блока: они часть доказательства, а не мусор сборки.
  outputDir: './test-results',
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL,
    locale: 'ru-RU',
    timezoneId: 'Asia/Tashkent',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});

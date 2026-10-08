/**
 * Playwright: проверки на живой системе и снимки экранов.
 *
 * Снимки — не украшение отчёта, а способ увидеть то, что не ловится ни одним другим
 * тестом: нижняя панель под жест-полосой, горизонтальная прокрутка на 390 px, серый текст
 * на сером фоне в приглушённой теме. Поэтому они делаются на трёх размерах и в двух темах
 * и прикладываются к отчёту блока.
 *
 * Где идут сценарии (`e2e/stand.ts`):
 * - **на машине разработчика** — на своём стенде: API на свежей базе `orbita_e2e` и
 *   собранный интерфейс, как в конвейере. Стенд поднимается отсюда и гасится после прогона;
 *   окно разработки (`make dev`, база разработки) прогон не трогает;
 * - **в конвейере** — серверы подняты отдельными шагами, адрес приходит в `ORBITA_E2E_URL`;
 * - **по уже поднятым серверам** — `ORBITA_E2E_URL=http://localhost:5173 make e2e`.
 *
 * Интерфейс стенда — сборка, а не режим разработки: Vite в режиме разработки собирает
 * модуль раздела при первом заходе, и первые сценарии не дожидались экрана за 7 с
 * (наблюдалось на полном прогоне 06.10.2026). В конвейере сценарии тоже идут по сборке.
 */

import { defineConfig, devices } from '@playwright/test';

import {
  LOCAL_STAND,
  STAND_API_PORT,
  STAND_DB_ENV,
  STAND_URL,
  STAND_WEB_PORT,
  withEnv,
} from './e2e/stand';

const baseURL = process.env.ORBITA_E2E_URL ?? STAND_URL;
const vite = 'node node_modules/vite/bin/vite.js';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/warmup.ts',
  // Снимки складываются рядом с отчётом блока: они часть доказательства, а не мусор сборки.
  outputDir: './test-results',
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  // Один повтор — и в конвейере, и на машине разработки. На двух ядрах рядом с браузером и
  // Docker ответ API эпизодически задерживался на 3–8 с при пороге ожидания 7 с, хотя сам
  // Пульт считается за 0,2 с (замер 06.10.2026). Прошедший со второй попытки сценарий
  // отчёт помечает «flaky» — неустойчивость видна, а настоящая поломка падает оба раза.
  retries: 1,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL,
    locale: 'ru-RU',
    timezoneId: 'Asia/Tashkent',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  // Не переиспользуется ни один сервер: база стенда должна быть свежей на каждом прогоне,
  // а чужой процесс на порту — это повод остановиться, а не прогнать сценарии мимо стенда.
  ...(LOCAL_STAND && {
    webServer: [
      {
        command: `uv run python -m app.e2e_stand --port ${STAND_API_PORT}`,
        cwd: '../backend',
        url: `http://127.0.0.1:${STAND_API_PORT}/api/health`,
        env: withEnv({ ...STAND_DB_ENV, ORBITA_BASE_URL: STAND_URL }),
        reuseExistingServer: false,
        timeout: 180_000,
        // Журнал API стенда — для разбора падения: ORBITA_E2E_STAND_LOG=1 make e2e.
        stdout: process.env.ORBITA_E2E_STAND_LOG ? 'pipe' : 'ignore',
        stderr: 'pipe',
      },
      {
        command: `${vite} build && ${vite} preview --port ${STAND_WEB_PORT} --strictPort`,
        url: STAND_URL,
        env: withEnv({ ORBITA_API_TARGET: `http://127.0.0.1:${STAND_API_PORT}` }),
        reuseExistingServer: false,
        timeout: 180_000,
        stdout: 'ignore',
        stderr: 'pipe',
      },
    ],
  }),

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});

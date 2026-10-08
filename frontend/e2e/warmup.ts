/**
 * Прогрев стенда перед сценариями (`globalSetup`).
 *
 * Свежий API на свежей базе первый Пульт считает дольше: импорты, кеши запросов,
 * первая сессия. На машине разработки (2 ядра, рядом браузер и Docker) первый сценарий
 * с открытием Пульта из-за этого не дожидался заголовка за 7 с — падал первым в каждом
 * прогоне (06.10.2026). Прогрев открывает Пульт один раз заранее тем же путём, что человек:
 * по личной ссылке в настоящем браузере. В конвейере и по чужим серверам — не нужен.
 */

import { chromium } from '@playwright/test';

import { issueLink } from './link';
import { LOCAL_STAND } from './stand';

export default async function warmup(): Promise<void> {
  if (!LOCAL_STAND) return;
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(issueLink('assistant'));
    await page.getByRole('heading', { name: 'Пульт', level: 1 }).waitFor({ timeout: 60_000 });
  } finally {
    await browser.close();
  }
}

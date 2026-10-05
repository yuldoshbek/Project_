/**
 * Монитор (`sections/meeting/`) — многопанельный обзор и режим «Совещание» на настоящем API.
 *
 * 1. На мониторе Пульт показывает панели разделов рядом с лестницей; на ноутбуке их нет.
 * 2. «Совещание» проходит повестку на большом мониторе без служебных элементов: экран
 *    закрывает приложение целиком, листается стрелками, Esc возвращает Пульт (критерий 2).
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

let leader: string;

test.beforeAll(() => {
  leader = issueLink('leader');
});

async function open(page: Page, theme: 'light' | 'dim' = 'light') {
  await page.goto(leader);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Пульт', level: 1 })).toBeVisible();
}

test('монитор: панели разделов рядом с Пультом', async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1440 });
  await open(page);
  const overview = page.getByRole('region', { name: 'Обзор разделов' });
  await expect(
    overview.getByRole('heading', { name: 'Готовы ли к дате и кто задерживает?' }),
  ).toBeVisible();
  await expect(overview.getByRole('heading', { name: 'Что ждёт моего «да»?' })).toBeVisible();
  await expect(overview.getByRole('heading', { name: 'Где неделя перегружена?' })).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/monitor-overview-light.png`,
    animations: 'disabled',
  });

  await overview.getByRole('button', { name: 'Открыть «Идеи и карты»' }).click();
  await expect(page.getByRole('heading', { name: 'Идеи и карты', level: 1 })).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Пульт', level: 1 })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Обзор разделов' })).toHaveCount(0);
});

for (const theme of ['light', 'dim'] as const) {
  test(`совещание на мониторе — повестка без служебных элементов, тема ${theme}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    await open(page, theme);
    await page.getByRole('button', { name: 'Совещание' }).click();
    const meeting = page.getByRole('dialog', { name: 'Совещание: один вопрос на экран' });
    await expect(meeting.getByRole('heading', { name: 'Что требует внимания?' })).toBeVisible();

    // Экран закрывает приложение целиком: боковая панель и шапка под ним.
    const box = await meeting.boundingBox();
    expect(box).toEqual({ x: 0, y: 0, width: 2560, height: 1440 });
    const covered = await page.evaluate(() => {
      const hit = document.elementFromPoint(100, 100);
      return hit?.closest('[role="dialog"]') !== null;
    });
    expect(covered, 'боковая панель видна поверх совещания').toBe(true);

    const counter = meeting.getByText(/^\d+ \/ \d+$/);
    const total = Number((await counter.textContent())?.split('/')[1]);
    expect(total).toBeGreaterThanOrEqual(5);
    await page.screenshot({
      path: `${REPORT_DIR}/meeting-1-monitor-${theme}.png`,
      animations: 'disabled',
    });

    for (let at = 2; at <= total; at += 1) {
      await page.keyboard.press('ArrowRight');
      await expect(counter).toHaveText(`${at} / ${total}`);
      if (at === 2) {
        await page.screenshot({
          path: `${REPORT_DIR}/meeting-2-monitor-${theme}.png`,
          animations: 'disabled',
        });
      }
    }
    await page.keyboard.press('Escape');
    await expect(meeting).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Пульт', level: 1 })).toBeVisible();
  });
}

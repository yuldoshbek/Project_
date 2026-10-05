/**
 * Доклады и мероприятия (`sections/reports/`) — на настоящем API (`/api/v1/preparations…`) и
 * вымышленных данных базы (`backend/app/demo_preparations.py`).
 *
 * 1. Раздел на трёх устройствах в двух темах, без горизонтальной прокрутки.
 * 2. «Готовы ли к дате и кто задерживает?» отвечает фразой; карточка показывает, кто
 *    задерживает, и готовит напоминание (критерий 5 блока 2); цели нажатия на телефоне —
 *    не меньше 44 px.
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;

let leader: string;
let assistant: string;

test.beforeAll(() => {
  leader = issueLink('leader');
  assistant = issueLink('assistant');
});

async function open(page: Page, link: string, theme: (typeof THEMES)[number] = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: 'Доклады', level: 1 })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Доклады: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await open(page, leader, theme);
      await expect(
        page.getByRole('heading', { name: 'Готовы ли к дате и кто задерживает?' }),
      ).toBeVisible();
      await page.screenshot({
        path: `${REPORT_DIR}/reports-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);
    });
  }
}

test('кто задерживает и напоминание — карточка на телефоне', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, assistant);
  await page.getByRole('button', { name: 'Открыть подготовку' }).click();
  const card = page.getByRole('dialog', { name: 'Карточка подготовки' });
  await expect(card.getByRole('heading', { name: 'Кто задерживает' })).toBeVisible();
  await expect(card.getByRole('button', { name: 'Напомнить' }).first()).toBeVisible();

  // У чекбокса цель — подпись вокруг него: квадратик 20 px нажимается вместе с текстом.
  const targets = card.locator(
    'button:visible, input:not([type="checkbox"]):visible, select:visible, label:has(input[type="checkbox"])',
  );
  const count = await targets.count();
  for (let index = 0; index < count; index += 1) {
    const box = await targets.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `цель ${index}`).toBeGreaterThanOrEqual(44);
  }
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/reports-card-phone-light.png`,
    animations: 'disabled',
  });
});

/**
 * Программы — экран на утверждение, вымышленные данные (`sections/programs/demo.ts`).
 *
 * Снимки трёх устройств в двух темах; горизонт лет с раскрытыми подпроектами и карточка
 * программы на ноутбуке; плитки и карточка на телефоне — без горизонтальной прокрутки и с
 * целями нажатия не меньше 44 px. Сценарии ничего не пишут: раздел только читает.
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;

const MIN_TOUCH_TARGET = 44;

let link: string;

test.beforeAll(() => {
  link = issueLink('assistant');
});

/**
 * Вымышленные даты считаются от сегодняшнего дня, а вердикт «успеваем?» зависит от того,
 * сколько дней до даты программы: без закреплённого дня сценарии падали бы с января.
 * Раздел данных у сервера не спрашивает, поэтому закреплённое время страницы ничего не
 * ломает. С API проверки станут структурными, а закрепление уйдёт.
 */
const NOW = new Date('2026-09-27T07:00:00Z');

async function openPrograms(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.clock.setFixedTime(NOW);
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/programs');
  await expect(page.getByRole('heading', { name: 'Программы', level: 1 })).toBeVisible();
  await expect(page.getByText('Не успевают: 1 из 4 с прогнозом')).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Программы: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openPrograms(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/programs-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('горизонт лет: подпроекты и карточка программы на ноутбуке', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPrograms(page);

  const horizon = page.getByRole('region', { name: 'Горизонт 2026–2030' });
  await horizon.getByRole('button', { name: 'Подпроекты: 3' }).click();
  await expect(horizon.getByText('IAC-2028: площадка и логистика')).toBeVisible();
  await horizon.screenshot({ path: `${REPORT_DIR}/programs-horizon-laptop-light.png` });

  await horizon
    .getByRole('button', { name: /^Спутниковая миссия «Навоий-2»/ })
    .first()
    .click();
  const panel = page.getByRole('dialog');
  await expect(panel.getByText('Вехи по годам')).toBeVisible();
  await expect(panel.getByText(/Не успеваем: за 90 дн/)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/programs-card-laptop-light.png` });

  await panel.getByRole('button', { name: 'Перенести дату' }).click();
  await expect(page.getByRole('status')).toContainText('«что если»');
});

test('телефон: плитки, карточка и цели нажатия', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openPrograms(page);
  await expect(page.getByRole('region', { name: 'Горизонт 2026–2030' })).toHaveCount(0);

  // Все кнопки раздела — под палец: 44 px и больше (критерий приёмки).
  const buttons = page.locator('main button');
  const count = await buttons.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `кнопка ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }

  await page.getByText('Спутниковая миссия «Навоий-2»').first().click();
  const panel = page.getByRole('dialog');
  await expect(panel.getByText('Вехи по годам')).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/programs-card-phone-light.png` });
});

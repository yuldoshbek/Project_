/**
 * Календарь — экран на утверждение, вымышленные данные (`sections/calendar/demo.ts`).
 *
 * Снимки трёх устройств в двух темах; горячий день и годовой цикл на ноутбуке; список дней
 * на телефоне — без горизонтальной прокрутки и с целями нажатия не меньше 44 px, горячий
 * день за концом списка; список годовых циклов.
 *
 * Вымышленные даты считаются от сегодняшнего дня, а даты циклов — по календарю: какой день
 * горячий и что в нём, зависит от дня запуска. Раздел данных у сервера не спрашивает,
 * поэтому время страницы закреплено; с API проверки станут структурными. Сценарии ничего
 * не пишут: заведённый цикл живёт во вкладке до перезагрузки.
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

const NOW = new Date('2026-09-28T07:00:00Z');

let link: string;

test.beforeAll(() => {
  link = issueLink('assistant');
});

async function openCalendar(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.clock.setFixedTime(NOW);
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: 'Календарь', level: 1 })).toBeVisible();
  await expect(page.getByText('Горячих дней: 3')).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Календарь: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openCalendar(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/calendar-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('горячий день и годовой цикл на ноутбуке', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openCalendar(page);

  await page.getByRole('button', { name: /^Вс, 18 октября/ }).click();
  await expect(page.getByRole('region', { name: 'Октябрь 2026' })).toBeVisible();
  await expect(page.getByText(/^Горячий день: 5 сроков/)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/calendar-hot-laptop-light.png` });

  await page.getByRole('button', { name: /^Пн, 5 октября/ }).click();
  await page.getByRole('button', { name: /Сведения в Кабмин по программе космического/ }).click();
  const sheet = page.getByRole('dialog', { name: 'Годовой цикл' });
  await expect(sheet.getByText('ежеквартально, 5-го числа')).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/calendar-cycle-laptop-light.png` });
});

test('новый годовой цикл: даты до записи', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openCalendar(page);

  await page.getByRole('button', { name: 'Новый годовой цикл' }).click();
  const form = page.getByRole('dialog', { name: 'Новый годовой цикл' });
  await form.getByLabel('Название').fill('Отчёт по субплатформам');
  await form.getByText('Ежеквартально').click();
  await form.getByLabel('Число').fill('15');
  await expect(form.getByText(/15\.10\.2026 · 15\.01\.2027/)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/calendar-form-laptop-light.png` });
});

test('телефон: ближайшие дни и цели нажатия', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openCalendar(page);
  await expect(page.getByRole('region', { name: 'Ближайшие дни' })).toBeVisible();

  // Все кнопки раздела — под палец: 44 px и больше (критерий приёмки).
  const buttons = page.locator('main button');
  const count = await buttons.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `кнопка ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }

  await page.getByRole('button', { name: /^Чт, 8 октября/ }).click();
  await expect(page.getByRole('region', { name: 'Чт, 8 октября' })).toBeInViewport();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/calendar-list-phone-light.png` });

  // 18 октября — за двумя неделями списка: список дорастает до него и прокручивает.
  await page.getByRole('button', { name: /^Вс, 18 октября/ }).click();
  await expect(page.getByRole('region', { name: 'Вс, 18 октября' })).toBeInViewport();
});

test('список годовых циклов на телефоне', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openCalendar(page);

  await page.getByRole('button', { name: 'Список циклов' }).click();
  const list = page.getByRole('dialog', { name: 'Годовые циклы' });
  await expect(list.getByText('ближайшая — 15.11.2027', { exact: false })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/calendar-cycles-phone-light.png` });
});

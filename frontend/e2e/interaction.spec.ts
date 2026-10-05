/**
 * Взаимодействие (`sections/interaction/`) — экран, утверждённый 01.10.2026, на настоящем API
 * (`/api/v1/interaction…`) и вымышленных данных базы (`backend/app/demo_interaction.py`).
 *
 * Что проверяется запуском:
 *
 * 1. четыре вопроса на трёх устройствах в двух темах, без горизонтальной прокрутки;
 * 2. телефон руководителя: список писем вместо таблицы, карточка письма и оценка ответа в
 *    одно касание, цели нажатия не меньше 44 px;
 * 3. ноутбук: таблица писем, организации со скоростью ответа, карточка организации;
 * 4. соглашения со «спящими».
 *
 * Снимки — в папку отчёта блока 2. Оценка ответа пишется в базу, поэтому сценарий проверяет
 * переключение, а не заранее известное состояние: повторный прогон не должен падать.
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

let leader: string;
let assistant: string;

test.beforeAll(() => {
  leader = issueLink('leader');
  assistant = issueLink('assistant');
});

async function open(
  page: Page,
  link: string,
  view: 'questions' | 'letters' | 'organizations' | 'agreements' = 'questions',
  theme: (typeof THEMES)[number] = 'light',
) {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto(view === 'questions' ? '/interaction' : `/interaction?view=${view}`);
  await expect(page.getByRole('heading', { name: 'Взаимодействие', level: 1 })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

async function touchTargets(page: Page, scope: string) {
  const targets = page.locator(scope).locator('button:visible, input:visible, select:visible');
  const count = await targets.count();
  for (let index = 0; index < count; index += 1) {
    const box = await targets.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `цель ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Взаимодействие: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await open(page, leader, 'questions', theme);
      await expect(page.getByRole('heading', { name: 'Кто нам не отвечает?' })).toBeVisible();
      await page.screenshot({
        path: `${REPORT_DIR}/interaction-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);
    });
  }
}

test('четыре вопроса, у каждого дата данных', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, leader);
  const panel = page.getByRole('tabpanel');
  await expect(panel.getByRole('heading', { level: 2 })).toHaveCount(4);
  await expect(panel.getByText(/^данные на /)).toHaveCount(4);
});

test('телефон руководителя: письма списком, карточка и оценка ответа', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, leader, 'letters');
  await expect(page.getByRole('table')).toHaveCount(0);
  await touchTargets(page, '[role="tabpanel"]');
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/interaction-letters-phone-light.png`,
    animations: 'disabled',
  });

  await page.getByRole('button', { name: /О совместной рабочей группе по мониторингу/ }).click();
  const card = page.getByRole('dialog', { name: 'Карточка письма' });
  await expect(card.getByRole('heading', { name: 'Как ответили?' })).toBeVisible();
  const substance = card.getByRole('button', { name: 'по существу' });
  const before = await substance.getAttribute('aria-pressed');
  await substance.click();
  await expect(substance).toHaveAttribute('aria-pressed', before === 'true' ? 'false' : 'true');
  await touchTargets(page, '[role="dialog"]');
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/interaction-letter-phone-light.png`,
    animations: 'disabled',
  });
});

test('ноутбук: письма таблицей, организации и карточка организации', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, assistant, 'letters');
  await expect(page.getByRole('table')).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/interaction-letters-laptop-light.png`,
    animations: 'disabled',
  });

  await page.getByRole('tab', { name: 'Организации' }).click();
  await expect(page.getByText(/отвечают за 25 дн/)).toBeVisible();
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/interaction-organizations-laptop-light.png`,
    animations: 'disabled',
  });

  await page.getByRole('button', { name: /^Министерство экологии/ }).click();
  const card = page.getByRole('dialog', { name: 'Карточка организации' });
  await expect(card.getByText('медиана 10 дн по 6 письмам')).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/interaction-organization-laptop-light.png`,
    animations: 'disabled',
  });
});

test('соглашения: спящие и следующий шаг', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, assistant);
  await page.getByRole('button', { name: 'Назначить следующий шаг' }).click();
  await expect(page.getByText('Спит', { exact: true })).toHaveCount(2);
  await page.screenshot({
    path: `${REPORT_DIR}/interaction-agreements-laptop-light.png`,
    animations: 'disabled',
  });
});

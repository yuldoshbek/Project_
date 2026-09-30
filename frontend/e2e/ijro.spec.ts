/**
 * Ижро (`sections/ijro/`) — экран на утверждение, на вымышленных данных (`demo.ts`).
 *
 * Что проверяется запуском:
 *
 * 1. двенадцать вопросов на трёх устройствах в двух темах, без горизонтальной прокрутки;
 * 2. телефон руководителя: список вместо таблицы, карточка поручения, цели нажатия не
 *    меньше 44 px, контрольная отметка в одно касание (критерий 3 блока 2);
 * 3. стена документов на ноутбуке;
 * 4. помощник: предпросмотр таблицы и её применение.
 *
 * Снимки — в папку отчёта блока 2. База не меняется: раздел пока живёт в памяти вкладки.
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
  view: 'questions' | 'assignments' | 'documents' | 'upload' = 'questions',
  theme: (typeof THEMES)[number] = 'light',
) {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto(view === 'questions' ? '/ijro' : `/ijro?view=${view}`);
  await expect(page.getByRole('heading', { name: 'Ижро', level: 1 })).toBeVisible();
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
    test(`Ижро: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await open(page, leader, 'questions', theme);
      await expect(
        page.getByRole('heading', { name: 'Что горит и что просрочено?' }),
      ).toBeVisible();
      await page.screenshot({
        path: `${REPORT_DIR}/ijro-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);
    });
  }
}

test('двенадцать вопросов, у каждого дата таблицы', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, leader);
  const panel = page.getByRole('tabpanel');
  await expect(panel.getByRole('heading', { level: 2 })).toHaveCount(12);
  await expect(panel.getByText(/^по таблице от \d{2}\.\d{2}\.\d{4}$/)).toHaveCount(12);
  await expect(page.getByRole('tab', { name: 'Загрузка' })).toHaveCount(0);
});

test('телефон руководителя: список, карточка, цели нажатия', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, leader, 'assignments');
  await expect(page.getByRole('table')).toHaveCount(0);
  await touchTargets(page, '[role="tabpanel"]');
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-list-phone-light.png`,
    animations: 'disabled',
  });

  await page.getByRole('tabpanel').getByRole('listitem').first().getByRole('button').click();
  const card = page.getByRole('dialog', { name: 'Карточка поручения' });
  await expect(card.getByRole('heading', { name: 'Содержание' })).toBeVisible();
  await touchTargets(page, '[role="dialog"]');
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-card-phone-light.png`,
    animations: 'disabled',
  });
});

test('телефон руководителя: контрольная отметка в одно касание', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, leader);
  await page.getByRole('button', { name: 'Контрольная отметка' }).click();

  const rows = page.getByRole('tabpanel').getByRole('listitem');
  const before = await rows.count();
  expect(before).toBeGreaterThan(0);
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-mark-phone-light.png`,
    animations: 'disabled',
  });

  await rows.first().getByRole('button', { name: 'Связался' }).click();
  await expect(rows).toHaveCount(before - 1);
});

test('ноутбук: реестр таблицей и стена документов', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, leader, 'assignments');
  await expect(page.getByRole('table')).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-table-laptop-light.png`,
    animations: 'disabled',
  });

  await page.getByRole('tab', { name: 'Документы' }).click();
  await expect(page.getByText(/^сдано \d+ из \d+$/)).toHaveCount(4);
  await noOverflow(page);
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-documents-laptop-light.png`,
    animations: 'disabled',
  });
});

test('помощник: предпросмотр таблицы, применение и повтор', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, assistant, 'upload');
  await page.getByRole('button', { name: 'Показать на образце' }).click();
  await expect(page.getByText('срок сдвинут: 3')).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-upload-laptop-light.png`,
    animations: 'disabled',
    fullPage: true,
  });

  await page.getByRole('checkbox', { name: 'Подтверждаю перенос' }).first().check();
  await page.getByRole('button', { name: 'Применить' }).click();
  await expect(page.getByRole('status')).toContainText('продлений записано 1');
  await expect(page.getByText(/Эта таблица уже применена/)).toBeVisible();
});

test('справка по проблемным поручениям открывается и печатается', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, leader);
  await page.getByRole('button', { name: 'Собрать справку' }).click();
  await expect(
    page.getByRole('heading', { name: 'Справка по проблемным поручениям' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Печать' })).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/ijro-spravka-laptop-light.png`,
    animations: 'disabled',
  });
});

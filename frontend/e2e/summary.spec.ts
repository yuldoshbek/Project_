/**
 * Утренняя сводка — вкладка Пульта на утверждение, на живой системе.
 *
 * Что проверяется запуском:
 *
 * 1. касание уведомления ведёт на вкладку (`/?view=summary`), и в ней те же строки, что на
 *    Пульте: «ждут решения» — ступень лестницы, «срок сегодня» — горящее с нулём дней;
 * 2. на iPhone в Safari — сначала «на экран «Домой»» (ТЗ 8), кнопки «включить» там нет;
 * 3. на телефоне цели нажатия не меньше 44 px и горизонтальной прокрутки нет;
 * 4. пока нет API, экран сам говорит, что доставка вымышлена, и после касания «включить» не
 *    обещает, что сводка придёт.
 *
 * Снимки трёх устройств в двух темах — в папку отчёта блока. Нужны вымышленные данные
 * (`make demo`).
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

const MIN_TOUCH_TARGET = 44;

let leader: string;
let assistant: string;

test.beforeAll(() => {
  leader = issueLink('leader');
  assistant = issueLink('assistant');
});

async function openSummary(page: Page, link: string, theme: (typeof THEMES)[number] = 'light') {
  // Безголовый Chromium отвечает «запрещено» на любые уведомления, даже с выданным
  // разрешением, и карточка устройства показывала бы «запрещены в настройках». Обычный
  // браузер, где их ещё не спрашивали, отвечает «default».
  await page.addInitScript(() => {
    if ('Notification' in window) {
      Object.defineProperty(Notification, 'permission', { get: () => 'default' });
    }
  });
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/?view=summary');
  await expect(page.getByRole('heading', { name: 'Утренняя сводка' })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Сводка: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openSummary(page, leader, theme);
      await page.screenshot({
        path: `${REPORT_DIR}/summary-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);
    });
  }
}

test('вкладка — те же строки, что на Пульте', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSummary(page, leader);
  await expect(page.getByRole('tab', { name: 'Сводка' })).toHaveAttribute('aria-selected', 'true');

  const awaiting = page.locator('section', {
    has: page.getByRole('heading', { name: 'Ждут решения' }),
  });
  const titles = await awaiting
    .locator('li button[aria-expanded] > span:nth-child(2)')
    .allTextContents();

  await page.getByRole('tab', { name: 'Сейчас' }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole('button', { name: 'Показать только: Ждёт решения' }).click();
  const ladder = await page
    .locator('main ol > li button[aria-expanded] > span:nth-child(2)')
    .allTextContents();
  expect(titles.length, 'в демо нет строк «ждёт решения»').toBeGreaterThan(0);
  expect(titles).toEqual(ladder);
});

test('помощник: дойдёт ли до руководителя и где меняется время', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSummary(page, assistant);
  await expect(page.getByRole('heading', { name: 'Кому приходит' })).toBeVisible();
  await expect(page.getByText(/порог «Утренняя сводка»/)).toBeVisible();
  await expect(page.getByText(/^(Пришла|Ещё не время)$/)).toBeVisible();
  await expect(page.getByText(/Доставка и устройство руководителя пока вымышлены/)).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/summary-assistant-laptop-light.png`,
    animations: 'disabled',
  });
});

test('iPhone в Safari: сначала на экран «Домой», потом уведомления', async ({ browser }) => {
  const context = await browser.newContext({
    userAgent: IPHONE,
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  const page = await context.newPage();
  await openSummary(page, leader);

  const device = page.locator('section', {
    has: page.getByRole('heading', { name: 'Уведомления на этом устройстве' }),
  });
  await expect(device.getByText('На экран «Домой»', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Включить уведомления' })).toHaveCount(0);
  await device.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${REPORT_DIR}/summary-install-phone-light.png`,
    animations: 'disabled',
  });

  for (const target of await page.locator('main').locator('button:visible, a:visible').all()) {
    const box = await target.boundingBox();
    if (box) expect(box.height).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }
  await noOverflow(page);
  await context.close();
});

test('ноутбук руководителя: касание «включить» в демо не обещает сводку', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSummary(page, leader);
  // Руководителю «дойдёт ли» отвечает карточка его устройства, а не «пришла на iPhone».
  await expect(page.getByText(/^(Пришла|Ещё не время)$/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Включить уведомления' }).click();
  await expect(page.getByText('Включены', { exact: true })).toBeVisible();
  await expect(page.getByText(/в демо: касание ничего не подписало/)).toBeVisible();
  await expect(page.getByText(/сводка придёт в/)).toHaveCount(0);
});

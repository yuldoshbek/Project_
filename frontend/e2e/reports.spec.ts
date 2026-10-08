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

  // У чекбокса и выбора файла цель — подпись вокруг: сам ввод скрыт или мал, нажимается
  // вместе с текстом.
  const targets = card.locator(
    'button:visible, input:not([type="checkbox"]):not([type="file"]):visible, select:visible, label:has(input[type="checkbox"]), label:has(input[type="file"])',
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

test('версия презентации: загрузка, просмотр, замечание на слайд', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, assistant);
  await page.getByRole('button', { name: 'Открыть подготовку' }).click();
  const card = page.getByRole('dialog', { name: 'Карточка подготовки' });
  const versions = card.getByRole('heading', { name: 'Версии презентации' });
  await expect(versions).toBeVisible();

  const before = await card.getByText(/^Версия \d+$/).count();
  await card.getByLabel('Загрузить версию').setInputFiles({
    name: 'Доклад о засухе.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4\n% вымышленная презентация\n'),
  });
  const number = before + 1;
  await expect(card.getByText(`Версия ${number}`, { exact: true })).toBeVisible();

  // Просмотр — короткоживущей ссылкой в новой вкладке, PDF показывает сам браузер.
  // Безголовый Chromium вместо просмотра скачивает PDF, поэтому проверяется сама ссылка.
  const [link] = await Promise.all([
    page.waitForResponse((response) => /\/api\/v1\/files\/[^/]+\/link$/.test(response.url())),
    card.getByRole('button', { name: 'Открыть' }).first().click(),
  ]);
  const { url } = (await link.json()) as { url: string };
  const file = await page.request.get(url);
  expect(file.status()).toBe(200);
  expect(file.headers()['content-type']).toBe('application/pdf');
  expect(file.headers()['content-disposition']).toMatch(/^inline/);
  for (const other of context.pages()) if (other !== page) await other.close();

  await open(page, leader);
  await page.getByRole('button', { name: 'Открыть подготовку' }).click();
  await expect(card.getByText(`Версия ${number}`, { exact: true })).toBeVisible();
  await card.getByRole('spinbutton', { name: 'Слайд' }).fill('4');
  await card.getByRole('textbox', { name: 'Замечание' }).fill('Подпись к карте мелкая');
  await card.getByRole('button', { name: 'Добавить' }).click();
  await expect(card.getByText('Подпись к карте мелкая').first()).toBeVisible();
  await card.getByRole('button', { name: 'на доработке' }).first().click();
  await expect(card.getByRole('button', { name: 'на доработке', pressed: true })).toHaveCount(1);
  await noOverflow(page);
  await versions.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${REPORT_DIR}/reports-versions-phone-light.png`,
    animations: 'disabled',
  });
});

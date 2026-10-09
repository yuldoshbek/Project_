/**
 * Блок 4 «Доработка» на живой системе — критерии приёмки из PLAN, запуском, а не на глаз.
 *
 * 1. «Что сорвётся за 14 дней?» отвечает числом и списком, решение — в одно касание;
 * 2. на телефоне название строки лестницы целиком, число изменений — без прокрутки;
 * 3. поиск находит поручение по латинице и проект по слову и открывает карточку;
 * 4. фото из Захвата прикладывается к записи и открывается из её карточки;
 * 5. монитор во всю ширину, касание дня в полосе открывает его в Календаре;
 * 6. без изменений экран спрашивает только метку; без сети — последняя картина.
 *
 * Снимки — в папку отчёта блока (`REPORT_DIR`).
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

let leader: string;
let assistant: string;

test.beforeAll(() => {
  leader = issueLink('leader');
  assistant = issueLink('assistant');
});

/** Карточка по её вопросу-заголовку: `<section>` без имени — не область для поиска по роли. */
function card(page: Page, title: string) {
  return page.locator('section').filter({ has: page.getByRole('heading', { name: title }) });
}

async function enter(page: Page, link: string, theme: 'light' | 'dim' = 'light'): Promise<void> {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Пульт', level: 1 })).toBeVisible();
  await expect(page.locator('main ol > li').first()).toBeVisible();
}

test('Пульт на телефоне: число изменений в шапке, горизонт 14 дней и решение в одно касание', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page, leader);

  // Название строки — до двух строк, а не обрезано в одну.
  const title = page.locator('main ol > li').first().locator('button span.line-clamp-2');
  await expect(title).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/pult-phone-light.png` });

  const soon = card(page, 'Что сорвётся за 14 дней?');
  await soon.scrollIntoViewIfNeeded();
  await expect(soon.getByText(/ближайший/)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/pult-soon-phone-light.png` });

  await soon
    .getByRole('button', { name: /^(Поторопить|Эскалировать|Утвердить)$/ })
    .first()
    .click();
  await expect(page.getByRole('button', { name: 'Отменить' })).toBeVisible();
  await page.getByRole('button', { name: 'Отменить' }).click();
});

test('поиск с телефона: «kosmik» находит поручение на кириллице и открывает карточку', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page, leader);

  await page.getByRole('navigation').getByRole('button', { name: 'Поиск' }).click();
  const sheet = page.getByRole('dialog', { name: 'Поиск по всем разделам' });
  await sheet.getByRole('searchbox', { name: 'Что найти' }).fill('kosmik');
  const ijro = sheet.getByRole('region', { name: 'Поручения Ижро' });
  await expect(ijro.getByRole('button').first()).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/search-phone-light.png` });

  await ijro.getByRole('button').first().click();
  await expect(page).toHaveURL(/\/ijro\?view=assignments&open=/);
  await expect(page.getByText('Содержание')).toBeVisible();
});

test('поиск на ноутбуке: клавиша «/», проект по слову, «Ввод» открывает карточку', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await enter(page, leader);

  await page.keyboard.press('/');
  const field = page.getByRole('searchbox', { name: 'Что найти' });
  await field.fill('геопортал');
  await expect(page.getByRole('region', { name: 'Проекты' })).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/search-laptop-light.png` });
  await field.press('Enter');
  await expect(page).toHaveURL(/\/(projects|programs|tasks|ijro|interaction|ideas|reports)\?/);
});

test('фото из Захвата ложится к задаче и открывается из её карточки', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await enter(page, assistant);

  await page.getByRole('button', { name: /^Захват/ }).click();
  const sheet = page.getByRole('dialog', { name: 'Захват' });
  const text = `Снимок доски ${Date.now()}`;
  await sheet.getByRole('textbox', { name: 'Текст записи' }).fill(text);
  // Маленький PNG: ровно то, что отдаёт поле файла после выбора снимка.
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    'base64',
  );
  await sheet
    .locator('input[type="file"]')
    .setInputFiles({ name: 'доска.png', mimeType: 'image/png', buffer: png });
  await expect(sheet.getByRole('img', { name: 'Выбранное фото' })).toBeVisible();
  await sheet.getByRole('button', { name: 'Записать' }).click();
  await expect(sheet.getByText(/Фото приложено/)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/capture-photo-laptop-light.png` });
  await page.keyboard.press('Escape');

  await page.keyboard.press('/');
  await page.getByRole('searchbox', { name: 'Что найти' }).fill(text);
  await page.getByRole('region', { name: 'Задачи' }).getByRole('button').first().click();
  await expect(page.getByRole('link', { name: 'Открыть фото «доска.png»' })).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/task-photo-laptop-light.png` });
});

for (const theme of ['light', 'dim'] as const) {
  test(`монитор во всю ширину, тема ${theme}: касание дня в полосе открывает Календарь`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    await enter(page, leader, theme);

    const width = await page.evaluate(
      () => document.querySelector('main > div')?.getBoundingClientRect().width ?? 0,
    );
    expect(width, 'обзор не во всю ширину').toBeGreaterThan(2000);
    const strip = card(page, 'Где неделя перегружена?').locator('ul button:not([disabled])');
    await expect(strip.first()).toBeVisible();
    await page.screenshot({ path: `${REPORT_DIR}/monitor-pult-${theme}.png` });

    if (theme === 'light') {
      await strip.first().click();
      await expect(page).toHaveURL(/\/calendar\?day=\d{4}-\d{2}-\d{2}/);
    }
  });
}

test('без изменений экран спрашивает только метку, а не Пульт', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await enter(page, leader);
  // Первый ответ Пульта уже пришёл; дальше считаем запросы за один круг опроса.
  const pult: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/pult') pult.push(request.url());
  });
  await page.waitForRequest((request) => new URL(request.url()).pathname === '/api/v1/changes', {
    timeout: 20_000,
  });
  // Ответ метки пришёл и обработан — Пульт не перечитан: правок не было.
  await page.waitForTimeout(1_000);
  expect(pult).toEqual([]);
});

test('без сети Пульт открывается последней картиной с пометкой «нет связи»', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page, leader);
  // Оболочку без сети отдаёт service worker — ждём, пока он возьмёт страницу.
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await expect(page.locator('main ol > li').first()).toBeVisible();

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('нет связи')).toBeVisible();
  await expect(page.locator('main ol > li').first()).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/offline-phone-light.png` });
  await context.setOffline(false);
});

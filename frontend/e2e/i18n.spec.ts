/**
 * Язык интерфейса — на настоящем API (`PUT /api/me/locale`).
 *
 * Интерфейс полностью переключается на узбекскую латиницу и кириллицу (критерий 3 блока 3):
 * выбор в меню шапки, язык хранится у пользователя — после перезагрузки тот же. В конце
 * язык возвращается русским: он записан на сервере, и соседние сценарии ждут русский.
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

let leader: string;

test.beforeAll(() => {
  leader = issueLink('leader');
});

/**
 * Выбрать язык и дождаться, пока он записан у пользователя. Интерфейс переключается сразу,
 * а сохранение уходит вдогонку: переход по адресу до ответа обрывал его, и страница
 * открывалась на прежнем языке — так прогон 05.10 упал на «Ғоялар ва хариталар», показав
 * раздел латиницей.
 */
async function choose(page: Page, label: string) {
  await page.getByRole('button', { name: /^(Тема|Mavzu|Мавзу):/ }).click();
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/me/locale') && response.request().method() === 'PUT',
  );
  await page.getByRole('menuitemradio', { name: label }).click();
  expect((await saved).ok(), 'язык сохранён на сервере').toBe(true);
}

/** Названия статусов проекта в наполнении (`app.seed`) — по-русски. */
const RUSSIAN_STATUSES = /^(В работе|На паузе|Завершён|Отменён)$/;

test.afterEach(async ({ page }) => {
  await page.request.put('/api/me/locale', { data: { locale: 'ru' } });
});

test('латиница и кириллица: меню, сохранение, разделы', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(leader);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Пульт', level: 1 })).toBeVisible();

  await choose(page, 'Oʻzbekcha');
  await expect(page.getByRole('link', { name: 'Loyihalar' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Nima eʼtibor talab qiladi' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'uz-Latn');
  await page.screenshot({
    path: `${REPORT_DIR}/i18n-pult-laptop-latn.png`,
    animations: 'disabled',
  });

  // Язык записан у пользователя: после перезагрузки — тот же.
  await page.reload();
  await expect(page.getByRole('link', { name: 'Loyihalar' })).toBeVisible();

  await choose(page, 'Ўзбекча');
  await expect(page.getByRole('link', { name: 'Лойиҳалар' })).toBeVisible();
  await page.goto('/ideas');
  await expect(page.getByRole('heading', { name: 'Ғоялар ва хариталар', level: 1 })).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/i18n-ideas-laptop-cyrl.png`,
    animations: 'disabled',
  });

  // Ни одного пропущенного ключа на экране: пропуск виден как ⟨ключ⟩.
  await expect(page.getByText(/⟨[\w.]+⟩/)).toHaveCount(0);

  // Статусы приходят из справочника, а не из словаря: полнота словарей их не видит, и
  // доска оставалась русской. Пропущенный узбекский ключ тоже показал бы русскую строку,
  // а не ⟨ключ⟩, поэтому ищется сам русский текст.
  await page.goto('/projects');
  await expect(page.getByRole('heading', { name: 'Лойиҳалар', level: 1 })).toBeVisible();
  const main = page.getByRole('main');
  await expect(main.getByRole('heading', { name: 'Ишда', level: 2 })).toBeVisible();
  await expect(main.getByText(RUSSIAN_STATUSES)).toHaveCount(0);
  await expect(page.getByText(/⟨[\w.]+⟩/)).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: 'Тақвим', level: 1 })).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/i18n-calendar-phone-cyrl.png`,
    animations: 'disabled',
  });
  await expect(page.getByText(/⟨[\w.]+⟩/)).toHaveCount(0);

  await choose(page, 'Русский');
  await expect(page.getByRole('heading', { name: 'Календарь', level: 1 })).toBeVisible();
});

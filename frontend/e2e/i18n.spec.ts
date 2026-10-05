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

async function choose(page: Page, label: string) {
  await page.getByRole('button', { name: /^(Тема|Mavzu|Мавзу):/ }).click();
  await page.getByRole('menuitemradio', { name: label }).click();
}

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

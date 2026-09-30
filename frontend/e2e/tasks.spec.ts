/**
 * Задачи на живой системе — через настоящий API и базу (`python -m app.demo`).
 *
 * Снимки трёх устройств в двух темах, таблица на ноутбуке, строка с разбором на сервере
 * (пример из ТЗ 7), «Кто перегружен?» как фильтр, карточка с чек-листом.
 *
 * Сценарии, которые пишут, возвращают картину: заведённая задача отменяется (удаления у
 * деловых записей нет — журнал помнит всё), отмеченный пункт чек-листа снимается.
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;

let link: string;

test.beforeAll(() => {
  link = issueLink('assistant');
});

async function openTasks(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: 'Задачи', level: 1 })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Просрочено' })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Задачи: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openTasks(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/tasks-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('строка с разбором: пример из ТЗ 7', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openTasks(page);

  const line = page.getByLabel('Новая задача строкой');
  await line.fill('к пятнице рассмотрение проекта постановления Минэкологии, Каримов');
  await expect(
    page.getByText('Понято: Рассмотрение проекта постановления Минэкологии'),
  ).toBeVisible();
  const form = page.locator('form').filter({ has: line });
  await expect(form.getByRole('combobox').first()).toHaveValue('review_and_endorse');
  // Идентификаторы людей в базе — свои; проверяем то, что видит человек: имя.
  await expect(form.getByRole('combobox').nth(1).locator('option:checked')).toHaveText(
    'Каримов А.',
  );
  await page.screenshot({ path: `${REPORT_DIR}/tasks-capture-laptop-light.png` });

  await form.getByRole('button', { name: 'Добавить' }).click();
  await expect(page.getByText(/Задача заведена: TSK-/)).toBeVisible();
  const created = page
    .getByRole('button', { name: /Рассмотрение проекта постановления Минэкологии/ })
    .first();
  await expect(created).toBeVisible();

  // Вернуть картину: отменённая задача уходит в свёрнутые «готовые и отменённые».
  await created.click();
  const panel = page.getByRole('dialog');
  await panel.getByRole('button', { name: 'Отменена' }).click();
  await expect(panel.getByText('Отменена').first()).toBeVisible();
  await page.keyboard.press('Escape');
});

test('таблица и «Кто перегружен?» на ноутбуке', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openTasks(page);

  await page.getByRole('button', { name: 'Показать задачи: Рахимов Ш.' }).click();
  await expect(page.getByText('Показаны задачи: Рахимов Ш.')).toBeVisible();
  await page.getByRole('tab', { name: 'Таблица' }).click();
  await expect(page.getByRole('columnheader', { name: 'Чек-лист' })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/tasks-table-laptop-light.png` });
});

test('карточка задачи на телефоне: чек-лист касанием', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openTasks(page);

  await page.getByText('Выезд на полигон в Джизаке').first().click();
  const panel = page.getByRole('dialog');
  const item = panel.getByRole('checkbox', { name: 'Приборы калибровки' });
  // Флажок меняется ответом сервера, а не щелчком: ждём его, а не мгновенной смены.
  // Отмеченный прошлым прерванным прогоном пункт — не повод отмечать его снова.
  if (!(await item.isChecked())) await item.click();
  await expect(item).toBeChecked();
  await expect(panel.getByText('чек-лист 2/3')).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/tasks-card-phone-light.png` });

  // Вернуть как было.
  await item.click();
  await expect(item).not.toBeChecked();
  await expect(panel.getByText('чек-лист 1/3')).toBeVisible();
});

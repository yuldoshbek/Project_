/**
 * Проекты на живой системе — через настоящий API и базу.
 *
 * Снимки трёх устройств в двух темах, таблица и таймлайн на ноутбуке, карточка проекта с
 * расчётом «что если», перенос плитки на паузу с причиной. Нужны вымышленные данные
 * (`python -m app.demo`): на пустой базе разделу нечего показать.
 *
 * Сценарии, которые пишут в базу, возвращают её как было: перенос на паузу снимается
 * кнопкой «В работе» в карточке. Иначе второй прогон начинался бы с другой картины, и
 * снимки отчёта расходились бы от прогона к прогону.
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

async function openProjects(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/projects');
  await expect(page.getByRole('heading', { name: 'Проекты', level: 1 })).toBeVisible();
}

/** День через `days` от сегодняшнего по Ташкенту — в формате поля даты. */
function inDays(days: number): string {
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tashkent' }).format(new Date());
  const moment = new Date(`${day}T00:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() + days);
  return moment.toISOString().slice(0, 10);
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Проекты: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openProjects(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/projects-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('таблица и таймлайн на ноутбуке', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openProjects(page);

  await page.getByRole('tab', { name: 'Таблица' }).click();
  await expect(page.getByRole('columnheader', { name: 'Что мешает' })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/projects-table-laptop-light.png` });

  await page.getByRole('tab', { name: 'Таймлайн' }).click();
  await expect(page.getByText('Сегодня', { exact: true })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/projects-timeline-laptop-light.png` });
});

test('«что если» считает и ничего не записывает', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openProjects(page);

  await page
    .getByRole('button', { name: /Постановление о порядке обмена/ })
    .first()
    .click();
  const panel = page.getByRole('dialog');
  await expect(panel.getByText('Что если')).toBeVisible();

  const milestone = panel.getByLabel('Внесение в Кабинет Министров');
  const before = await milestone.inputValue();
  // Через три дня — внутри порога «горит» (7 дней): расчёт обязан это показать.
  await milestone.fill(inDays(3));
  await panel.getByRole('button', { name: 'Посчитать' }).click();
  await expect(panel.getByText(/Горит: \d+ → \d+/)).toBeVisible();
  await expect(panel.getByText(/в базе ничего не изменилось/)).toBeVisible();
  await panel.getByText('Что если').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${REPORT_DIR}/projects-whatif-laptop-light.png` });

  // «Сбросить» возвращает даты: расчёт ничего не записал.
  await panel.getByRole('button', { name: 'Сбросить' }).click();
  await expect(milestone).toHaveValue(before);
});

test('перенос на паузу — только с причиной', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openProjects(page);

  // Первая плитка колонки: она на экране без прокрутки, и перетаскивание не промахнётся.
  const tile = page.getByRole('region', { name: 'В работе' }).getByRole('article').first();
  const code = (await tile.textContent())?.match(/PRJ-\d{4}-\d{3}/)?.[0];
  expect(code, 'у плитки нет номера').toBeTruthy();
  await tile.dragTo(page.getByRole('region', { name: 'На паузе' }));

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
  await dialog.getByRole('textbox').fill('Ждём снимки за август');
  await dialog.getByRole('button', { name: 'Сохранить' }).click();

  const paused = page
    .getByRole('region', { name: 'На паузе' })
    .getByRole('article')
    .filter({ hasText: code! });
  await expect(paused).toBeVisible();
  await expect(paused.getByText('Причина: Ждём снимки за август')).toBeVisible();

  // Вернуть как было — кнопкой статуса в карточке: это второй путь смены статуса.
  await paused.getByRole('button').first().click();
  const panel = page.getByRole('dialog');
  await panel.getByRole('button', { name: 'В работе' }).click();
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('region', { name: 'В работе' }).getByRole('article').filter({ hasText: code! }),
  ).toBeVisible();
});

// Карточка с организациями — экран на утверждение: правка ложится во временный слой
// вкладки (`draft.ts`), база не меняется.
for (const size of [
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'phone', width: 390, height: 844 },
] as const) {
  test(`карточка: организации и сведения, ${size.name}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openProjects(page);
    if (size.name === 'phone') await page.getByRole('tab', { name: /В работе/ }).click();

    await page
      .getByRole('button', { name: /Совместная программа наблюдения/ })
      .first()
      .click();
    const panel = page.getByRole('dialog');
    const organizations = panel.locator('section').filter({ hasText: 'Кто заказчик' });
    await expect(organizations.getByText('Министерство экологии')).toBeVisible();
    await expect(organizations.getByText(/Головное ведомство — не агентство/)).toBeVisible();

    // Центр — одним касанием.
    await organizations.getByRole('button', { name: 'исполнитель', exact: true }).click();
    await expect(
      organizations.getByRole('combobox', { name: /Роль: Центр космического мониторинга/ }),
    ).toHaveValue('executor');

    await organizations.scrollIntoViewIfNeeded();
    await noOverflow(page);
    await page.screenshot({ path: `${REPORT_DIR}/projects-card-orgs-${size.name}-light.png` });
  });
}

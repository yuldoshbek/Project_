/**
 * Захват — экран на утверждение (`sections/capture/`): входящие — вымышленные данные
 * (`demo.ts`), разбор фразы и задача — настоящий API «Задач».
 *
 * Снимки трёх устройств в двух темах с открытым Захватом и разобранной фразой; нижняя
 * панель телефона по ТЗ 6 и лист «Ещё»; цели нажатия не меньше 44 px; клавиша «+» на
 * ноутбуке. Сценарии ничего не пишут в базу: задача не заводится, идея ложится во входящие
 * вымышленного сервера и живёт до перезагрузки.
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

const PHRASE = 'к пятнице рассмотрение проекта постановления Минэкологии, Каримов';

let link: string;

test.beforeAll(() => {
  link = issueLink('assistant');
});

async function openPult(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Пульт', level: 1 })).toBeVisible();
}

async function capture(page: Page) {
  await page.getByRole('button', { name: /^Захват/ }).click();
  const sheet = page.getByRole('dialog', { name: 'Захват' });
  await expect(sheet.getByRole('textbox', { name: 'Текст записи' })).toBeFocused();
  return sheet;
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Захват: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openPult(page, theme);
      const sheet = await capture(page);
      await sheet.getByRole('textbox', { name: 'Текст записи' }).fill(PHRASE);
      // Разбор — на сервере: срок и ответственный понятны из фразы.
      await expect(sheet.getByText(/^Понято: /)).toBeVisible();
      const assignee = sheet.getByLabel('Ответственный');
      await expect(assignee).not.toHaveValue('');
      // Имя видно, а не только выбрано: в ряд из четырёх полей оно обрезалось до пустоты,
      // а «проверьте перед записью» — как раз про него. Ширина текста — счётом по шрифту поля.
      const fits = await assignee.evaluate((select: HTMLSelectElement) => {
        const context = document.createElement('canvas').getContext('2d');
        if (!context) return false;
        const style = getComputedStyle(select);
        context.font = `${style.fontSize} ${style.fontFamily}`;
        const name = select.selectedOptions[0]?.text ?? '';
        const arrow = 20;
        return context.measureText(name).width <= select.clientWidth - arrow;
      });
      expect(fits, 'имя ответственного видно целиком').toBe(true);
      await page.screenshot({ path: `${REPORT_DIR}/capture-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('телефон: нижняя панель по ТЗ 6, «Ещё» и цели нажатия', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openPult(page);

  const bar = page.locator('nav.fixed');
  await expect(bar.getByRole('link')).toHaveText(['Пульт', 'Календарь']);
  const buttons = bar.getByRole('button');
  await expect(buttons).toHaveCount(3);
  for (let index = 0; index < 3; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    expect(box?.height ?? 0, `кнопка панели ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }
  await page.screenshot({ path: `${REPORT_DIR}/capture-bar-phone-light.png` });

  await page.getByRole('button', { name: 'Ещё' }).click();
  const more = page.getByRole('dialog', { name: 'Все разделы' });
  await expect(more.getByRole('link', { name: /Задачи/ })).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/capture-more-phone-light.png` });
  await more.getByRole('link', { name: /Задачи/ }).click();
  await expect(page.getByRole('heading', { name: 'Задачи', level: 1 })).toBeVisible();
});

test('телефон: идея во входящие и цели нажатия листа', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openPult(page);
  const sheet = await capture(page);

  const buttons = sheet.locator('button, label:has(input[type="radio"])');
  const count = await buttons.count();
  for (let index = 0; index < count; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `цель ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }

  await sheet.getByRole('group', { name: 'Что это' }).getByText('Идея').click();
  await sheet
    .getByRole('textbox', { name: 'Текст записи' })
    .fill('Мониторинг пастбищ для Минсельхоза');
  await sheet.getByRole('button', { name: 'Записать' }).click();
  await expect(sheet.getByRole('status')).toHaveText('Идея во входящих.');
  await expect(sheet.getByRole('listitem').first()).toContainText('во входящих до «Идей и карт»');
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/capture-idea-phone-light.png` });
});

test('ноутбук: клавиша «+» открывает Захват с любого экрана', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPult(page);
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: 'Календарь', level: 1 })).toBeVisible();
  await page.keyboard.press('+');
  await expect(page.getByRole('dialog', { name: 'Захват' })).toBeVisible();
});

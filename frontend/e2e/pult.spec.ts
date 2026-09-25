/**
 * Пульт на живой системе — глазами руководителя.
 *
 * Три обещания экрана, утверждённого заказчиком 25.09.2026, проверяются здесь запуском, а
 * не на глаз:
 *
 * 1. **пять строк лестницы на телефоне без прокрутки** (PLAN-10X, «Пульт на iPhone»);
 * 2. **решение в одно касание и «Отменить»** — через настоящий API и базу;
 * 3. **отчёт недели печатается в читаемый PDF** (критерий 6 блока 1).
 *
 * Снимки трёх устройств в двух темах — в папку отчёта блока. Нужны вымышленные данные
 * (`make demo`): на пустой базе Пульту нечего показать, и проверка пяти строк бессмысленна.
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
  link = issueLink('leader');
});

async function openPult(page: Page, theme: (typeof THEMES)[number] = 'light'): Promise<void> {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Пульт' })).toBeVisible();
  await expect(page.locator('main ol > li').first()).toBeVisible();
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Пульт: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openPult(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/pult-${size.name}-${theme}.png` });

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
    });
  }
}

test('на телефоне пять строк лестницы видны без прокрутки', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openPult(page);

  const rows = page.locator('main ol > li');
  expect(
    await rows.count(),
    'в лестнице меньше пяти строк — нет вымышленных данных?',
  ).toBeGreaterThanOrEqual(5);

  const fifth = await rows.nth(4).boundingBox();
  const bar = await page.locator('nav.fixed').boundingBox();
  expect(fifth, 'пятая строка не отрисована').not.toBeNull();
  expect(bar, 'нижняя панель не отрисована').not.toBeNull();
  expect(fifth!.y + fifth!.height).toBeLessThanOrEqual(bar!.y);
});

test('решение в одно касание и «Отменить» — через API и базу', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPult(page);

  const awaiting = page.getByRole('button', { name: 'Показать только: Ждёт решения' });
  const before = Number(await awaiting.getByText(/^\d+$/).textContent());
  expect(before, 'нет строк «ждёт решения»').toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Утвердить' }).first().click();
  await expect(awaiting.getByText(/^\d+$/)).toHaveText(String(before - 1));

  await page.getByRole('button', { name: 'Отменить' }).click();
  await expect(awaiting.getByText(/^\d+$/)).toHaveText(String(before));
});

test('отчёт недели: снимок и PDF', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPult(page);

  await page.getByRole('tab', { name: 'Отчёт' }).click();
  await expect(page.getByRole('heading', { name: /Отчёт за неделю/ })).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/report-week-laptop-light.png`, fullPage: true });

  // PDF — так, как его сохранит браузер из «Печать»: стили печати, лист A4.
  await page.emulateMedia({ media: 'print' });
  const pdf = await page.pdf({
    path: `${REPORT_DIR}/report-week.pdf`,
    format: 'A4',
    printBackground: true,
    margin: { top: '14mm', bottom: '14mm', left: '14mm', right: '14mm' },
  });
  expect(pdf.byteLength, 'PDF пустой').toBeGreaterThan(10_000);

  // Служебное на листе не печатается: только отчёт.
  await expect(page.getByRole('button', { name: 'Печать и PDF' })).toBeHidden();
  await expect(page.getByRole('navigation').first()).toBeHidden();
});

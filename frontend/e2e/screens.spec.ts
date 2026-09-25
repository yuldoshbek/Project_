/**
 * Снимки экранов: три устройства, две темы.
 *
 * Снимки — часть отчёта блока, а не побочный продукт. Они ловят то, что не ловит ни один
 * другой тест: горизонтальную прокрутку на 390 px, нижнюю панель под жест-полосой, серый
 * текст на сером фоне в приглушённой теме.
 *
 * Здесь же проверяются два правила, которые иначе проверяются «на глаз»: **нет
 * горизонтальной прокрутки** и **цель нажатия на телефоне не меньше 44 px**.
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;

// Пульт снимается глазами руководителя в pult.spec.ts: это его экран. Здесь — то, что
// видит помощник.
const PAGES = [{ name: 'management', path: '/management' }] as const;

const MIN_TOUCH_TARGET = 44;

let link: string;

test.beforeAll(() => {
  link = issueLink();
});

async function useTheme(page: Page, theme: (typeof THEMES)[number]): Promise<void> {
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`снимки: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(link);
      await useTheme(page, theme);

      for (const target of PAGES) {
        await page.goto(target.path);
        await page.waitForLoadState('networkidle');
        await page.screenshot({
          path: `${REPORT_DIR}/${target.name}-${size.name}-${theme}.png`,
          fullPage: false,
        });

        // Горизонтальная прокрутка — верный признак, что раскладка не влезла. На телефоне
        // это выглядит как «половина экрана уехала», и замечают это обычно на приёмке.
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `горизонтальная прокрутка на ${target.path}`).toBeLessThanOrEqual(1);
      }
    });
  }
}

test('на телефоне цели нажатия не меньше 44 px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(link);

  const links = page.getByRole('navigation').getByRole('link');
  const count = await links.count();
  expect(count, 'в нижней панели нет разделов').toBeGreaterThan(0);

  for (let index = 0; index < count; index += 1) {
    const box = await links.nth(index).boundingBox();
    expect(box, 'кнопка панели не отрисована').not.toBeNull();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }
});

test('тема выбирается явно и запоминается', async ({ page }) => {
  await page.goto(link);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.dataset.theme))
    .toBe('light');

  await page.getByRole('button', { name: /Тема/ }).click();
  await page.getByRole('menuitemradio', { name: 'Приглушённая' }).click();

  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe('dim');

  // Выбор переживает перезагрузку: тему ставит встроенный скрипт до первой отрисовки,
  // иначе на приглушённой теме видна светлая вспышка.
  await page.reload();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe('dim');
});

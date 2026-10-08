/**
 * Календарь на живой системе — через настоящий API и базу (`python -m app.demo`).
 *
 * Снимки трёх устройств в двух темах; горячий день и годовой цикл на ноутбуке; форма цикла
 * с датами до записи; список дней на телефоне — без горизонтальной прокрутки и с целями
 * нажатия не меньше 44 px, горячий день за концом списка; список годовых циклов.
 *
 * Вымышленные сроки сервер считает от дня загрузки демо, а даты циклов — по календарю,
 * поэтому проверки — по устройству экрана, а не по числам дня. Горячие дни демо — сегодня,
 * через 10 и через 20 дней: последний дальше двух недель списка телефона. Сценарии ничего
 * не пишут: цикл до записи не заводится, отмена не нажимается.
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

const ANSWER = /^Горячих дней: \d+$/;
const DATE = /\d{2}\.\d{2}\.\d{4}/;

let link: string;

test.beforeAll(() => {
  link = issueLink('assistant');
});

async function openCalendar(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: 'Календарь', level: 1 })).toBeVisible();
  await expect(page.getByText(ANSWER)).toBeVisible();
}

/** Кнопки горячих дней в карточке «Где неделя перегружена?» — по порядку дней. */
function hotButtons(page: Page) {
  return page
    .getByRole('heading', { name: 'Где неделя перегружена?' })
    .locator('xpath=ancestor::section[1]')
    .getByRole('button');
}

/** «Вс, 18 октября» — день горячей строки без приписки «· сегодня». */
async function dayOf(button: ReturnType<typeof hotButtons>): Promise<string> {
  const text = (await button.locator('span span').first().textContent()) ?? '';
  return text.split(' · ')[0]!.trim();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Календарь: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openCalendar(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/calendar-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('горячий день и годовой цикл на ноутбуке', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openCalendar(page);

  // Последний горячий день окна: сетка уходит на его месяц и выбирает его.
  const last = hotButtons(page).last();
  const title = await dayOf(last);
  await last.click();
  await expect(page.getByRole('heading', { name: title, level: 2 })).toBeVisible();
  await expect(page.getByText(/^Горячий день: \d+ срок/)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/calendar-hot-laptop-light.png` });

  await page.getByRole('button', { name: 'Список циклов' }).click();
  const list = page.getByRole('dialog', { name: 'Годовые циклы' });
  await list.getByRole('button', { name: /Сведения в Кабмин/ }).click();
  const sheet = page.getByRole('dialog', { name: 'Годовой цикл' });
  await expect(sheet.getByText('ежеквартально, 5-го числа')).toBeVisible();
  await expect(sheet.getByText(DATE).first()).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/calendar-cycle-laptop-light.png` });
});

test('новый годовой цикл: даты до записи', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openCalendar(page);

  await page.getByRole('button', { name: 'Новый годовой цикл' }).click();
  const form = page.getByRole('dialog', { name: 'Новый годовой цикл' });
  await form.getByLabel('Название').fill('Отчёт по субплатформам');
  await form.getByText('Ежеквартально').click();
  await form.getByLabel('Число').fill('15');
  // Кварталы на год вперёд — даты считает сервер. Горизонт включает свой день: если
  // сегодня 15-е число квартального месяца, дат пять, а не четыре.
  const quarters = new RegExp(`^${DATE.source}( · ${DATE.source}){3,4}$`);
  await expect(form.getByText(quarters)).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/calendar-form-laptop-light.png` });
});

test('телефон: ближайшие дни и цели нажатия', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openCalendar(page);
  await expect(page.getByRole('region', { name: 'Ближайшие дни' })).toBeVisible();

  // Все кнопки раздела — под палец: 44 px и больше (критерий приёмки).
  const buttons = page.locator('main button');
  const count = await buttons.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `кнопка ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }

  const days = hotButtons(page);
  const second = await dayOf(days.nth(1));
  await days.nth(1).click();
  await expect(page.getByRole('region', { name: second })).toBeInViewport();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/calendar-list-phone-light.png` });

  // Последний горячий день — за двумя неделями списка: список дорастает и прокручивает.
  const far = await dayOf(days.last());
  await days.last().click();
  await expect(page.getByRole('region', { name: far })).toBeInViewport();
});

test('список годовых циклов на телефоне', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openCalendar(page);

  await page.getByRole('button', { name: 'Список циклов' }).click();
  const list = page.getByRole('dialog', { name: 'Годовые циклы' });
  await expect(list.getByText(/ближайшая — /).first()).toBeVisible();
  await expect(list.getByRole('button', { name: /Переаттестация операторов/ })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/calendar-cycles-phone-light.png` });
});

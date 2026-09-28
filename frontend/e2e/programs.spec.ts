/**
 * Программы на живой системе — через настоящий API и базу (`python -m app.demo`).
 *
 * Снимки трёх устройств в двух темах; горизонт лет с раскрытыми подпроектами, карточка
 * программы и переход в карточку проекта на «что если» на ноутбуке; плитки и карточка на
 * телефоне — без горизонтальной прокрутки и с целями нажатия не меньше 44 px.
 *
 * Вымышленные даты сервер считает от дня загрузки демо, поэтому проверки — по устройству
 * экрана, а не по числам дня. Одно исключение: «перенести дату» есть только у программы,
 * которая не успевает, а темп берётся за 90 дней — после загрузки демо у каталога снимков
 * хватает закрытых задач примерно на два месяца, дальше демо загружают заново. Сценарии
 * ничего не пишут: раздел только читает, «что если» здесь не считается.
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

const HORIZON = /^Горизонт \d{4}–\d{4}$/;

let link: string;

test.beforeAll(() => {
  link = issueLink('assistant');
});

async function openPrograms(page: Page, theme: (typeof THEMES)[number] = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/programs');
  await expect(page.getByRole('heading', { name: 'Программы', level: 1 })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Успеваем к дате?' })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Программы: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openPrograms(page, theme);
      await page.screenshot({ path: `${REPORT_DIR}/programs-${size.name}-${theme}.png` });
      await noOverflow(page);
    });
  }
}

test('горизонт лет: подпроекты, карточка программы и карточка проекта', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPrograms(page);

  const horizon = page.getByRole('region', { name: HORIZON });
  await horizon.getByRole('button', { name: 'Подпроекты: 3' }).click();
  await expect(horizon.getByText('Конгресс IAC: площадка и логистика')).toBeVisible();
  await horizon.screenshot({ path: `${REPORT_DIR}/programs-horizon-laptop-light.png` });

  await horizon
    .getByRole('button', { name: /^Спутниковая миссия «Навоий-2»/ })
    .first()
    .click();
  const panel = page.getByRole('dialog');
  await expect(panel.getByText('Вехи по годам')).toBeVisible();
  await expect(panel.getByText('Успеваем ли к дате программы?')).toBeVisible();
  await page.screenshot({ path: `${REPORT_DIR}/programs-card-laptop-light.png` });

  // Правят программу в карточке проекта: лист программы сменяется ею, а не ложится сверху.
  await panel.getByRole('button', { name: 'Открыть карточку проекта' }).click();
  const project = page.getByRole('dialog', { name: 'Проекты' });
  await expect(
    project.getByRole('heading', { name: 'Спутниковая миссия «Навоий-2»' }),
  ).toBeVisible();
  await expect(project.getByText('готовность — с подпроектами')).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
});

test('«перенести дату» ведёт в «что если» карточки проекта', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPrograms(page);

  await page.getByRole('button', { name: 'Перенести дату' }).first().click();
  const project = page.getByRole('dialog', { name: 'Проекты' });
  const whatIf = project.getByRole('heading', { name: 'Что если' });
  await expect(whatIf).toBeVisible();
  await expect(whatIf).toBeInViewport();
  await page.screenshot({ path: `${REPORT_DIR}/programs-move-laptop-light.png` });
});

test('телефон: плитки, карточка и цели нажатия', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openPrograms(page);
  await expect(page.getByRole('region', { name: HORIZON })).toHaveCount(0);

  // Все кнопки раздела — под палец: 44 px и больше (критерий приёмки).
  const buttons = page.locator('main button');
  const count = await buttons.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const box = await buttons.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `кнопка ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }

  await page.getByText('Спутниковая миссия «Навоий-2»').first().click();
  const panel = page.getByRole('dialog');
  await expect(panel.getByText('Вехи по годам')).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: `${REPORT_DIR}/programs-card-phone-light.png` });
});

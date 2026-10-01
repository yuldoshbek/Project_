/**
 * Управление (`sections/management/`) — экран утверждён 29.09.2026, работает на API
 * `/api/v1/management`; устройства и перевыпуск — `/api/access/…`.
 *
 * Снимок по умолчанию (обход недели) на трёх устройствах в двух темах снимает
 * `screens.spec.ts`; здесь — остальные вкладки, мини-обход на телефоне, цели нажатия не
 * меньше 44 px, отсутствие горизонтальной прокрутки и взгляд руководителя. Сценарии ничего
 * не пишут в базу: действия обхода и пороги здесь открываются и отменяются, ссылки не
 * перевыпускаются (это делает `reissue.spec.ts` со своей ссылкой).
 */

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const PHONE = { width: 390, height: 844 };
const LAPTOP = { width: 1440, height: 900 };
const MONITOR = { width: 2560, height: 1440 };

const MIN_TOUCH_TARGET = 44;

let assistant: string;
let leader: string;

test.beforeAll(() => {
  assistant = issueLink('assistant');
  leader = issueLink('leader');
});

async function open(page: Page, link: string, theme: 'light' | 'dim' = 'light') {
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/management');
  await expect(page.getByRole('heading', { name: 'Управление', level: 1 })).toBeVisible();
}

async function tab(page: Page, name: string) {
  await page.getByRole('tab', { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole('tabpanel')).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

async function touchTargets(page: Page) {
  const targets = page
    .getByRole('tabpanel')
    .locator('button:visible, input:visible, select:visible, a:visible');
  const count = await targets.count();
  for (let index = 0; index < count; index += 1) {
    const box = await targets.nth(index).boundingBox();
    if (!box) continue;
    expect(box.height, `цель ${index}`).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }
}

test('ноутбук: пороги с предпросмотром, справочники с шаблоном вех, доступ', async ({ page }) => {
  await page.setViewportSize(LAPTOP);
  await open(page, assistant);

  await tab(page, 'Пороги');
  const burn = page.getByRole('listitem').filter({ hasText: 'За сколько дней до срока' });
  await burn.getByRole('button', { name: 'Больше: Горит' }).click();
  await burn.getByRole('button', { name: 'Больше: Горит' }).click();
  await expect(burn.getByText(/→ станет \d+/)).toBeVisible();
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-thresholds-laptop-light.png`,
  });
  await noOverflow(page);

  await tab(page, 'Справочники');
  await page
    .getByRole('listitem')
    .filter({ hasText: 'Нормативный акт' })
    .getByRole('button', { name: 'Вехи шаблона' })
    .click();
  await expect(page.getByRole('heading', { name: 'Вехи шаблона: Нормативный акт' })).toBeVisible();
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-dictionaries-laptop-light.png`,
  });
  await noOverflow(page);

  await tab(page, 'Доступ');
  await expect(page.getByText(/Ссылка выпущена/).first()).toBeVisible();
  await expect(page.getByText(/Последний раз/).first()).toBeVisible();
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-access-laptop-light.png`,
  });
  await noOverflow(page);
});

test('монитор: справочники тремя колонками', async ({ page }) => {
  await page.setViewportSize(MONITOR);
  await open(page, assistant, 'dim');
  await tab(page, 'Справочники');
  await page
    .getByRole('listitem')
    .filter({ hasText: 'Спутниковая миссия' })
    .getByRole('button', { name: 'Вехи шаблона' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Вехи шаблона: Спутниковая миссия' }),
  ).toBeVisible();
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-dictionaries-monitor-dim.png`,
  });
  await noOverflow(page);
});

test('телефон: мини-обход в одно касание, вкладки, цели нажатия', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await open(page, assistant);

  await touchTargets(page);
  // Действие со строкой открывается прямо в пункте; записывать его здесь нельзя — база
  // разработки общая, и закрытое решение из демо назад не откроется. Открыли и отменили.
  const note = page.getByRole('button', { name: 'Записать, что мешает' }).first();
  await note.click();
  await expect(page.getByLabel('Что мешает')).toBeFocused();
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-round-phone-light.png`,
  });
  await noOverflow(page);
  await page.getByRole('button', { name: 'Отмена' }).click();

  await tab(page, 'Пороги');
  await touchTargets(page);
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-thresholds-phone-light.png`,
  });
  await noOverflow(page);

  await tab(page, 'Справочники');
  await page.getByRole('button', { name: /^Типы задач/ }).click();
  await expect(page.getByRole('heading', { name: 'Типы задач' })).toBeVisible();
  await touchTargets(page);
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-dictionaries-phone-light.png`,
  });
  await noOverflow(page);

  await tab(page, 'Доступ');
  await touchTargets(page);
  await noOverflow(page);
});

test('руководитель: пороги и справочники без правки', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await open(page, leader);
  await expect(page.getByRole('tab')).toHaveText(['Пороги', 'Справочники']);
  await expect(page.getByText(/Управление ведёт помощник/)).toBeVisible();
  await expect(page.getByRole('button', { name: /^Больше:/ })).toHaveCount(0);
  await page.screenshot({
    animations: 'disabled',
    path: `${REPORT_DIR}/management-leader-phone-light.png`,
  });
  await noOverflow(page);
});

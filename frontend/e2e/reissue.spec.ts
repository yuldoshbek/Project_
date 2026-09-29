/**
 * Перевыпуск ссылки закрывает доступ прежним устройствам.
 *
 * Отдельным файлом нарочно: сценарий гасит сессии, и соседние проверки, работающие по той
 * же ссылке, падали бы не по своей вине. У файла своя ссылка — гасит он только её.
 *
 * Проверяется ровно то, ради чего кнопка существует: тот, кому ссылку переслали, теряет
 * доступ в тот же момент, а не «после истечения срока». И что тот, кто перевыпустил свою
 * ссылку, не остаётся за дверью: новая ссылка — на экране, и она открывает систему.
 */

import { expect, test } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const PHONE = { width: 390, height: 844 };
const LAPTOP = { width: 1440, height: 900 };

test('перевыпуск гасит прежнюю сессию сразу', async ({ browser }) => {
  const link = issueLink();

  const before = await browser.newContext();
  const beforePage = await before.newPage();
  await beforePage.goto(link);
  await expect(beforePage.getByRole('heading', { name: 'Пульт' })).toBeVisible();

  const manager = await browser.newContext();
  const managerPage = await manager.newPage();
  await managerPage.goto(link);
  await managerPage.goto('/management');
  await managerPage.getByRole('tab', { name: 'Доступ' }).click();
  await managerPage.getByRole('button', { name: 'Перевыпустить ссылку' }).first().click();
  // Перевыпуск переспрашивает: случайное касание выкинуло бы из системы и того, кто нажал.
  await managerPage.getByRole('button', { name: 'Перевыпустить', exact: true }).click();
  // Своя ссылка погасила и сессию того, кто нажал: новую показывает экран «откройте по
  // ссылке» — иначе помощник остался бы вне системы.
  await expect(
    managerPage.getByRole('heading', { name: 'Ваша ссылка перевыпущена' }),
  ).toBeVisible();
  await expect(
    managerPage.getByText('Ссылка показывается один раз', { exact: false }),
  ).toBeVisible();
  const open = managerPage.getByRole('link', { name: 'Открыть по новой ссылке' });
  const fresh = await open.getAttribute('href');
  expect(fresh).toMatch(/\/api\/access\//);
  expect(fresh).not.toBe(link);

  for (const [device, size] of [
    ['phone', PHONE],
    ['laptop', LAPTOP],
  ] as const) {
    await managerPage.setViewportSize(size);
    for (const theme of ['light', 'dim'] as const) {
      await managerPage.evaluate((value) => {
        document.documentElement.setAttribute('data-theme', value);
      }, theme);
      // Ссылка на снимке закрыта: снимки лежат в публичном репозитории.
      await managerPage.screenshot({
        path: `${REPORT_DIR}/access-reissued-${device}-${theme}.png`,
        mask: [managerPage.locator('code')],
        // Тема меняется на лету: без этого снимок ловит кнопки посреди перехода цвета.
        animations: 'disabled',
      });
    }
    const overflow = await managerPage.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `горизонтальная прокрутка: ${device}`).toBeLessThanOrEqual(1);
    if (device === 'phone') {
      for (const target of await managerPage.locator('a:visible, button:visible').all()) {
        expect((await target.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      }
    }
  }

  // Ссылка не одноразовая: открывается и здесь, и на другом устройстве.
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto(fresh!);
  await expect(otherPage.getByRole('heading', { name: 'Пульт' })).toBeVisible();
  await open.click();
  await expect(managerPage.getByRole('heading', { name: 'Пульт' })).toBeVisible();
  await other.close();

  // Страница, открытая по прежней ссылке, теряет доступ на следующем же запросе.
  await beforePage.reload();
  await expect(beforePage.getByText('Откройте ORBITA по своей личной ссылке')).toBeVisible();

  await before.close();
  await manager.close();
});

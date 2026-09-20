/**
 * Перевыпуск ссылки закрывает доступ прежним устройствам.
 *
 * Отдельным файлом нарочно: сценарий гасит сессии, и соседние проверки, работающие по той
 * же ссылке, падали бы не по своей вине. У файла своя ссылка — гасит он только её.
 *
 * Проверяется ровно то, ради чего кнопка существует: тот, кому ссылку переслали, теряет
 * доступ в тот же момент, а не «после истечения срока».
 */

import { expect, test } from '@playwright/test';

import { issueLink } from './link';

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
  await managerPage.getByRole('button', { name: 'Перевыпустить ссылку' }).first().click();
  await expect(
    managerPage.getByText('Ссылка показывается один раз', { exact: false }),
  ).toBeVisible();

  // Страница, открытая по прежней ссылке, теряет доступ на следующем же запросе.
  await beforePage.reload();
  await expect(beforePage.getByText('Откройте ORBITA по своей личной ссылке')).toBeVisible();

  await before.close();
  await manager.close();
});

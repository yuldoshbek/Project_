/**
 * Вход по личной ссылке — на живой системе.
 *
 * Это первый критерий приёмки блока 0: заказчик открывает ORBITA по своей ссылке и видит
 * систему. Всё остальное — оболочка, темы, разделы — не имеет смысла, если этот сценарий
 * не работает в настоящем браузере с настоящими cookie.
 */

import { expect, test } from '@playwright/test';

import { issueLink } from './link';

let link: string;

test.beforeAll(() => {
  link = issueLink();
});

test('без ссылки система не отдаёт ничего', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('Откройте ORBITA по своей личной ссылке')).toBeVisible();
});

test('по личной ссылке открывается система', async ({ page }) => {
  await page.goto(link);

  // После перехода человек оказывается в приложении, а не на странице с токеном.
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: 'Пульт' })).toBeVisible();
});

test('сессия держится между переходами', async ({ page }) => {
  await page.goto(link);
  await page.goto('/management');

  await expect(page.getByRole('heading', { name: 'Управление' })).toBeVisible();
  // Справочники наполнены — это критерий приёмки блока 0.
  await expect(page.getByText('Направления')).toBeVisible();
});

test('cookie сессии закрыта от скриптов', async ({ page, context }) => {
  await page.goto(link);

  const cookies = await context.cookies();
  const session = cookies.find((cookie) => cookie.name === '__Host-orbita');

  expect(session, 'сессионной cookie нет').toBeDefined();
  expect(session?.httpOnly, 'cookie доступна из JavaScript').toBe(true);
  expect(session?.sameSite).toBe('Lax');
});

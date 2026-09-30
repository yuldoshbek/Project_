/**
 * Утренняя сводка — вкладка Пульта на живой системе.
 *
 * Что проверяется запуском:
 *
 * 1. касание уведомления ведёт на вкладку (`/?view=summary`), и в ней те же строки, что на
 *    Пульте: «ждут решения» — ступень лестницы, в том же порядке;
 * 2. на iPhone в Safari — сначала «на экран «Домой»» (ТЗ 8), кнопки «включить» там нет;
 * 3. на телефоне цели нажатия не меньше 44 px и горизонтальной прокрутки нет;
 * 4. помощник видит настоящую доставку: пока руководитель не включил уведомления — «не придёт»;
 * 5. руководитель включает уведомления — подписку принимает и хранит настоящий сервер, карточка
 *    говорит «Включены · с …», а помощник видит устройство руководителя. Контур сценариев не
 *    рабочий, расписание сюда сводку не шлёт — и карточка не обещает её ко времени.
 *
 * Браузерная часть пушей подменена (`stubPush`): в Chromium сценариев нет службы пушей. Сервер
 * — настоящий, и ему нужен ключ VAPID: в конвейере его создаёт `ci.yml`, локально он в `.env`.
 *
 * Порядок сценариев важен: снимки идут первыми, пока подписки руководителя нет. Её стирает
 * выпуск ссылки руководителя — в `beforeAll` этого и каждого файла сценариев.
 *
 * Снимки трёх устройств в двух темах — в папку отчёта блока. Нужны вымышленные данные
 * (`make demo`).
 */

import { randomUUID } from 'node:crypto';

import { expect, test, type Page } from '@playwright/test';

import { REPORT_DIR, issueLink } from './link';

const SIZES = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1440, height: 900 },
  { name: 'monitor', width: 2560, height: 1440 },
] as const;

const THEMES = ['light', 'dim'] as const;

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

const MIN_TOUCH_TARGET = 44;

/**
 * Подписи доставки у помощника — все состояния. Какое из них, зависит от часов и контура:
 * сценарии идут на вымышленных данных, а там расписания нет и подпись — «Не по расписанию».
 */
const DELIVERY = /^(Пришла|Ещё не время|Отправляется|Не ушла|Сегодня не пришла|Не по расписанию)$/;

/**
 * Ключи шифрования подписки. Сервер проверяет их форму — точка P-256 и 16 байт, — поэтому
 * они настоящие: открытая точка сгенерирована один раз, закрытый ключ к ней выброшен. Секрета
 * здесь нет — это то, что браузер и так отдаёт серверу.
 */
const KEYS = {
  p256dh: 'BJwh8qcTbPeksWy4AoxZZKAjrLY3yan-9ydDcE8xTuBRa1OZLCzBku1Fvg_2YTz_xDlydszk5FG5SMcNZslhkd0',
  auth: 'POIZrrDUbgme5CUOyHTnbw',
};

let leader: string;
let assistant: string;

test.beforeAll(() => {
  leader = issueLink('leader');
  assistant = issueLink('assistant');
});

/**
 * Пуши браузера — подменой, сервер — настоящий.
 *
 * Безголовый Chromium отвечает «запрещено» на любые уведомления, даже с выданным разрешением,
 * а службы пушей у него нет, и настоящий `subscribe` падает. Подменены разрешение и
 * регистрация service worker: подписка уходит на сервер как из настоящего браузера, и сервер
 * проверяет её сам — адрес службы пушей и ключи.
 */
async function stubPush(page: Page) {
  await page.addInitScript(
    ({ endpoint, keys }) => {
      let permission: NotificationPermission = 'default';
      let current: object | null = null;
      if (!('Notification' in window) || !('serviceWorker' in navigator)) return;

      Object.defineProperty(Notification, 'permission', {
        get: () => permission,
        configurable: true,
      });
      Notification.requestPermission = () => {
        permission = 'granted';
        return Promise.resolve(permission);
      };
      const pushManager = {
        getSubscription: () => Promise.resolve(current),
        subscribe: (options: { applicationServerKey: Uint8Array }) => {
          const applicationServerKey = new Uint8Array(options.applicationServerKey).slice().buffer;
          current = {
            endpoint,
            options: { applicationServerKey, userVisibleOnly: true },
            toJSON: () => ({ endpoint, expirationTime: null, keys }),
            unsubscribe: () => {
              current = null;
              return Promise.resolve(true);
            },
          };
          return Promise.resolve(current);
        },
      };
      navigator.serviceWorker.getRegistration = () =>
        Promise.resolve({ active: {}, pushManager } as unknown as ServiceWorkerRegistration);
    },
    { endpoint: `https://fcm.googleapis.com/fcm/send/e2e-${randomUUID()}`, keys: KEYS },
  );
}

async function openSummary(page: Page, link: string, theme: (typeof THEMES)[number] = 'light') {
  await stubPush(page);
  await page.goto(link);
  await page.evaluate((value) => {
    localStorage.setItem('orbita.theme', value);
    document.documentElement.setAttribute('data-theme', value);
  }, theme);
  await page.goto('/?view=summary');
  await expect(page.getByRole('heading', { name: 'Утренняя сводка' })).toBeVisible();
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'горизонтальная прокрутка').toBeLessThanOrEqual(1);
}

for (const size of SIZES) {
  for (const theme of THEMES) {
    test(`Сводка: ${size.name}, тема ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openSummary(page, leader, theme);
      // Снимок — то, что руководитель видит на своём устройстве: кнопку, а не «нет ключа».
      await expect(
        page.getByRole('button', { name: 'Включить уведомления' }),
        'у сервера нет ключа VAPID (ORBITA_VAPID_PRIVATE_KEY)',
      ).toBeVisible();
      await page.screenshot({
        path: `${REPORT_DIR}/summary-${size.name}-${theme}.png`,
        animations: 'disabled',
      });
      await noOverflow(page);
    });
  }
}

test('вкладка — те же строки, что на Пульте', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSummary(page, leader);
  await expect(page.getByRole('tab', { name: 'Сводка' })).toHaveAttribute('aria-selected', 'true');

  const awaiting = page.locator('section', {
    has: page.getByRole('heading', { name: 'Ждут решения' }),
  });
  const titles = await awaiting
    .locator('li button[aria-expanded] > span:nth-child(2)')
    .allTextContents();

  await page.getByRole('tab', { name: 'Сейчас' }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole('button', { name: 'Показать только: Ждёт решения' }).click();
  const ladder = await page
    .locator('main ol > li button[aria-expanded] > span:nth-child(2)')
    .allTextContents();
  expect(titles.length, 'в демо нет строк «ждёт решения»').toBeGreaterThan(0);
  expect(titles).toEqual(ladder);
});

test('помощник: сводка не придёт, пока руководитель не включил уведомления', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSummary(page, assistant);
  await expect(page.getByRole('heading', { name: 'Кому приходит' })).toBeVisible();
  await expect(page.getByText(/порог «Утренняя сводка»/)).toBeVisible();
  // Подписок руководителя нет: их стёр выпуск его ссылки в `beforeAll`.
  await expect(page.getByText('Не придёт: у руководителя не включены уведомления')).toBeVisible();
  await expect(page.getByText(/У руководителя уведомления не включены/)).toBeVisible();
  await page.screenshot({
    path: `${REPORT_DIR}/summary-assistant-laptop-light.png`,
    animations: 'disabled',
  });
});

test('iPhone в Safari: сначала на экран «Домой», потом уведомления', async ({ browser }) => {
  const context = await browser.newContext({
    userAgent: IPHONE,
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  const page = await context.newPage();
  await openSummary(page, leader);

  const device = page.locator('section', {
    has: page.getByRole('heading', { name: 'Уведомления на этом устройстве' }),
  });
  await expect(device.getByText('На экран «Домой»', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Включить уведомления' })).toHaveCount(0);
  await device.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${REPORT_DIR}/summary-install-phone-light.png`,
    animations: 'disabled',
  });

  for (const target of await page.locator('main').locator('button:visible, a:visible').all()) {
    const box = await target.boundingBox();
    if (box) expect(box.height).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  }
  await noOverflow(page);
  await context.close();
});

test('руководитель включает уведомления — помощник видит его устройство', async ({
  page,
  browser,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSummary(page, leader);
  // Руководителю «дойдёт ли» отвечает карточка его устройства, а не «пришла на iPhone».
  await expect(page.getByText(DELIVERY)).toHaveCount(0);

  await page.getByRole('button', { name: 'Включить уведомления' }).click();

  const device = page.locator('section', {
    has: page.getByRole('heading', { name: 'Уведомления на этом устройстве' }),
  });
  await expect(device.getByText('Включены', { exact: true })).toBeVisible();
  await expect(device).toContainText(
    /с \d{2}\.\d{2}\.\d{4} · здесь приходит только «ждёт вашего решения»/,
  );
  await expect(device).not.toContainText('сводка придёт в');

  const other = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const second = await other.newPage();
  await openSummary(second, assistant);
  const recipient = second.locator('section', {
    has: second.getByRole('heading', { name: 'Кому приходит' }),
  });
  await expect(recipient).toContainText(/\S+ руководителя, с \d{2}\.\d{2}\.\d{4}/);
  // Устройство есть — доставка отвечает по существу, а не «не придёт».
  await expect(second.getByText(DELIVERY)).toBeVisible();
  await other.close();
});

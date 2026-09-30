/**
 * Что показать на устройстве: на iPhone без экрана «Домой» уведомлений нет вовсе — сначала
 * установка; запрет в настройках кнопкой не снять. И подписка: ждёт, пока worker встанет, но
 * не дольше `WORKER_WAIT_MS` — кнопка «Включить» не висит без ответа.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  NoWorkerError,
  WORKER_WAIT_MS,
  deviceSetup,
  isAppleMobile,
  keyBytes,
  sameKey,
  subscribe,
  subscriptionBody,
  type DeviceEnvironment,
} from './notifications';

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const IPAD_AS_MAC =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';
const CHROME =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36';

function env(overrides: Partial<DeviceEnvironment>): DeviceEnvironment {
  return {
    userAgent: CHROME,
    touchPoints: 0,
    standalone: false,
    pushCapable: true,
    permission: 'default',
    ...overrides,
  };
}

describe('deviceSetup', () => {
  it('iPhone в Safari — сначала на экран «Домой»', () => {
    expect(deviceSetup(env({ userAgent: IPHONE, pushCapable: false, permission: null }))).toBe(
      'install',
    );
  });

  it('iPad называет себя «Macintosh», но касаний у него больше одного', () => {
    expect(deviceSetup(env({ userAgent: IPAD_AS_MAC, touchPoints: 5 }))).toBe('install');
    expect(deviceSetup(env({ userAgent: IPAD_AS_MAC, touchPoints: 0 }))).toBe('ready');
  });

  it('с экрана «Домой» — можно включать', () => {
    expect(deviceSetup(env({ userAgent: IPHONE, standalone: true }))).toBe('ready');
  });

  it('браузер без уведомлений и запрет в настройках', () => {
    expect(deviceSetup(env({ pushCapable: false, permission: null }))).toBe('unsupported');
    expect(deviceSetup(env({ permission: 'denied' }))).toBe('denied');
  });

  it('запрет снимается по-разному: в настройках iPhone или в настройках сайта', () => {
    expect(isAppleMobile(env({ userAgent: IPHONE, standalone: true }))).toBe(true);
    expect(isAppleMobile(env({ userAgent: IPAD_AS_MAC, touchPoints: 5 }))).toBe(true);
    expect(isAppleMobile(env({}))).toBe(false);
  });
});

/** Открытый ключ сервера — точка P-256, 65 байт с 0x04 впереди; в base64url без «=». */
const KEY =
  'BCGMnF2SzmRBdUfjotw5UOjT7dzbfuITkzf-vQlO-Rd-5cgg6YnBwslxqINz5yASCxoEP3DM-cuaBxwvqOwwBq8';

function subscription(key: Uint8Array | null, json: PushSubscriptionJSON = {}): PushSubscription {
  return {
    endpoint: 'https://fcm.googleapis.com/fcm/send/unit-1',
    options: { applicationServerKey: key ? key.slice().buffer : null, userVisibleOnly: true },
    toJSON: () => json,
  } as unknown as PushSubscription;
}

describe('ключ сервера', () => {
  it('base64url со «-» и «_» без «=» — те же 65 байт, что у сервера', () => {
    const bytes = keyBytes(KEY);
    expect(bytes).toHaveLength(65);
    expect(bytes[0]).toBe(0x04);
    // Обратно — та же строка: ни «-», ни «_» не потерялись.
    const back = btoa(String.fromCharCode(...bytes))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    expect(back).toBe(KEY);
  });

  it('подписка другим ключом — не наша: после смены ключа она не доставляет', () => {
    const other = keyBytes(KEY);
    other[1] = (other[1] ?? 0) ^ 0xff;
    expect(sameKey(subscription(keyBytes(KEY)), KEY)).toBe(true);
    expect(sameKey(subscription(other), KEY)).toBe(false);
    expect(sameKey(subscription(null), KEY)).toBe(false);
  });
});

describe('что уходит серверу', () => {
  it('адрес и ключи шифрования — без срока действия и прочего из toJSON()', () => {
    const keys = { p256dh: 'p256dh-key', auth: 'auth-key' };
    expect(
      subscriptionBody(
        subscription(null, {
          endpoint: 'https://fcm.googleapis.com/fcm/send/unit-1',
          expirationTime: null,
          keys,
        }),
      ),
    ).toEqual({ endpoint: 'https://fcm.googleapis.com/fcm/send/unit-1', keys });
  });
});

/** Worker, который ещё ставится: состояние меняется событием `statechange`, как в браузере. */
class PendingWorker extends EventTarget {
  state: ServiceWorkerState = 'installing';

  become(state: ServiceWorkerState) {
    this.state = state;
    this.dispatchEvent(new Event('statechange'));
  }
}

/**
 * Регистрация без подписки; `active` — worker уже встал, `pending` — ещё ставится. Без обоих —
 * регистрация, чей файл worker ещё скачивается: первый worker приходит событием `updatefound`
 * (`arrive`).
 */
function registration({
  active = false,
  pending = null,
}: { active?: boolean; pending?: PendingWorker | null } = {}) {
  const made = subscription(keyBytes(KEY));
  const pushManager = {
    getSubscription: vi.fn(() => Promise.resolve(null)),
    subscribe: vi.fn(() => Promise.resolve(made)),
  };
  const value = Object.assign(new EventTarget(), {
    active: active ? {} : null,
    installing: pending as PendingWorker | null,
    waiting: null,
    pushManager,
  });
  const arrive = (worker: PendingWorker) => {
    value.installing = worker;
    value.dispatchEvent(new Event('updatefound'));
  };
  return { pushManager, arrive, value: value as unknown as ServiceWorkerRegistration };
}

describe('подписка ждёт worker, но не вечно', () => {
  afterEach(() => vi.useRealTimers());

  it('worker уже встал — подписка сразу', async () => {
    const { value, pushManager } = registration({ active: true });
    await subscribe(value, KEY);
    expect(pushManager.subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(KEY),
    });
  });

  it('worker ставится — подписка, когда он встал', async () => {
    const worker = new PendingWorker();
    const { value, pushManager } = registration({ pending: worker });
    const done = subscribe(value, KEY);
    await Promise.resolve();
    expect(pushManager.subscribe).not.toHaveBeenCalled();

    worker.become('installed');
    worker.become('activating');
    worker.become('activated');

    await done;
    expect(pushManager.subscribe).toHaveBeenCalledTimes(1);
  });

  it('установка сорвалась — отказ словами, а не вечное ожидание', async () => {
    const worker = new PendingWorker();
    const { value, pushManager } = registration({ pending: worker });
    const done = subscribe(value, KEY);
    await Promise.resolve();

    worker.become('redundant');

    await expect(done).rejects.toBeInstanceOf(NoWorkerError);
    expect(pushManager.subscribe).not.toHaveBeenCalled();
  });

  it('файл worker ещё скачивается — подписка, когда первый worker встал', async () => {
    const { value, pushManager, arrive } = registration();
    const done = subscribe(value, KEY);
    await Promise.resolve();
    expect(pushManager.subscribe).not.toHaveBeenCalled();

    const worker = new PendingWorker();
    arrive(worker);
    worker.become('activated');

    await done;
    expect(pushManager.subscribe).toHaveBeenCalledTimes(1);
  });

  it('первый worker так и не появился — через 15 секунд отказ', async () => {
    vi.useFakeTimers();
    const { value, pushManager } = registration();
    const refused = expect(subscribe(value, KEY)).rejects.toBeInstanceOf(NoWorkerError);

    await vi.advanceTimersByTimeAsync(WORKER_WAIT_MS);

    await refused;
    expect(pushManager.subscribe).not.toHaveBeenCalled();
  });

  it('worker так и не встал — через 15 секунд отказ, кнопка снова доступна', async () => {
    vi.useFakeTimers();
    const { value, pushManager } = registration({ pending: new PendingWorker() });
    const done = subscribe(value, KEY);
    const refused = expect(done).rejects.toBeInstanceOf(NoWorkerError);

    await vi.advanceTimersByTimeAsync(WORKER_WAIT_MS - 1);
    expect(pushManager.subscribe).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    await refused;
    expect(pushManager.subscribe).not.toHaveBeenCalled();
  });
});

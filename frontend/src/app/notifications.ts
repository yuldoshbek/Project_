/**
 * Может ли это устройство показывать уведомления ORBITA (ТЗ 8).
 *
 * На iPhone уведомления работают только у ORBITA, установленной на экран «Домой»: в Safari их
 * нет вовсе, и кнопка «включить» там ничего бы не сделала. Поэтому сначала — установлена ли,
 * потом — умеет ли браузер, и только потом — разрешение. Что показать на каждом шаге, решает
 * экран «Сводка» (`sections/pult/Summary.tsx`).
 *
 * Здесь же подписка на пуши — всё, что говорит с браузером. С сервером о подписке говорит
 * `sections/pult/usePult.ts`.
 */

export type DeviceSetup =
  /** iPhone или iPad, ORBITA открыта в Safari: сначала — на экран «Домой». */
  | 'install'
  /** Браузер уведомлений не показывает. */
  | 'unsupported'
  /** Уведомления запрещены в настройках устройства: кнопкой их не вернуть. */
  | 'denied'
  /** Можно включать. */
  | 'ready';

export interface DeviceEnvironment {
  userAgent: string;
  /** Касаний больше одного: iPad с iPadOS называет себя «Macintosh». */
  touchPoints: number;
  /** Открыта со значка на экране «Домой», а не во вкладке браузера. */
  standalone: boolean;
  /** Есть уведомления, service worker и подписка на пуши. */
  pushCapable: boolean;
  permission: NotificationPermission | null;
}

export function readEnvironment(): DeviceEnvironment {
  const pushCapable =
    'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
  return {
    userAgent: navigator.userAgent,
    touchPoints: navigator.maxTouchPoints,
    standalone:
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true,
    pushCapable,
    permission: pushCapable ? Notification.permission : null,
  };
}

/**
 * iPhone или iPad. Отличается не только установкой: запрет уведомлений снимается в настройках
 * iPhone, а в браузере на ноутбуке — в настройках сайта.
 */
export function isAppleMobile({ userAgent, touchPoints }: DeviceEnvironment): boolean {
  return /iPhone|iPad|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && touchPoints > 1);
}

export function deviceSetup(environment: DeviceEnvironment): DeviceSetup {
  if (isAppleMobile(environment) && !environment.standalone) return 'install';
  if (!environment.pushCapable) return 'unsupported';
  if (environment.permission === 'denied') return 'denied';
  return 'ready';
}

/**
 * Регистрация service worker этой страницы; `null` — его нет, как на сервере разработки.
 *
 * `getRegistration`, а не `ready`: `ready` ждёт worker вечно, если его не зарегистрировали, и
 * карточка устройства висела бы в «загрузке».
 */
export async function workerRegistration(): Promise<ServiceWorkerRegistration | null> {
  return (await navigator.serviceWorker.getRegistration()) ?? null;
}

/**
 * Worker исчез между показом кнопки и касанием или так и не встал: подписаться не на что.
 * Текста у ошибки нет — экран показывает свой ключ перевода.
 */
export class NoWorkerError extends Error {
  override name = 'NoWorkerError';
}

/** Открытый ключ сервера из base64url в байты: так его принимает `subscribe` на любом браузере. */
export function keyBytes(key: string): Uint8Array<ArrayBuffer> {
  const base64 = key.replace(/-/g, '+').replace(/_/g, '/');
  const text = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='));
  const bytes = new Uint8Array(text.length);
  for (let index = 0; index < text.length; index += 1) bytes[index] = text.charCodeAt(index);
  return bytes;
}

/**
 * Подписка сделана этим ключом сервера. После смены ключа старая подписка молча не
 * доставляет ничего: сервер подписывает пуш другим ключом, и служба пушей его отвергает.
 */
export function sameKey(subscription: PushSubscription, key: string): boolean {
  const own = subscription.options.applicationServerKey;
  if (!own) return false;
  const current = new Uint8Array(own);
  const expected = keyBytes(key);
  return (
    current.length === expected.length && current.every((byte, index) => byte === expected[index])
  );
}

/** Подписка этого устройства, сделанная нынешним ключом сервера; `null` — её нет. */
export async function currentSubscription(
  registration: ServiceWorkerRegistration,
  key: string,
): Promise<PushSubscription | null> {
  const subscription = await registration.pushManager.getSubscription();
  return subscription && sameKey(subscription, key) ? subscription : null;
}

/**
 * Сколько ждать, пока worker встанет. Установка кладёт в кеш около мегабайта: на медленной
 * сети это секунды, а не минуты, — дольше кнопка висела бы без ответа.
 */
export const WORKER_WAIT_MS = 15_000;

/**
 * Дождаться, пока worker регистрации станет активным: подписка требует активного, а сразу
 * после первой загрузки он может ещё ставиться.
 *
 * Не `navigator.serviceWorker.ready`: если установка сорвалась (не скачался файл оболочки),
 * регистрация пропадает, а `ready` не отвечает никогда — кнопка «Включить» осталась бы
 * нажатой без единого слова. Здесь ожидание кончается всегда: worker встал, worker отброшен
 * (`redundant`) или время вышло — в двух последних случаях `NoWorkerError`, и экран говорит
 * своими словами.
 *
 * Регистрация бывает и совсем пустой: `register()` создаёт её до того, как файл worker
 * скачан, и в это время у неё нет ни активного, ни ставящегося (так по спецификации). Тогда
 * ждём `updatefound` — первый worker появится с ним; сорвавшаяся загрузка его не пришлёт, и
 * ожидание кончит таймер.
 */
function activated(registration: ServiceWorkerRegistration): Promise<void> {
  if (registration.active) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let pending: ServiceWorker | null = null;
    const settle = (error?: NoWorkerError) => {
      clearTimeout(timer);
      registration.removeEventListener('updatefound', found);
      pending?.removeEventListener('statechange', check);
      if (error) reject(error);
      else resolve();
    };
    const check = () => {
      if (pending?.state === 'activated') settle();
      else if (pending?.state === 'redundant') settle(new NoWorkerError());
    };
    const follow = (worker: ServiceWorker) => {
      pending?.removeEventListener('statechange', check);
      pending = worker;
      worker.addEventListener('statechange', check);
      check();
    };
    const found = () => {
      if (registration.installing) follow(registration.installing);
    };
    const timer = setTimeout(() => settle(new NoWorkerError()), WORKER_WAIT_MS);
    const waiting = registration.installing ?? registration.waiting;
    if (waiting) follow(waiting);
    else registration.addEventListener('updatefound', found);
  });
}

/**
 * Подписать устройство на пуши нынешним ключом сервера.
 *
 * Подписка со старым ключом снимается: браузер не даёт подписаться другим ключом, пока она
 * есть. `userVisibleOnly` — условие Safari и Chrome: каждый пуш показывается человеку.
 */
export async function subscribe(
  registration: ServiceWorkerRegistration,
  key: string,
): Promise<PushSubscription> {
  const existing = await registration.pushManager.getSubscription();
  if (existing && sameKey(existing, key)) return existing;
  if (existing) await existing.unsubscribe();
  await activated(registration);
  return registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: keyBytes(key),
  });
}

/** Что сервер хранит о подписке: адрес службы пушей и ключи шифрования. */
export interface SubscriptionBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export function subscriptionBody(subscription: PushSubscription): SubscriptionBody {
  const { endpoint, keys } = subscription.toJSON();
  return {
    endpoint: endpoint ?? subscription.endpoint,
    keys: { p256dh: keys?.['p256dh'] ?? '', auth: keys?.['auth'] ?? '' },
  };
}

/// <reference lib="webworker" />
/**
 * Service worker ORBITA: оболочка без сети и уведомления.
 *
 * Кешируется оболочка, а не данные. Данные обновляются опросом и обязаны быть свежими:
 * показанный из кеша просроченный срок — это неверное решение руководителя, а не экономия сети.
 *
 * Пуш приносит данные, а не текст: слова складывают те же функции и ключи, что предпросмотр на
 * вкладке «Сводка» (`sections/pult/push.ts`, ADR-0036).
 *
 * Собирается отдельно от приложения (`vite-plugin-pwa`, `injectManifest`) и в бюджет открытия
 * не входит: браузер грузит его сам, в фоне.
 */

import { clientsClaim } from 'workbox-core';
import {
  cleanupOutdatedCaches,
  createHandlerBoundToURL,
  precacheAndRoute,
} from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';

import type { PushPayload } from '@/sections/pult/model';
import { SUMMARY_URL, notificationOf, workerT } from '@/sections/pult/push';

declare let self: ServiceWorkerGlobalScope;

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Переход по адресу отдаёт оболочку, кроме API: личная ссылка — это `/api/access/<токен>`, и
// оболочка на её месте означала бы, что войти по ссылке нельзя.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html'), {
    denylist: [/^\/api\//, /^\/internal\//],
  }),
);

// Новая версия встаёт сразу, а не ждёт, пока закроют все вкладки: приложение с экрана «Домой»
// закрывают редко, и обновление ждало бы днями (`registerType: 'autoUpdate'`).
void self.skipWaiting();
clientsClaim();

const t = workerT();

function read(data: PushMessageData | null): PushPayload | null {
  try {
    return (data?.json() as PushPayload | undefined) ?? null;
  } catch {
    return null;
  }
}

self.addEventListener('push', (event) => {
  const payload = read(event.data);
  const { title, body } = notificationOf(t, payload);
  // Показывается всегда, даже если данные не разобрались: iOS отзывает подписку у того, кто
  // получает пуши молча.
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icon-192.png',
      ...(payload ? { tag: payload.tag } : {}),
      data: { url: payload?.url ?? SUMMARY_URL },
    }),
  );
});

/** Только свой адрес: ссылка из пуша не уводит с ORBITA. */
function target(raw: unknown): string {
  const origin = self.location.origin;
  const url = new URL(typeof raw === 'string' ? raw : SUMMARY_URL, origin);
  return url.origin === origin ? url.href : new URL(SUMMARY_URL, origin).href;
}

async function open(url: string): Promise<void> {
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of windows) {
    try {
      // Открытое окно переводится на сводку, а не открывается второе: у приложения с экрана
      // «Домой» окно одно.
      const focused = await client.focus();
      await focused.navigate(url);
      return;
    } catch {
      // Окно не под этим worker — оно не переводится; пробуем следующее или открываем новое.
    }
  }
  await self.clients.openWindow(url);
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = event.notification.data as { url?: unknown } | null;
  event.waitUntil(open(target(data?.url)));
});

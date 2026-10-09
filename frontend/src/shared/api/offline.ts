/**
 * Последняя картина без сети (блок 4, пакет D; допущение V53).
 *
 * Руководитель открывает ORBITA с iPhone в самолёте, в лифте, на объекте без связи. Оболочку
 * приложения отдаёт service worker, а данные — нет: без них экран — «не получилось». Поэтому
 * последний ответ Пульта и «кто вошёл» хранятся на устройстве и показываются сразу при
 * открытии, с временем данных (инвариант 7), пока свежий ответ не пришёл или пока нет связи.
 *
 * Хранится только это — первый экран руководителя, а не все разделы: данные агентства на
 * устройстве — это риск, и он берётся ровно под задачу «увидеть, что горит, без связи».
 * Старше недели — не показывается. Погашенная сессия (перевыпуск ссылки) стирает картину.
 */

import type { QueryClient, QueryKey } from '@tanstack/react-query';

const KEPT: readonly QueryKey[] = [['pult'], ['me']];
const PREFIX = 'orbita:last:';
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function storageKey(key: QueryKey): string {
  return `${PREFIX}${JSON.stringify(key)}`;
}

function isKept(key: QueryKey): boolean {
  return KEPT.some((each) => JSON.stringify(each) === JSON.stringify(key));
}

// Хранилище может быть недоступно (приватный режим Safari, запрет сайта) — тогда картина
// просто не хранится, а приложение работает как раньше.
function safely<T>(action: () => T): T | undefined {
  try {
    return action();
  } catch {
    return undefined;
  }
}

/** Показать сохранённую картину сразу при открытии — и сразу пометить устаревшей. */
export function restoreLastPicture(client: QueryClient, now = Date.now()): void {
  for (const key of KEPT) {
    const raw = safely(() => window.localStorage.getItem(storageKey(key)));
    if (!raw) continue;
    const saved = safely(() => JSON.parse(raw) as { at: number; data: unknown });
    if (!saved || typeof saved.at !== 'number' || now - saved.at > MAX_AGE_MS) continue;
    client.setQueryData(key, saved.data, { updatedAt: saved.at });
    // Устаревшая сразу: иначе при умолчании «данные не устаревают» (`QUERY_DEFAULTS`)
    // экран так и остался бы на вчерашней картине, не спросив сервер.
    void client.invalidateQueries({ queryKey: key, exact: true, refetchType: 'none' });
  }
}

/** Каждый успешный ответ хранимых запросов — на устройство. */
export function keepLastPicture(client: QueryClient): () => void {
  return client.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success') return;
    if (!isKept(event.query.queryKey)) return;
    const record = JSON.stringify({ at: Date.now(), data: event.query.state.data });
    safely(() => window.localStorage.setItem(storageKey(event.query.queryKey), record));
  });
}

/** Стереть картину: сессия погашена — данные агентства на устройстве больше не нужны. */
export function forgetLastPicture(): void {
  for (const key of KEPT) safely(() => window.localStorage.removeItem(storageKey(key)));
}

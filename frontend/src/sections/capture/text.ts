/**
 * Подписи Захвата: когда записано и куда ушло. Числа — с сервера, здесь только слова.
 */

import type { TFunction } from 'i18next';

import { formatDate, localDay } from '@/shared/time';

import type { Capture } from './model';

const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;

/**
 * «только что», «40 мин назад», «5 ч назад», «вчера», «3 дн назад».
 *
 * Меньше суток — часами; дальше — календарными днями по Ташкенту (инвариант 8): записанное
 * в 23:00 позавчера в девять утра — это «2 дн назад», хотя прошло 34 часа.
 */
export function agoText(t: TFunction, createdAt: string, asOf: string): string {
  const minutes = Math.max(0, Math.round((Date.parse(asOf) - Date.parse(createdAt)) / MINUTE_MS));
  if (minutes < 1) return t('capture.ago.now');
  if (minutes < 60) return t('capture.ago.minutes', { count: minutes });
  const hours = Math.round(minutes / 60);
  const days = Math.round((Date.parse(localDay(asOf)) - Date.parse(localDay(createdAt))) / DAY_MS);
  // 00:10 → 23:50 округляется до 24 ч, но это всё ещё сегодня.
  if (hours < 24 || days === 0) return t('capture.ago.hours', { count: hours });
  return days === 1 ? t('capture.ago.yesterday') : t('capture.ago.days', { count: days });
}

/**
 * «Помощник · 2 ч назад · срок 10.10.2026 · в «Задачах»» — строка под записью.
 * У мероприятия дата — это дата, а не срок; у письма — срок ответа.
 *
 * `demo` — экран на вымышленных данных: просьба руководителя до API в «Задачи» не попадает,
 * и строка говорит «встанет после утверждения», а не «в «Задачах»», — иначе заказчик идёт в
 * «Задачи» и её там не находит.
 */
export function metaText(t: TFunction, capture: Capture, asOf: string, demo: boolean): string {
  const parts = [t(`capture.authors.${capture.author}`), agoText(t, capture.created_at, asOf)];
  if (capture.due_on) {
    parts.push(t(`capture.recent.due.${capture.kind}`, { date: formatDate(capture.due_on) }));
  }
  if (capture.destination === 'inbox') parts.push(t(`capture.recent.inbox.${capture.kind}`));
  else if (demo && capture.kind === 'request') parts.push(t('capture.recent.requestLater'));
  else parts.push(t('capture.recent.tasks'));
  return parts.join(' · ');
}

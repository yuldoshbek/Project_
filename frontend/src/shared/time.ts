/**
 * Показ времени.
 *
 * Хранение в UTC, показ в ташкентском времени — инвариант 5 (CLAUDE.md). Разница в пять
 * часов кажется мелочью ровно до первого срока: задача со сроком в 21:00 по Ташкенту
 * хранится как 16:00 UTC, а срок в 02:00 ночи — как 21:00 UTC **предыдущего дня**. Срежь
 * из такой метки первые десять символов — и на экране окажется вчерашнее число.
 *
 * Часовой пояс задан явно, а не берётся из браузера: оба пользователя в Ташкенте, но
 * ноутбук в командировке переводить дату не должен — срок назначен по времени агентства.
 */

import { DISPLAY_TIME_ZONE } from './config';

const DATE = new Intl.DateTimeFormat('ru-RU', {
  timeZone: DISPLAY_TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const DATE_TIME = new Intl.DateTimeFormat('ru-RU', {
  timeZone: DISPLAY_TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/** Дата метки времени по времени агентства: «30.08.2026». Пусто, если срока нет. */
export function formatDate(value: string | null | undefined): string {
  const moment = parse(value);
  return moment === null ? '' : DATE.format(moment);
}

/** Дата и время по времени агентства: «30.08.2026, 21:00». Пусто, если метки нет. */
export function formatDateTime(value: string | null | undefined): string {
  const moment = parse(value);
  return moment === null ? '' : DATE_TIME.format(moment);
}

/**
 * Разбор метки времени.
 *
 * Непонятная строка показывается пустотой, а не «Invalid Date»: пустая ячейка читается
 * как «срока нет», а английская ругань посреди русского экрана — как поломка системы.
 */
function parse(value: string | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null;
  const moment = new Date(value);
  return Number.isNaN(moment.getTime()) ? null : moment;
}

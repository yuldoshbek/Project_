/**
 * Время на экране — всегда в Ташкенте.
 *
 * В базе и в ответах API время в UTC (CLAUDE.md, инвариант о времени). Показывать его как
 * есть нельзя: руководитель в поездке увидел бы сдвинутые сроки и принял бы решение по
 * чужому дню. Перевод делается здесь, в одном месте, а не в каждом компоненте.
 */

export const AGENCY_TIMEZONE = 'Asia/Tashkent';

const dateFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: AGENCY_TIMEZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const dateTimeFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: AGENCY_TIMEZONE,
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

const timeFormat = new Intl.DateTimeFormat('ru-RU', {
  timeZone: AGENCY_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
});

export function formatDate(value: string | Date): string {
  return dateFormat.format(new Date(value));
}

export function formatDateTime(value: string | Date): string {
  return dateTimeFormat.format(new Date(value));
}

export function formatTime(value: string | Date): string {
  return timeFormat.format(new Date(value));
}

/**
 * «Только что», «12 минут назад», «вчера в 18:40».
 *
 * Относительное время — не украшение: на вопрос «свежие ли это данные» точная дата
 * отвечает хуже, чем «сорок минут назад». Дальше двух суток относительность теряет смысл,
 * и возвращается дата.
 */
export function formatSince(value: string | Date | null | undefined, never: string): string {
  if (!value) return never;

  const moment = new Date(value);
  const minutes = Math.round((Date.now() - moment.getTime()) / 60_000);

  if (minutes < 1) return 'только что';
  if (minutes < 60) return `${minutes} мин назад`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  if (hours < 48) return `вчера в ${formatTime(moment)}`;

  return formatDate(moment);
}

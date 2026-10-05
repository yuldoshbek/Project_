/**
 * Подписи раздела: вид даты, правило цикла, горячий день словами, заголовки дней и
 * месяцев. Числа приходят с сервера; здесь только слова вокруг них.
 */

import type { TFunction } from 'i18next';

import { intlLocale } from '@/shared/i18n';

import { KINDS, type CalendarItem, type CycleRuleFields, type HotDay } from './model';

const DAY_MS = 86_400_000;

// Названия дней и месяцев — на языке интерфейса; форматтер собирается один раз на язык.
const formats = new Map<string, Intl.DateTimeFormat>();

function formatter(name: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const locale = intlLocale();
  const key = `${locale}:${name}`;
  let found = formats.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, options);
    formats.set(key, found);
  }
  return found;
}

const weekdayDay = () =>
  formatter('weekdayDay', { weekday: 'short', day: 'numeric', month: 'long', timeZone: 'UTC' });

const monthName = () => formatter('monthName', { month: 'long', timeZone: 'UTC' });

const weekdayShort = () => formatter('weekdayShort', { weekday: 'short', timeZone: 'UTC' });

const dayMonth = () => formatter('dayMonth', { day: 'numeric', month: 'long', timeZone: 'UTC' });

function utc(date: string): Date {
  return new Date(`${date.slice(0, 10)}T00:00:00Z`);
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** «Чт, 1 октября» — заголовок дня. */
export function dayTitle(date: string): string {
  return capital(weekdayDay().format(utc(date)));
}

/** «Сентябрь 2026» — заголовок месяца сетки. */
export function monthTitle(month: string): string {
  return `${capital(monthName().format(utc(`${month}-01`)))} ${month.slice(0, 4)}`;
}

/**
 * «20 января» — день срока в правиле цикла.
 *
 * Год — високосный, чтобы 29 февраля осталось 29 февраля. Дня, которого нет в месяце
 * (30 февраля), через дату не показать — она перекатится в март и спрячет опечатку, которую
 * человек должен увидеть: такой день пишется числом и месяцем как есть.
 */
export function dayOfYear(month: number, day: number): string {
  const last = new Date(Date.UTC(2000, month, 0)).getUTCDate();
  if (Number.isInteger(day) && day >= 1 && day <= last) {
    return dayMonth().format(new Date(Date.UTC(2000, month - 1, day)));
  }
  const genitive = dayMonth()
    .format(new Date(Date.UTC(2000, month - 1, 1)))
    .replace(/^1\s/, '');
  return `${day} ${genitive}`;
}

/** «ежегодно, 20 января», «ежеквартально, 5-го числа», «раз в 3 года, 1 марта, с 2027». */
export function ruleText(t: TFunction, cycle: CycleRuleFields): string {
  if (cycle.rule === 'quarterly') return t('calendar.rule.quarterly', { day: cycle.day });
  if (cycle.rule === 'annual') {
    return t('calendar.rule.annual', { date: dayOfYear(cycle.month, cycle.day) });
  }
  return t('calendar.rule.everyYears', {
    count: cycle.every_years,
    date: dayOfYear(cycle.month, cycle.day),
    year: cycle.anchor_year,
  });
}

/** Перечень словами: «2 вехи, задача и годовой цикл». */
function listed(parts: string[], t: TFunction): string {
  if (parts.length <= 1) return parts.join('');
  return `${parts.slice(0, -1).join(', ')} ${t('calendar.and')} ${parts.at(-1)!}`;
}

/**
 * «4 срока: 2 вехи, задача и годовой цикл» — горячий день словами (ТЗ 5: «24.09 — 3 срока и
 * мероприятие»). Одна запись вида называется без числа: «задача», а не «1 задача».
 */
export function hotText(t: TFunction, hot: Pick<HotDay, 'count' | 'kinds'>): string {
  const parts = KINDS.filter((kind) => (hot.kinds[kind] ?? 0) > 0).map((kind) => {
    const count = hot.kinds[kind]!;
    return count === 1 ? t(`calendar.one.${kind}`) : t(`calendar.many.${kind}`, { count });
  });
  return `${t('calendar.hot.count', { count: hot.count })}: ${listed(parts, t)}`;
}

/** «Пн», «Вт», … «Вс» — шапка сетки, неделя с понедельника. */
export function weekdayNames(): string[] {
  // 1 января 2024 года — понедельник.
  return Array.from({ length: 7 }, (_, index) =>
    capital(weekdayShort().format(new Date(Date.UTC(2024, 0, 1 + index)))),
  );
}

/** «Январь» … «Декабрь» — выбор месяца в форме цикла. */
export function monthNames(): string[] {
  return Array.from({ length: 12 }, (_, index) =>
    capital(monthName().format(new Date(Date.UTC(2001, index, 1)))),
  );
}

/** «сегодня», «завтра», «через 12 дн», «3 дн назад». */
export function relativeDay(t: TFunction, date: string, today: string): string {
  const days = Math.round((utc(date).getTime() - utc(today).getTime()) / DAY_MS);
  if (days === 0) return t('calendar.day.today');
  if (days === 1) return t('calendar.day.tomorrow');
  if (days > 1) return t('calendar.day.in', { days });
  return t('calendar.day.ago', { days: -days });
}

/**
 * Подпись клетки сетки для экранного диктора: день, сколько сроков, сколько скрыто
 * фильтром, горячий ли.
 */
export function cellLabel(
  t: TFunction,
  date: string,
  count: number,
  hidden: number,
  hot: boolean,
): string {
  const parts = [t('calendar.day.cell', { day: dayTitle(date), count })];
  if (hidden > 0) parts.push(t('calendar.filter.hidden', { count: hidden }).toLowerCase());
  if (hot) parts.push(t('calendar.hot.day').toLowerCase());
  return parts.join(', ');
}

/** Название даты. У решения без текста — вид решения, как на Пульте (`pult/text.rowTitle`). */
export function itemTitle(
  t: TFunction,
  item: Pick<CalendarItem, 'title' | 'kind' | 'decision_kind'>,
): string {
  if (item.title) return item.title;
  if (item.decision_kind) return t(`pult.decisions.${item.decision_kind}`);
  return t(`calendar.kinds.${item.kind}`);
}

/** «на 4 недели вперёд» — окно ответа карточки, как его прислал сервер. */
export function hotWindowText(t: TFunction, days: number): string {
  return days % 7 === 0
    ? t('calendar.hot.weeks', { count: days / 7 })
    : t('calendar.hot.days', { count: days });
}

/** «Задача · сделано», «Веха · срок проекта» — вид даты с отметками. */
export function kindText(
  t: TFunction,
  item: Pick<CalendarItem, 'kind' | 'is_done' | 'ends_project'>,
): string {
  const parts = [t(`calendar.kinds.${item.kind}`)];
  if (item.ends_project) parts.push(t('calendar.endsProject'));
  if (item.is_done) parts.push(t('calendar.done'));
  return parts.join(' · ');
}

/**
 * Видна ли дата при выбранных источниках. Веха «и срок проекта» — ещё и срок проекта: она
 * видна и тому, кто оставил одни сроки проектов.
 */
export function isShown(
  item: Pick<CalendarItem, 'kind' | 'ends_project'>,
  shown: ReadonlySet<string>,
): boolean {
  return shown.has(item.kind) || (item.ends_project && shown.has('project'));
}

/** «Горячий день: 4 срока: …» — строка над списком горячего дня. */
export function hotDayText(t: TFunction, hot: Pick<HotDay, 'count' | 'kinds'>): string {
  return `${t('calendar.hot.day')}: ${hotText(t, hot)}`;
}

/** «Чт, 1 октября · сегодня» — строка горячего дня в карточке. */
export function hotDayTitle(t: TFunction, date: string, today: string): string {
  return date === today ? `${dayTitle(date)} · ${t('calendar.day.today')}` : dayTitle(date);
}

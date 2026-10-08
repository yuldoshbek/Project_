/**
 * Форматтеры `Intl` на языке интерфейса: названия месяцев и дней, числа с разрядами.
 *
 * Форматтер берётся при каждом вызове, а не собирается при загрузке модуля. Модуль
 * загружается один раз, а язык меняется на ходу: собранный заранее форматтер навсегда
 * остаётся русским — так в узбекском интерфейсе Ижро, Программы и таймлайн проектов
 * показывали «октябрь» и «окт» (замечание ревью блока 3). Сборка `Intl` не бесплатна —
 * сетка календаря просит её на каждую клетку, — поэтому готовый форматтер запоминается
 * на пару «язык + настройки».
 */

import { intlLocale } from '.';

const dates = new Map<string, Intl.DateTimeFormat>();
const numbers = new Map<string, Intl.NumberFormat>();

// Ключ — сами настройки, а не имя от вызывающего: два места с одним именем и разными
// настройками получили бы чужой форматтер, а разный порядок полей стоит лишь лишней записи.
function keyOf(locale: string, options: object): string {
  return `${locale}|${JSON.stringify(options)}`;
}

/** Форматтер дат на языке интерфейса. */
export function dateFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const locale = intlLocale();
  const key = keyOf(locale, options);
  let found = dates.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, options);
    dates.set(key, found);
  }
  return found;
}

/** Форматтер чисел на языке интерфейса. */
export function numberFormat(options: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const locale = intlLocale();
  const key = keyOf(locale, options);
  let found = numbers.get(key);
  if (!found) {
    found = new Intl.NumberFormat(locale, options);
    numbers.set(key, found);
  }
  return found;
}

/** Первая буква — заглавная по правилам языка интерфейса: «октябрь» → «Октябрь». */
export function capital(text: string): string {
  return text.charAt(0).toLocaleUpperCase(intlLocale()) + text.slice(1);
}

/**
 * Общие константы интерфейса.
 *
 * Три письменности — требование ТЗ 10.3, а не удобство: агентство работает и на
 * русском, и на узбекской кириллице, и на узбекской латинице одновременно.
 * Английский добавляется четвёртой локалью без изменений в коде компонентов.
 */

export const SUPPORTED_LOCALES = ['ru', 'uz-Cyrl', 'uz-Latn'] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'ru';

/** Ключ, под которым выбор языка переживает перезагрузку страницы. */
export const LOCALE_STORAGE_KEY = 'orbita.locale';

/** Часовой пояс агентства. Сроки хранятся в UTC, показываются здесь (CLAUDE.md). */
export const DISPLAY_TIME_ZONE = 'Asia/Tashkent';

export function isSupportedLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/**
 * Значение для атрибута lang.
 *
 * Обе узбекские локали — один язык в разных письменностях, поэтому используется
 * тег с указанием алфавита (BCP 47). Браузер по нему выбирает переносы и шрифт.
 */
export function htmlLangFor(locale: Locale): string {
  return locale === 'ru' ? 'ru' : locale === 'uz-Cyrl' ? 'uz-Cyrl' : 'uz-Latn';
}

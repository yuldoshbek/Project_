/**
 * Настройки, приходящие из окружения сборки.
 * Оболочка приложения появится в ORB-005 — здесь только то, что нужно инструментам.
 */

export const SUPPORTED_LOCALES = ['ru', 'uz-Cyrl', 'uz-Latn'] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'ru';

export function isSupportedLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

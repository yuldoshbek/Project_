/**
 * Языки интерфейса: русский, узбекский латиницей и кириллицей (ТЗ 3.8, критерий 3 блока 3).
 *
 * Правило жёсткое: **ни одной строки текста в коде компонентов**, только ключи. Причина не
 * в переводе, а в том, что строка в коде — это строка, которую нельзя переписать без
 * разработчика, а формулировки заказчик правит на приёмке пакетом.
 *
 * Русский словарь — в сборке сразу: с него начинается каждый вход. Узбекские грузятся по
 * требованию отдельными кусками — у руководителя на телефоне первый экран не тянет два
 * словаря, которыми он, может быть, не пользуется. Язык хранится у пользователя на сервере
 * (`/api/me`), а не в браузере: открыл ORBITA на другом устройстве — тот же язык.
 */

import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import { ru } from './ru';

export const DEFAULT_LOCALE = 'ru';

/**
 * `code` — язык i18next (BCP 47: правила множественного числа берутся по нему), `server` —
 * как язык записан у пользователя, `intl` — для названий дней и месяцев.
 */
export const LOCALES = [
  { code: 'ru', server: 'ru', label: 'Русский', intl: 'ru-RU' },
  { code: 'uz-Latn', server: 'uz_latn', label: 'Oʻzbekcha', intl: 'uz-Latn-UZ' },
  { code: 'uz-Cyrl', server: 'uz_cyrl', label: 'Ўзбекча', intl: 'uz-Cyrl-UZ' },
] as const;

export type ServerLocale = (typeof LOCALES)[number]['server'];

const LOADERS: Record<string, () => Promise<Record<string, unknown>>> = {
  'uz-Latn': () => import('./uz-latn').then((module) => module.uzLatn),
  'uz-Cyrl': () => import('./uz-cyrl').then((module) => module.uzCyrl),
};

void i18next.use(initReactI18next).init({
  resources: { ru: { translation: ru } },
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  interpolation: { escapeValue: false },
  // Пропущенный ключ должен быть виден, а не выглядеть пустым местом: пустая графа на
  // экране читается как «данных нет», а это другое сообщение.
  parseMissingKeyHandler: (key) => `⟨${key}⟩`,
  // Рекламная строка библиотеки в консоли браузера и в выводе тестов ничего не сообщает.
  showSupportNotice: false,
});

/** Включить язык пользователя: подгрузить словарь, если его ещё нет, и переключиться. */
export async function applyLocale(server: string): Promise<void> {
  const locale = LOCALES.find((each) => each.server === server) ?? LOCALES[0];
  const load = LOADERS[locale.code];
  if (load && !i18next.hasResourceBundle(locale.code, 'translation')) {
    i18next.addResourceBundle(locale.code, 'translation', await load(), true, true);
  }
  if (i18next.language !== locale.code) await i18next.changeLanguage(locale.code);
  document.documentElement.lang = locale.code;
}

/** Язык для `Intl`: названия дней и месяцев — на языке интерфейса. */
export function intlLocale(): string {
  return LOCALES.find((each) => each.code === i18next.language)?.intl ?? 'ru-RU';
}

/** Текущий язык в записи сервера — для выбора в меню. */
export function currentServerLocale(): ServerLocale {
  return LOCALES.find((each) => each.code === i18next.language)?.server ?? 'ru';
}

export default i18next;

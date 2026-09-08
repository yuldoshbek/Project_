/**
 * Локализация интерфейса.
 *
 * Ни одной пользовательской строки в компонентах — только ключи. Это не стилистика:
 * правило eslint `react/jsx-no-literals` роняет сборку на забытом литерале, потому что
 * иначе узбекские локали расходятся с русской молча и обнаруживаются на приёмке.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import {
  DEFAULT_LOCALE,
  htmlLangFor,
  isSupportedLocale,
  LOCALE_STORAGE_KEY,
  type Locale,
} from '../config';
import ru from './locales/ru.json';
import uzCyrl from './locales/uz-Cyrl.json';
import uzLatn from './locales/uz-Latn.json';

export const resources = {
  ru: { translation: ru },
  'uz-Cyrl': { translation: uzCyrl },
  'uz-Latn': { translation: uzLatn },
} as const;

/**
 * Выбор языка при запуске: сохранённый выбор, затем язык браузера, затем русский.
 *
 * Собственный определитель вместо i18next-browser-languagedetector: нам нужно
 * различать две узбекские письменности, а стандартный определитель сводит их к `uz`.
 */
export function detectLocale(
  storage: Pick<Storage, 'getItem'> | undefined = globalThis.localStorage,
  languages: readonly string[] = globalThis.navigator?.languages ?? [],
): Locale {
  const stored = safeRead(storage);
  if (stored && isSupportedLocale(stored)) {
    return stored;
  }

  for (const language of languages) {
    if (isSupportedLocale(language)) {
      return language;
    }
    // uz, uz-UZ и подобное без указания письменности: в Узбекистане латиница —
    // основная письменность делопроизводства, поэтому она и берётся.
    if (language.toLowerCase().startsWith('uz')) {
      return language.toLowerCase().includes('cyrl') ? 'uz-Cyrl' : 'uz-Latn';
    }
    if (language.toLowerCase().startsWith('ru')) {
      return 'ru';
    }
  }

  return DEFAULT_LOCALE;
}

function safeRead(storage: Pick<Storage, 'getItem'> | undefined): string | null {
  // В приватном окне и при запрете хранилища обращение бросает исключение —
  // язык интерфейса не повод ронять приложение.
  try {
    return storage?.getItem(LOCALE_STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

export function applyLocaleToDocument(locale: Locale): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = htmlLangFor(locale);
  }
}

void i18n.use(initReactI18next).init({
  resources,
  lng: detectLocale(),
  fallbackLng: DEFAULT_LOCALE,
  interpolation: { escapeValue: false },
  returnNull: false,
});

applyLocaleToDocument(i18n.language as Locale);

i18n.on('languageChanged', (language) => {
  if (isSupportedLocale(language)) {
    applyLocaleToDocument(language);
    try {
      globalThis.localStorage?.setItem(LOCALE_STORAGE_KEY, language);
    } catch {
      // Хранилище недоступно — выбор просто не переживёт перезагрузку.
    }
  }
});

export default i18n;

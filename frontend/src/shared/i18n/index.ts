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
 * Ключ сохранения языка. Пока выбор человека в пути, язык из перечитанного `/api/me` —
 * эхо прежнего сохранения — не включается: иначе он перебивал следующий выбор, пока
 * грузился его словарь (найдено ревью правок).
 */
export const LOCALE_MUTATION_KEY = ['locale'] as const;

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

// Номер последнего выбора языка. Пока на 4G грузится словарь одного языка, человек успевает
// выбрать другой, а язык с сервера при входе может прийти позже выбора в меню: без номера
// победил бы не последний выбор, а тот, чей словарь догрузился последним.
let latest = 0;

/**
 * Включить язык пользователя: подгрузить словарь, если его ещё нет, и переключиться.
 *
 * `false` — пока грузился словарь, выбрали другой язык, и этот вызов уже ничего не меняет.
 * Словарь, который не загрузился, — отказ со словами для человека, а не текст браузера.
 */
export async function applyLocale(server: string): Promise<boolean> {
  const turn = ++latest;
  const locale = LOCALES.find((each) => each.server === server) ?? LOCALES[0];
  const load = LOADERS[locale.code];
  if (load && !i18next.hasResourceBundle(locale.code, 'translation')) {
    let bundle: Record<string, unknown>;
    try {
      bundle = await load();
    } catch {
      // Выбор уже сменился — сообщать о словаре, который больше не нужен, незачем.
      if (turn !== latest) return false;
      throw new Error(i18next.t('language.notLoaded'));
    }
    // Словарь кладётся и тогда, когда выбор уже сменился: следующий выбор этого языка
    // не будет грузить его второй раз.
    i18next.addResourceBundle(locale.code, 'translation', bundle, true, true);
  }
  if (turn !== latest) return false;
  if (i18next.language !== locale.code) await i18next.changeLanguage(locale.code);
  if (turn !== latest) return false;
  document.documentElement.lang = locale.code;
  return true;
}

/** Язык для `Intl`: названия дней и месяцев — на языке интерфейса. */
export function intlLocale(): string {
  return LOCALES.find((each) => each.code === i18next.language)?.intl ?? 'ru-RU';
}

function serverOf(language: string): ServerLocale {
  return LOCALES.find((each) => each.code === language)?.server ?? 'ru';
}

/** Текущий язык в записи сервера — для выбора в меню. */
export function currentServerLocale(): ServerLocale {
  return serverOf(i18next.language);
}

/**
 * Название из справочника на языке интерфейса: справочник отдаёт все три написания.
 * Незаполненное — русское, а не пустая графа. `language` — язык i18next; компонент
 * передаёт свой из `useTranslation`, чтобы смена языка перестроила подписи.
 */
export function localName(
  names: Readonly<Record<ServerLocale, string>>,
  language: string = i18next.language,
): string {
  return names[serverOf(language)] || names.ru;
}

export default i18next;

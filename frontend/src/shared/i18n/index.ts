/**
 * Языки интерфейса.
 *
 * Правило жёсткое: **ни одной строки текста в коде компонентов**, только ключи. Причина не
 * в переводе, а в том, что строка в коде — это строка, которую нельзя переписать без
 * разработчика, а формулировки заказчик правит на приёмке пакетом.
 *
 * Сейчас один язык — русский. Узбекская латиница и кириллица приезжают в блоке 3, и
 * приезжают файлами рядом: машинерия уже стоит, добавить язык — это добавить словарь.
 */

import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import { ru } from './ru';

export const DEFAULT_LOCALE = 'ru';

export const LOCALES = [{ code: 'ru', label: 'Русский' }] as const;

void i18next.use(initReactI18next).init({
  resources: { ru: { translation: ru } },
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  interpolation: { escapeValue: false },
  // Пропущенный ключ должен быть виден, а не выглядеть пустым местом: пустая графа на
  // экране читается как «данных нет», а это другое сообщение.
  parseMissingKeyHandler: (key) => `⟨${key}⟩`,
});

export default i18next;

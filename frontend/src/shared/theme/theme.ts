/**
 * Тема оформления: тёмная, светлая и «как в системе».
 *
 * Тёмная — основная ([ADR-0021](../../../../docs/adr/ADR-0021-cosmic-visual-layer.md)):
 * агентство космическое, и тёмное небо здесь родная среда, а не режим для работающих
 * после полуночи. Светлая нужна для печати, отчётов (ТЗ 6.7) и того, кто её выбрал.
 *
 * Состояний три, а не два. Тумблер без «системы» ломает телефон руководителя, который
 * переключается на тёмное по расписанию сам: он выбрал бы светлую днём и получил бы её
 * же ночью. Поэтому «система» — не отсутствие выбора, а полноценное третье состояние.
 *
 * Разрешение системной настройки делает этот модуль, а не CSS. Иначе светлую палитру
 * пришлось бы писать дважды — под `@media (prefers-color-scheme)` и под `[data-theme]`, —
 * а два списка из тридцати цветов расходятся на первой же правке.
 */

export const THEME_MODES = ['system', 'light', 'dark'] as const;

export type ThemeMode = (typeof THEME_MODES)[number];
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'orbita.theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

export function isThemeMode(value: unknown): value is ThemeMode {
  return typeof value === 'string' && (THEME_MODES as readonly string[]).includes(value);
}

/**
 * Что записано у этого человека на этом устройстве.
 *
 * Хранилище может быть недоступно: приватное окно, запрет на данные сайта. Это рабочее
 * состояние, а не отказ — возвращаем «систему» и продолжаем.
 */
export function readMode(): ThemeMode {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return isThemeMode(saved) ? saved : 'system';
  } catch {
    return 'system';
  }
}

export function writeMode(mode: ThemeMode): void {
  try {
    if (mode === 'system') {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, mode);
    }
  } catch {
    // Записать некуда — выбор живёт до перезагрузки. Молчим: сообщать человеку, что
    // его браузер не хранит данные сайта, здесь нечем помочь.
  }
}

export function prefersDark(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_QUERY).matches;
}

export function resolve(mode: ThemeMode): ResolvedTheme {
  if (mode === 'light' || mode === 'dark') return mode;
  return prefersDark() ? 'dark' : 'light';
}

/** Ставит атрибут, по которому CSS выбирает палитру. Тот же атрибут ставит встроенный
 *  скрипт в `index.html` до первой отрисовки — иначе на тёмном экране видна светлая
 *  вспышка. */
export function apply(theme: ResolvedTheme): void {
  document.documentElement.setAttribute('data-theme', theme);
}

/**
 * Подписка на смену системной настройки.
 *
 * Нужна только в состоянии «система»: человек переключил телефон на тёмное по
 * расписанию, страница при этом открыта. Возвращает отписку.
 */
export function watchSystem(onChange: (theme: ResolvedTheme) => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => {};
  const query = window.matchMedia(DARK_QUERY);
  const handler = (event: MediaQueryListEvent) => onChange(event.matches ? 'dark' : 'light');
  query.addEventListener('change', handler);
  return () => query.removeEventListener('change', handler);
}

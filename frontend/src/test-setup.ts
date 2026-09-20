/**
 * Подготовка окружения для vitest.
 *
 * `matchMedia` в jsdom нет, а на нём стоят и тема, и выбор устройства. Без заглушки падал бы
 * каждый тест оболочки — и падал бы с ошибкой про matchMedia, а не про то, что проверялось.
 */

import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

interface MediaState {
  /** Ширина окна, по которой отвечают запросы `max-width` и `min-width`. */
  width: number;
  /** Отвечает ли система «предпочитаю тёмное». */
  prefersDark: boolean;
  /** Просил ли человек меньше движения. */
  reducedMotion: boolean;
}

const state: MediaState = { width: 1440, prefersDark: false, reducedMotion: false };

/** Задать «устройство» для теста: ширина, тема системы, предпочтение движения. */
export function setViewport(next: Partial<MediaState>): void {
  Object.assign(state, next);
  window.innerWidth = state.width;
  window.dispatchEvent(new Event('resize'));
}

function answer(query: string): boolean {
  const max = /max-width:\s*(\d+)px/.exec(query);
  if (max?.[1]) return state.width <= Number(max[1]);

  const min = /min-width:\s*(\d+)px/.exec(query);
  if (min?.[1]) return state.width >= Number(min[1]);

  if (query.includes('prefers-color-scheme: dark')) return state.prefersDark;
  if (query.includes('prefers-reduced-motion')) return state.reducedMotion;
  return false;
}

vi.stubGlobal(
  'matchMedia',
  (query: string) =>
    ({
      media: query,
      matches: answer(query),
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList,
);

afterEach(() => {
  cleanup();
  setViewport({ width: 1440, prefersDark: false, reducedMotion: false });
});

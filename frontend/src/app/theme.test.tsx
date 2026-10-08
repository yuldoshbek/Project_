/**
 * Тема «как в системе» следует за системой и при работающем приложении — вечером, по
 * расписанию телефона. Подписку на смену системной темы не проверял ни один тест, а при
 * переходе на правила React Compiler (eslint-plugin-react-hooks 7) она переписана.
 */

import { act, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { ThemeProvider } from './theme';

const original = window.matchMedia;

afterEach(() => {
  vi.stubGlobal('matchMedia', original);
});

it('режим «как в системе» переключает тему вслед за системой', () => {
  let dark = false;
  const listeners = new Set<() => void>();
  vi.stubGlobal(
    'matchMedia',
    (query: string) =>
      ({
        media: query,
        get matches() {
          return query.includes('prefers-color-scheme: dark') && dark;
        },
        addEventListener: (_: string, listener: () => void) => listeners.add(listener),
        removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
      }) as unknown as MediaQueryList,
  );
  localStorage.removeItem('orbita.theme');

  render(
    <ThemeProvider>
      <p>экран</p>
    </ThemeProvider>,
  );
  expect(document.documentElement.getAttribute('data-theme')).toBe('light');

  act(() => {
    dark = true;
    listeners.forEach((listener) => listener());
  });
  expect(document.documentElement.getAttribute('data-theme')).toBe('dim');
});

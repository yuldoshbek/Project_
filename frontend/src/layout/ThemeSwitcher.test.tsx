import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeSwitcher } from './ThemeSwitcher';

/**
 * jsdom не реализует matchMedia. Подменяем его целиком, потому что проверять надо
 * именно поведение при системной настройке: без подмены «система» всегда разрешалась
 * бы в светлую, и третье состояние осталось бы непроверенным.
 */
function mockSystem(dark: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: dark,
      media: query,
      addEventListener: (_: string, handler: (event: MediaQueryListEvent) => void) => {
        listeners.add(handler);
      },
      removeEventListener: (_: string, handler: (event: MediaQueryListEvent) => void) => {
        listeners.delete(handler);
      },
    })),
  );
  return {
    change(nowDark: boolean) {
      for (const handler of listeners) {
        handler({ matches: nowDark } as MediaQueryListEvent);
      }
    },
    get listenerCount() {
      return listeners.size;
    },
  };
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('переключатель темы', () => {
  it('по умолчанию следует за системой', () => {
    mockSystem(true);
    render(<ThemeSwitcher />);

    expect(screen.getByRole('combobox')).toHaveValue('system');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('светлая система даёт светлую тему, а не тёмную по умолчанию', () => {
    mockSystem(false);
    render(<ThemeSwitcher />);

    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('выбор человека сильнее системной настройки', async () => {
    mockSystem(true);
    const user = userEvent.setup();
    render(<ThemeSwitcher />);

    await user.selectOptions(screen.getByRole('combobox'), 'light');

    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem('orbita.theme')).toBe('light');
  });

  it('выбор переживает перезагрузку', () => {
    mockSystem(true);
    window.localStorage.setItem('orbita.theme', 'light');

    render(<ThemeSwitcher />);

    expect(screen.getByRole('combobox')).toHaveValue('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('в состоянии «система» следует за сменой настройки на открытой странице', () => {
    const system = mockSystem(false);
    render(<ThemeSwitcher />);
    expect(document.documentElement.dataset.theme).toBe('light');

    system.change(true);

    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('при выбранной теме за системой не следит: подписки нет', async () => {
    const system = mockSystem(false);
    const user = userEvent.setup();
    render(<ThemeSwitcher />);

    await user.selectOptions(screen.getByRole('combobox'), 'dark');

    expect(system.listenerCount).toBe(0);
    system.change(false);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('возврат к «системе» возвращает и слежение', async () => {
    const system = mockSystem(false);
    const user = userEvent.setup();
    render(<ThemeSwitcher />);

    const select = screen.getByRole('combobox');
    await user.selectOptions(select, 'dark');
    await user.selectOptions(select, 'system');

    expect(window.localStorage.getItem('orbita.theme')).toBeNull();
    expect(document.documentElement.dataset.theme).toBe('light');

    system.change(true);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('названия состояний переводятся, а сами значения — нет', () => {
    mockSystem(false);
    render(<ThemeSwitcher />);

    expect(screen.getByText('Тема')).toBeInTheDocument();
    for (const name of ['Как в системе', 'Светлая', 'Тёмная']) {
      expect(screen.getByRole('option', { name })).toBeInTheDocument();
    }

    // Значения остаются английскими: по ним CSS выбирает палитру, и перевод значения
    // сломал бы тему, а не подпись.
    const values = screen
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value);
    expect(values).toEqual(['system', 'light', 'dark']);
  });
});

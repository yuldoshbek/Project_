/**
 * Оболочка на трёх устройствах.
 *
 * Проверяется то, что ломается молча: на телефоне вместо нижней панели появляется боковая
 * полоса (и половина экрана уходит под навигацию), либо в панели оказывается шесть кнопок
 * вместо пяти — и цель нажатия становится меньше 44 px.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '@/app/theme';
import { PHONE_SECTIONS, SECTIONS } from '@/app/sections';
import { setViewport } from '@/test-setup';

import { AppShell } from './AppShell';

// Маршрутизатор в этих проверках не участвует: они про раскладку, а не про переходы.
// Ссылки подменены на обычные, чтобы падение здесь означало поломку оболочки, а не
// настройки маршрутов.
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useRouterState: () => '/',
}));

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <AppShell>
          <p>Содержимое раздела</p>
        </AppShell>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe('оболочка меняется вместе с устройством', () => {
  it('на телефоне навигация внизу, боковой полосы нет', () => {
    setViewport({ width: 390 });
    renderShell();

    const navigations = screen.getAllByRole('navigation');
    expect(navigations).toHaveLength(1);
    expect(screen.getByText('Содержимое раздела')).toBeInTheDocument();
  });

  it('в нижней панели пять разделов: шестая кнопка сделала бы цель нажатия меньше 44 px', () => {
    expect(PHONE_SECTIONS).toHaveLength(5);
  });

  it('на ноутбуке боковая полоса со всеми десятью разделами', () => {
    setViewport({ width: 1440 });
    renderShell();

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(SECTIONS.length);
  });

  it('на мониторе раскладка та же, что на ноутбуке, но шире', () => {
    setViewport({ width: 2560 });
    renderShell();

    expect(screen.getAllByRole('link')).toHaveLength(SECTIONS.length);
  });
});

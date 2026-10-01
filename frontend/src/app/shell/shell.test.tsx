/**
 * Оболочка на трёх устройствах.
 *
 * Проверяется то, что ломается молча: на телефоне вместо нижней панели появляется боковая
 * полоса (и половина экрана уходит под навигацию), либо в панели оказывается шесть мест
 * вместо пяти — и цель нажатия становится меньше 44 px. И Захват: он есть на каждом экране
 * (ТЗ 6, 7) — посередине нижней панели, кнопкой в верхней строке и клавишей «+»; лист держит
 * фокус внутри и возвращает его туда, откуда открыт.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '@/app/theme';
import { MORE_SECTIONS, PHONE_SECTIONS, SECTIONS } from '@/app/sections';
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

beforeEach(() => {
  // Захват спрашивает, кто вошёл; остальное оболочке не нужно.
  vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve({
      ok: false,
      status: 404,
      statusText: '',
      json: () => Promise.resolve({ detail: 'нет подмены' }),
    } as unknown as Response),
  );
});

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <AppShell>
          <p>Содержимое раздела</p>
          <input aria-label="Поле раздела" />
        </AppShell>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe('оболочка меняется вместе с устройством', () => {
  it('на телефоне навигация внизу: Пульт · Календарь · (+) · Поиск · Ещё', () => {
    setViewport({ width: 390 });
    renderShell();

    const navigations = screen.getAllByRole('navigation');
    expect(navigations).toHaveLength(1);
    const bar = within(navigations[0]!);
    expect(bar.getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Пульт',
      'Календарь',
    ]);
    expect(
      bar
        .getAllByRole('button')
        .map((button) => button.getAttribute('aria-label') ?? button.textContent),
    ).toEqual(['Захват', 'Поиск', 'Ещё']);
    expect(screen.getByText('Содержимое раздела')).toBeInTheDocument();
  });

  it('пять мест, не больше: шестое сделало бы цель нажатия меньше 44 px', () => {
    expect(PHONE_SECTIONS.map((section) => section.id)).toEqual(['pult', 'calendar']);
    expect(PHONE_SECTIONS.length + MORE_SECTIONS.length).toBe(SECTIONS.length);
  });

  it('«Ещё» — все остальные разделы, неготовые с номером блока', () => {
    setViewport({ width: 390 });
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Ещё' }));

    const sheet = screen.getByRole('dialog', { name: 'Все разделы' });
    expect(within(sheet).getAllByRole('link')).toHaveLength(MORE_SECTIONS.length);
    // «Ижро» и «Взаимодействие» уже открываются; их соседи по блоку 2 — ещё нет.
    expect(within(sheet).getByRole('link', { name: /Ижро/ })).not.toHaveTextContent('блок');
    expect(within(sheet).getByRole('link', { name: /Взаимодействие/ })).not.toHaveTextContent(
      'блок',
    );
    expect(within(sheet).getByRole('link', { name: /Доклады/ })).toHaveTextContent('блок 2');
  });

  it('«Поиск» честно говорит, что его нет в плане блоков (V19)', () => {
    setViewport({ width: 390 });
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Поиск' }));
    const sheet = screen.getByRole('dialog', { name: 'Поиск по всем разделам' });
    expect(within(sheet).getByText(/вопрос на приёмке блока 1 \(V19\)/)).toBeInTheDocument();
  });

  it('(+) открывает Захват', () => {
    setViewport({ width: 390 });
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Захват' }));
    expect(screen.getByRole('dialog', { name: 'Захват' })).toBeInTheDocument();
  });

  it('на ноутбуке боковая полоса со всеми десятью разделами и кнопка Захвата', () => {
    setViewport({ width: 1440 });
    renderShell();

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(SECTIONS.length);
    fireEvent.click(screen.getByRole('button', { name: /Захват/ }));
    expect(screen.getByRole('dialog', { name: 'Захват' })).toBeInTheDocument();
  });

  it('клавиша «+» открывает Захват, но не посреди набора текста', () => {
    setViewport({ width: 1440 });
    renderShell();

    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Поле раздела' }), { key: '+' });
    expect(screen.queryByRole('dialog', { name: 'Захват' })).not.toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: '+' });
    expect(screen.getByRole('dialog', { name: 'Захват' })).toBeInTheDocument();
  });

  it('клавиша «+» не открывает Захват поверх открытого листа', () => {
    setViewport({ width: 390 });
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Ещё' }));

    fireEvent.keyDown(document.body, { key: '+' });
    expect(screen.queryByRole('dialog', { name: 'Захват' })).not.toBeInTheDocument();
  });

  it('Escape закрывает Захват, и фокус возвращается на кнопку, которая его открыла', async () => {
    setViewport({ width: 1440 });
    renderShell();
    const open = screen.getByRole('button', { name: /Захват/ });
    open.focus();
    fireEvent.click(open);
    const sheet = screen.getByRole('dialog', { name: 'Захват' });
    expect(within(sheet).getByRole('textbox', { name: 'Текст записи' })).toHaveFocus();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Захват' })).not.toBeInTheDocument();
    await waitFor(() => expect(open).toHaveFocus());
  });

  it('Tab не уходит из открытого листа на экран за ним', () => {
    setViewport({ width: 390 });
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Ещё' }));
    const sheet = screen.getByRole('dialog', { name: 'Все разделы' });
    const close = within(sheet).getByRole('button', { name: 'Закрыть разделы' });
    const links = within(sheet).getAllByRole('link');
    const last = links.at(-1)!;

    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(close).toHaveFocus();

    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
  });

  it('на мониторе раскладка та же, что на ноутбуке, но шире', () => {
    setViewport({ width: 2560 });
    renderShell();

    expect(screen.getAllByRole('link')).toHaveLength(SECTIONS.length);
  });
});

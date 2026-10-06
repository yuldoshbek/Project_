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
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '@/app/theme';
import { MORE_SECTIONS, PHONE_SECTIONS, SECTIONS } from '@/app/sections';
import { applyLocale } from '@/shared/i18n';
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

describe('язык интерфейса', () => {
  // Словари — заранее: здесь проверяются меню, сохранение и откат, а загрузку куска словаря
  // проверяет `shared/i18n/i18n.test.ts`. Под нагрузкой параллельного прогона первая сборка
  // узбекского словаря занимала секунды, и проверка падала по времени, а не по сути.
  beforeAll(async () => {
    await applyLocale('uz_latn');
    await applyLocale('uz_cyrl');
    await applyLocale('ru');
  }, 30_000);

  afterEach(async () => {
    // Экран снимается до смены языка: иначе русский перерисовал бы его уже вне проверки.
    cleanup();
    await applyLocale('ru');
  });

  function reply(status: number, body?: unknown): Response {
    return {
      ok: status < 400,
      status,
      statusText: '',
      json: () => Promise.resolve(body),
    } as unknown as Response;
  }

  /**
   * Сервер с пользователем: `/api/me` отдаёт записанный язык, `PUT /api/me/locale` отвечает
   * `answer` и при успехе записывает язык — как настоящий API.
   */
  function server(locale: string, answer: () => Response) {
    let saved = locale;
    vi.mocked(globalThis.fetch).mockImplementation((url, init) => {
      if (String(url) === '/api/me/locale') {
        const response = answer();
        if (response.ok) saved = (JSON.parse(String(init?.body)) as { locale: string }).locale;
        return Promise.resolve(response);
      }
      if (String(url) === '/api/me') {
        return Promise.resolve(
          reply(200, {
            id: 'u-assistant',
            full_name: 'Помощник',
            role: 'assistant',
            locale: saved,
            timezone: 'Asia/Tashkent',
            can_write: true,
          }),
        );
      }
      return Promise.resolve(reply(404, { detail: 'нет подмены' }));
    });
  }

  const calls = () => vi.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url));

  it('выбор в меню переключает интерфейс сразу, сохраняет язык и перечитывает экран', async () => {
    server('ru', () => reply(204));
    setViewport({ width: 1440 });
    renderShell();
    await waitFor(() => expect(calls()).toContain('/api/me'));
    fireEvent.click(screen.getByRole('button', { name: /^Тема:/ }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Oʻzbekcha' }));

    expect(await screen.findByRole('link', { name: 'Loyihalar' })).toBeInTheDocument();
    const saved = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([url]) => String(url) === '/api/me/locale');
    expect(saved?.[1]?.method).toBe('PUT');
    expect(saved?.[1]?.body).toBe(JSON.stringify({ locale: 'uz_latn' }));
    // Названия справочников сервер отдаёт на языке пользователя: после сохранения
    // перечитываются все запросы, а не один `/api/me`, иначе экран остался бы наполовину
    // на прежнем языке.
    await waitFor(() => {
      const put = calls().indexOf('/api/me/locale');
      expect(calls().lastIndexOf('/api/me')).toBeGreaterThan(put);
      expect(calls().lastIndexOf('/api/health')).toBeGreaterThan(put);
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('сохранение не прошло — язык возвращается к записанному на сервере, и это сказано', async () => {
    server('uz_cyrl', () => reply(500, { detail: 'база недоступна' }));
    await applyLocale('uz_cyrl');
    setViewport({ width: 1440 });
    renderShell();
    await waitFor(() => expect(calls()).toContain('/api/me'));
    fireEvent.click(screen.getByRole('button', { name: /^Мавзу:/ }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Oʻzbekcha' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Тил алмашмади: база недоступна');
    expect(screen.getByRole('link', { name: 'Лойиҳалар' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Loyihalar' })).not.toBeInTheDocument();

    fireEvent.click(within(alert).getByRole('button', { name: 'Тушунарли' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

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

  it('«Ещё» — все остальные разделы, и каждый уже открывается', () => {
    setViewport({ width: 390 });
    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Ещё' }));

    const sheet = screen.getByRole('dialog', { name: 'Все разделы' });
    const links = within(sheet).getAllByRole('link');
    expect(links).toHaveLength(MORE_SECTIONS.length);
    // Номер блока подписывает только раздел без экрана; с блоком 3 таких не осталось.
    for (const link of links) expect(link).not.toHaveTextContent('блок');
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

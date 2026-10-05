/**
 * Идеи и карты — обещания экрана.
 *
 * «Что ждёт моего „да“?» — ответ числом, старшая идея и действие; руководитель решает идею в
 * проект одним действием, и идея показывает выросший проект (критерий 1 блока 3); помощник
 * не решает, а отправляет на рассмотрение; карта — полотно на ноутбуке и контур на телефоне.
 *
 * Сеть подменена на уровне `fetch`: `/api/v1/ideas…` и `/api/v1/maps…` отвечает сервер в
 * памяти (`test-server.ts`), сессию — заготовка.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { IdeasSection } from './IdeasSection';
import { FakeIdeas, handle } from './test-server';

let search: Record<string, unknown> = {};

vi.mock('@tanstack/react-router', async () => {
  const { useSyncExternalStore } = await import('react');
  const listeners = new Set<() => void>();
  return {
    useSearch: () =>
      useSyncExternalStore(
        (notify) => {
          listeners.add(notify);
          return () => listeners.delete(notify);
        },
        () => search,
      ),
    useNavigate: () => (options: { search: Record<string, unknown> }) => {
      search = options.search;
      listeners.forEach((notify) => notify());
      return Promise.resolve();
    },
  };
});

function user(role: 'assistant' | 'leader'): CurrentUser {
  return {
    id: `u-${role}`,
    full_name: role,
    role,
    locale: 'ru',
    timezone: 'Asia/Tashkent',
    can_write: role === 'assistant',
  };
}

function reply(status: number, body: unknown): Response {
  return {
    ok: status < 400,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

let server = new FakeIdeas();

function serve(role: 'assistant' | 'leader') {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const body = init?.body
      ? (JSON.parse(String(init.body)) as Record<string, unknown>)
      : undefined;
    const answer = handle(server, method, path, body, role);
    if (answer) return Promise.resolve(reply(answer[0], answer[1]));
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IdeasSection />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  server = new FakeIdeas();
  search = {};
});

describe('Идеи и карты', () => {
  it('«Что ждёт моего „да“?» — сколько и сколько ждёт старшая', async () => {
    serve('leader');
    renderSection();

    expect(await screen.findByText('2 идеи ждут вашего «да»')).toBeVisible();
    expect(screen.getByText('дольше всех — 9 дней')).toBeVisible();
    const waiting = screen.getByRole('region', { name: 'На рассмотрении' });
    const rows = within(waiting).getAllByRole('listitem');
    // Дольше всех ждущая — первой.
    expect(rows[0]).toHaveTextContent('Открытый каталог снимков для вузов');
  });

  it('руководитель решает старшую идею в проект одним действием', async () => {
    serve('leader');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Решить старшую' }));
    const sheet = await screen.findByRole('dialog', { name: 'Решение по идее' });
    expect(within(sheet).getByText('Открытый каталог снимков для вузов')).toBeVisible();
    fireEvent.click(within(sheet).getByRole('button', { name: 'В проект' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText('1 идея ждёт вашего «да»')).toBeVisible();
    const decided = screen.getByRole('region', { name: 'Решено' });
    expect(within(decided).getByText(/Проект PR-0\d+ · Открытый каталог/)).toBeVisible();
  });

  it('помощник не решает, а отправляет набросок на рассмотрение', async () => {
    serve('assistant');
    renderSection();

    expect(await screen.findByRole('button', { name: 'Показать' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Решить' })).toBeNull();
    const drafts = screen.getByRole('region', { name: 'Наброски' });
    fireEvent.click(within(drafts).getByRole('button', { name: 'На рассмотрение' }));

    expect(await screen.findByText('3 идеи ждут вашего «да»')).toBeVisible();
  });

  it('новая идея записывается наброском', async () => {
    serve('leader');
    renderSection();

    fireEvent.change(await screen.findByLabelText('Идея'), {
      target: { value: 'Снимки для учебников географии' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));

    const drafts = screen.getByRole('region', { name: 'Наброски' });
    expect(await within(drafts).findByText('Снимки для учебников географии')).toBeVisible();
  });

  it('ноутбук: полотно карты — узел добавляется под выбранным и превращается в задачу', async () => {
    setViewport({ width: 1440 });
    search = { view: 'maps' };
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: /Мониторинг сельского хозяйства/ }));
    const canvas = await screen.findByRole('region', { name: 'Полотно карты' });
    // Структура: связанный узел показывает ступень Пульта, несвязанный — «не связан».
    expect(within(canvas).getByText('Просрочено')).toBeVisible();
    expect(within(canvas).getAllByText('не связан')).toHaveLength(2);

    fireEvent.click(within(canvas).getByRole('button', { name: 'Пастбища' }));
    fireEvent.change(screen.getByLabelText('Новый узел под «Пастбища»'), {
      target: { value: 'Пилот на весну' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить узел' }));
    expect(await within(canvas).findByRole('button', { name: 'Пилот на весну' })).toBeVisible();

    const panel = screen.getByRole('region', { name: 'Узел' });
    fireEvent.click(within(panel).getByRole('button', { name: 'В задачу' }));
    expect(await within(panel).findByText(/Задача Т-099/)).toBeVisible();
  });

  it('телефон: карта — контур, без полотна', async () => {
    setViewport({ width: 390 });
    search = { view: 'maps', map: 'm-agro' };
    serve('leader');
    renderSection();

    const outline = await screen.findByRole('region', { name: 'Контур карты' });
    expect(within(outline).getByText('Засуха')).toBeVisible();
    expect(within(outline).getByText('PR-003')).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Полотно карты' })).toBeNull();
  });
});

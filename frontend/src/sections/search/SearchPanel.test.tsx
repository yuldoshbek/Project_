/**
 * Панель поиска: запрос после паузы набора, находки по разделам, переход к карточке.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SearchView } from './model';
import SearchPanel from './SearchPanel';

const navigate = vi.hoisted(() => vi.fn(() => Promise.resolve()));
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }));

const FOUND: SearchView = {
  query: 'kosmik',
  groups: [
    {
      kind: 'ijro',
      hits: [
        {
          id: 'a-1',
          title: 'Космик мониторинг маълумотлари асосида',
          code: 'IJR-2026-001',
          context: 'ПҚ-312',
        },
      ],
      more: false,
    },
    {
      kind: 'project',
      hits: [{ id: 'p-1', title: 'Космик сурат архиви', code: 'PRJ-2026-004', context: null }],
      more: true,
    },
  ],
};

function serve(answer: (query: string) => SearchView) {
  const asked: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = new URL(String(input), 'http://localhost');
    const query = url.searchParams.get('q') ?? '';
    asked.push(query);
    return Promise.resolve(
      new Response(JSON.stringify(answer(query)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
  return asked;
}

function renderPanel() {
  const onPick = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SearchPanel onPick={onPick} />
    </QueryClientProvider>,
  );
  return onPick;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  navigate.mockClear();
});

describe('поиск по всем разделам', () => {
  it('находки по разделам; касание открывает карточку в её разделе и закрывает панель', async () => {
    const asked = serve(() => FOUND);
    const onPick = renderPanel();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Что найти' }), {
      target: { value: 'kosmik' },
    });

    expect(await screen.findByText('Поручения Ижро')).toBeInTheDocument();
    expect(screen.getByText('IJR-2026-001 · ПҚ-312')).toBeInTheDocument();
    expect(screen.getByText('Есть ещё — уточните запрос.')).toBeInTheDocument();
    expect(asked).toEqual(['kosmik']);

    fireEvent.click(screen.getByRole('button', { name: /Космик мониторинг/ }));

    expect(navigate).toHaveBeenCalledWith({
      to: '/ijro',
      search: { view: 'assignments', open: 'a-1' },
    });
    expect(onPick).toHaveBeenCalledTimes(1);
  });

  it('«Ввод» открывает первую находку', async () => {
    serve(() => FOUND);
    renderPanel();
    const field = screen.getByRole('searchbox', { name: 'Что найти' });

    fireEvent.change(field, { target: { value: 'kosmik' } });
    await screen.findByText('Поручения Ижро');
    fireEvent.submit(field);

    expect(navigate).toHaveBeenCalledWith({
      to: '/ijro',
      search: { view: 'assignments', open: 'a-1' },
    });
  });

  it('пусто — фразой с запросом, а не пустым местом', async () => {
    serve((query) => ({ query, groups: [] }));
    renderPanel();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Что найти' }), {
      target: { value: 'луна' },
    });

    expect(await screen.findByText('По запросу «луна» ничего не нашлось.')).toBeInTheDocument();
  });

  it('одна буква не ищется — подсказка, что и как искать', async () => {
    const asked = serve(() => FOUND);
    renderPanel();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Что найти' }), {
      target: { value: 'к' },
    });

    // Пауза набора прошла, а запроса нет.
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    await waitFor(() => expect(screen.getByText(/по части названия или номера/)).toBeVisible());
    expect(asked).toEqual([]);
  });
});

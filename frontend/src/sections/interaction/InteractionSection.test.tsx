/**
 * Взаимодействие — обещания экрана на утверждение.
 *
 * Четыре вопроса с датой данных и действием; действие открывает те же письма, что посчитаны в
 * ответе; на телефоне — список, не таблица; скорость ответа — только при пяти письмах, иначе
 * словами; руководитель оценивает ответ одним касанием; помощник отмечает ответ и вносит
 * письмо; «спящие» соглашения будит следующий шаг; карточка организации собирает всё.
 *
 * Данные раздела — вымышленный сервер `demo.ts`; сеть (сессия) подменена на уровне `fetch`.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { demoInteraction } from './demo';
import { InteractionSection } from './InteractionSection';

const route = vi.hoisted(() => {
  let search: Record<string, unknown> = {};
  const listeners = new Set<() => void>();
  return {
    get: () => search,
    set: (next: Record<string, unknown>) => {
      search = next;
      listeners.forEach((listener) => listener());
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
});

vi.mock('@tanstack/react-router', async () => {
  const { useSyncExternalStore } = await import('react');
  return {
    useSearch: () => useSyncExternalStore(route.subscribe, route.get),
    useNavigate: () => (options: { search: Record<string, unknown> }) => {
      route.set(options.search);
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

function serve(role: 'assistant' | 'leader') {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const found = path === '/api/me';
    return Promise.resolve({
      ok: found,
      status: found ? 200 : 404,
      statusText: '',
      json: () => Promise.resolve(found ? user(role) : { detail: `нет подмены ${path}` }),
    } as unknown as Response);
  });
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <InteractionSection />
    </QueryClientProvider>,
  );
}

function tableRows() {
  return screen.getAllByRole('row').slice(1);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  route.set({});
  demoInteraction.reset();
});

describe('Взаимодействие', () => {
  it('четыре вопроса, у каждого дата данных и ответ словами', async () => {
    serve('leader');
    renderSection();

    expect(await screen.findByRole('heading', { name: 'Кто нам не отвечает?' })).toBeVisible();
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getAllByRole('heading', { level: 2 })).toHaveLength(4);
    expect(within(panel).getAllByText(/^данные на /)).toHaveLength(4);
    expect(screen.getByText('без ответа писем: 5 · организаций: 4')).toBeVisible();
  });

  it('«Кому напомнить» открывает те же письма, что посчитаны в ответе', async () => {
    serve('leader');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Кому напомнить' }));

    expect(screen.getByRole('tab', { name: 'Письма' })).toHaveAttribute('aria-selected', 'true');
    expect(tableRows()).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: 'Убрать отбор: Кто нам не отвечает?' }));
    expect(tableRows().length).toBeGreaterThan(5);
  });

  it('на телефоне — список писем, таблицы нет (ТЗ 6)', async () => {
    setViewport({ width: 390 });
    route.set({ view: 'letters' });
    serve('leader');
    renderSection();

    expect(
      await screen.findByText('О согласовании «дорожной карты» навигационных услуг'),
    ).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('скорость — медианой при пяти письмах, остальные словами (критерий 4 блока)', async () => {
    route.set({ view: 'organizations' });
    serve('leader');
    renderSection();

    expect(await screen.findByText(/отвечают за 25 дн/)).toBeVisible();
    expect(screen.getAllByText(/мало писем \(1\)/).length).toBeGreaterThan(0);
  });

  it('руководитель оценивает полученный ответ одним касанием', async () => {
    route.set({ view: 'letters' });
    serve('leader');
    renderSection();

    fireEvent.click(
      await screen.findByRole('button', { name: 'О совместной рабочей группе по мониторингу' }),
    );
    const card = await screen.findByRole('dialog', { name: 'Карточка письма' });
    const formal = within(card).getByRole('button', { name: 'формально' });
    expect(formal).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(formal);
    await waitFor(() =>
      expect(within(card).getByRole('button', { name: 'формально' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
    expect(within(card).queryByRole('button', { name: 'Ответ получен' })).not.toBeInTheDocument();
  });

  it('помощник отмечает ответ — письмо уходит из «кто не отвечает»', async () => {
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Кому напомнить' }));
    expect(tableRows()).toHaveLength(5);
    fireEvent.click(
      screen.getByRole('button', { name: 'О согласовании «дорожной карты» навигационных услуг' }),
    );
    const card = await screen.findByRole('dialog', { name: 'Карточка письма' });
    fireEvent.click(within(card).getByRole('button', { name: 'Ответ получен' }));

    await waitFor(() => expect(tableRows()).toHaveLength(4));
  });

  it('помощник вносит письмо — оно в списке', async () => {
    route.set({ view: 'letters' });
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Новое письмо' }));
    fireEvent.change(screen.getByLabelText('Тема'), {
      target: { value: 'О данных для отчёта по засухе' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Внести' }));

    expect(await screen.findByText('О данных для отчёта по засухе')).toBeVisible();
  });

  it('руководитель письма не вносит и ответ не отмечает', async () => {
    route.set({ view: 'letters' });
    serve('leader');
    renderSection();

    expect(
      await screen.findByText('О согласовании «дорожной карты» навигационных услуг'),
    ).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Новое письмо' })).not.toBeInTheDocument(),
    );
  });

  it('спящие соглашения: действие вопроса — отбор, следующий шаг будит', async () => {
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Назначить следующий шаг' }));
    expect(screen.getByRole('tab', { name: 'Соглашения' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getAllByText('Спит')).toHaveLength(2);

    fireEvent.click(screen.getAllByRole('button', { name: 'Изменить шаг' })[0]!);
    fireEvent.change(screen.getByLabelText('Следующий шаг'), {
      target: { value: 'Созвониться и назначить встречу' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(screen.getAllByText('Спит')).toHaveLength(1));
  });

  it('карточка организации собирает письма, соглашения, поручения и проекты', async () => {
    route.set({ view: 'organizations' });
    serve('leader');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: /^Минэкологии/ }));
    const card = await screen.findByRole('dialog', { name: 'Карточка организации' });
    expect(await within(card).findByText('медиана 10 дн по 6 письмам')).toBeVisible();
    expect(within(card).getByText('Меморандум о мониторинге водных ресурсов')).toBeVisible();
    expect(within(card).getByText('ПҚ-312 · 2-банд')).toBeVisible();
    expect(within(card).getByText('Геоданные для мониторинга засухи')).toBeVisible();
  });
});

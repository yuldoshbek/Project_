/**
 * Доклады и мероприятия — обещания экрана.
 *
 * «Готовы ли к дате и кто задерживает?» — ответ фразой и действие; у подготовки видно, каких
 * сведений не хватает и кто задерживает, напоминание готовится кнопкой (критерий 5 блока 2);
 * полученные сведения снимают задержку; руководитель не правит, помощник заводит подготовку.
 *
 * Сеть подменена на уровне `fetch`: `/api/v1/preparations…` отвечает сервер в памяти
 * (`test-server.ts`), сессию — заготовка.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';

import { ReportsSection } from './ReportsSection';
import { FakeReports, handle } from './test-server';

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

let server = new FakeReports();

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
      <ReportsSection />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  server = new FakeReports();
});

describe('Доклады и мероприятия', () => {
  it('«Готовы ли к дате?» — кто задерживает и на сколько', async () => {
    serve('leader');
    renderSection();

    expect(
      await screen.findByText(
        '«Об итогах космического мониторинга засухи» — не хватает 2 сведений',
      ),
    ).toBeVisible();
    expect(screen.getAllByText(/Министерство экологии задерживает 4 дн/).length).toBeGreaterThan(0);
  });

  it('карточка: напоминание тому, кто задерживает, копируется кнопкой', async () => {
    serve('leader');
    const writeText = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Открыть подготовку' }));
    const card = await screen.findByRole('dialog', { name: 'Карточка подготовки' });
    const reminders = await within(card).findAllByRole('button', { name: 'Напомнить' });
    fireEvent.click(reminders[0]!);

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const calls = writeText.mock.calls as unknown as string[][];
    expect(calls[0]?.[0]).toContain('Данные о засухе');
    expect(await within(card).findByRole('status')).toHaveTextContent('скопирован');
    // Руководитель не правит подготовку: кнопок «Получено» у него нет.
    expect(within(card).queryByRole('button', { name: 'Получено' })).not.toBeInTheDocument();
  });

  it('помощник отмечает «получено» — задержка уходит', async () => {
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Открыть подготовку' }));
    const card = await screen.findByRole('dialog', { name: 'Карточка подготовки' });
    expect(await within(card).findAllByRole('button', { name: 'Напомнить' })).toHaveLength(2);

    fireEvent.click(within(card).getAllByRole('button', { name: 'Получено' })[0]!);

    await waitFor(() =>
      expect(within(card).getAllByRole('button', { name: 'Напомнить' })).toHaveLength(1),
    );
  });

  it('помощник заводит подготовку — она в списке', async () => {
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Новая подготовка' }));
    fireEvent.change(screen.getByLabelText('Название'), {
      target: { value: 'О готовности наземной станции' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Завести' }));

    expect(await screen.findByText('О готовности наземной станции')).toBeVisible();
  });

  it('«Что пора начинать готовить?» показывает те же подготовки', async () => {
    serve('leader');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Показать' }));

    expect(screen.getByText('по вопросу: 1')).toBeVisible();
    expect(screen.getByText('О ходе программы спутниковой группировки')).toBeVisible();
    expect(screen.queryByText('Ежеквартальная справка для Администрации Президента')).toBeNull();
  });
});

/**
 * Экран Пульта против ответа API: решение, отмена, вопрос помощника, фильтры.
 *
 * Порядок лестницы и счётчики считает сервер, и проверяются они там (`backend/tests/
 * test_pult.py`, `test_attention.py`). Здесь — что экран делает с ответом: какие кнопки
 * видит руководитель и помощник, что уходит на сервер по касанию и что делает «Отменить».
 * Сеть подменена на уровне `fetch`, как в тесте «Управления».
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';

import type { PultRow, PultView, ReportView } from './model';
import { PultSection } from './PultSection';

const KARIMOV = { id: 'p-karimov', name: 'Каримов А.' };
const TURSUNOV = { id: 'p-tursunov', name: 'Турсунов Б.' };

function row(overrides: Partial<PultRow>): PultRow {
  return {
    section: 'projects',
    entity_id: 'e-1',
    title: 'Строка',
    decision_kind: null,
    target_type: 'project',
    target_id: 'e-1',
    context: null,
    step: 'overdue',
    deviation: 3,
    due_on: '2026-09-22',
    original_due_on: '2026-09-22',
    responsible: KARIMOV,
    question: null,
    last_decision: null,
    ...overrides,
  };
}

const VIEW: PultView = {
  as_of: '2026-09-25T12:00:00Z',
  last_visit_at: '2026-09-24T18:40:00Z',
  rows: [
    row({
      section: 'milestones',
      entity_id: 'm-1',
      target_type: 'milestone',
      target_id: 'm-1',
      title: 'Согласование ТЗ',
      context: 'Спутниковая миссия',
      step: 'awaiting_decision',
      deviation: 6,
      question: { id: 'q-1', text: 'Утвердить перенос вехи?', asked_on: '2026-09-19' },
    }),
    row({ entity_id: 'p-2', target_id: 'p-2', title: 'Справка для Кабмина' }),
    row({
      section: 'decisions',
      entity_id: 'd-1',
      target_type: 'task',
      target_id: 't-9',
      title: null,
      decision_kind: 'hurry',
      responsible: TURSUNOV,
      deviation: 1,
    }),
  ],
  counts: { awaiting_decision: 1, overdue: 2, burning: 0, blocked_by_others: 0, silent: 0 },
  on_track: 21,
  holders: [
    {
      person: KARIMOV,
      counts: { awaiting_decision: 1, overdue: 1, burning: 0, blocked_by_others: 0, silent: 0 },
      total: 2,
      worst: 'awaiting_decision',
    },
    {
      person: TURSUNOV,
      counts: { awaiting_decision: 0, overdue: 1, burning: 0, blocked_by_others: 0, silent: 0 },
      total: 1,
      worst: 'overdue',
    },
  ],
  changes: [
    {
      kind: 'deadline_moved',
      section: 'milestones',
      entity_id: 'm-2',
      title: 'Приёмка платформы',
      at: '2026-09-25T09:00:00Z',
      moved: { from: '2026-09-09', to: '2026-09-16' },
    },
  ],
  deadline_moves: { period_days: 30, moves: 1, total_shift_days: 7, items: [] },
  is_demo: true,
};

function report(period: 'week' | 'month'): ReportView {
  return {
    period,
    start: period === 'week' ? '2026-09-21' : '2026-09-01',
    end: period === 'week' ? '2026-09-27' : '2026-09-30',
    generated_at: '2026-09-25T12:00:00Z',
    totals: {
      created_projects: 2,
      created_tasks: 5,
      closed_tasks: 7,
      closed_projects: 1,
      passed_milestones: 3,
      decisions_made: 4,
      decisions_done: 2,
      moves: 1,
      shift_days: 7,
    },
    counts: VIEW.counts,
    on_track: VIEW.on_track,
    rows: VIEW.rows,
    more_rows: 0,
    holders: VIEW.holders,
    decisions: [
      {
        kind: 'hurry',
        title: 'Справка для Кабмина',
        decided_on: '2026-09-23',
        state: 'open',
        done_on: null,
      },
    ],
    deadline_moves: VIEW.deadline_moves,
    is_demo: true,
  };
}

function user(role: 'leader' | 'assistant'): CurrentUser {
  return {
    id: `u-${role}`,
    full_name: role,
    role,
    locale: 'ru',
    timezone: 'Asia/Tashkent',
    can_write: role === 'assistant',
  };
}

function reply(status: number, body?: unknown): Response {
  return {
    ok: status < 400,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/** Подменить сеть. Возвращает список запросов, чтобы проверить, что ушло на сервер. */
function serve(role: 'leader' | 'assistant') {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (path === '/api/v1/pult') return Promise.resolve(reply(200, VIEW));
    if (path.startsWith('/api/v1/pult/report')) {
      return Promise.resolve(reply(200, report(path.includes('period=month') ? 'month' : 'week')));
    }
    if (method === 'POST') return Promise.resolve(reply(201, { id: 'created-1' }));
    if (method === 'DELETE') return Promise.resolve(reply(204));
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
  return calls;
}

function renderPult() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PultSection />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('Пульт', () => {
  it('говорит, что данные вымышленные, пока это не рабочий контур', async () => {
    serve('leader');
    renderPult();
    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
  });

  it('решение уходит на сервер по объекту строки, «Отменить» удаляет именно его', async () => {
    const calls = serve('leader');
    renderPult();
    await screen.findByText('Согласование ТЗ');

    fireEvent.click((await screen.findAllByRole('button', { name: 'Утвердить' }))[0]!);

    await waitFor(() => expect(screen.getByRole('button', { name: 'Отменить' })).toBeVisible());
    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/v1/decisions',
      body: { target_type: 'milestone', target_id: 'm-1', kind: 'approve' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Отменить' }));
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'DELETE',
        path: '/api/v1/decisions/created-1',
        body: undefined,
      }),
    );
  });

  it('строка-решение торопит работу, а не само решение', async () => {
    const calls = serve('leader');
    renderPult();
    await screen.findByText('Согласование ТЗ');

    // Решение без текста подписано своим видом: пустая строка читалась бы как «данных нет».
    const buttons = await screen.findAllByRole('button', { name: 'Поторопить' });
    expect(screen.getAllByText('Поторопить').length).toBeGreaterThan(buttons.length);
    fireEvent.click(buttons[buttons.length - 1]!);

    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'POST',
        path: '/api/v1/decisions',
        body: { target_type: 'task', target_id: 't-9', kind: 'hurry' },
      }),
    );
  });

  it('помощник не видит кнопок решения — только «Спросить»', async () => {
    serve('assistant');
    renderPult();
    await screen.findByText('Согласование ТЗ');

    expect(screen.queryByRole('button', { name: 'Утвердить' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Спросить' }).length).toBeGreaterThan(0);
  });

  it('касание человека в «Кто держит» оставляет только его строки', async () => {
    serve('leader');
    renderPult();
    await screen.findByText('Согласование ТЗ');

    fireEvent.click(screen.getByRole('button', { name: 'Показать строки: Турсунов Б.' }));

    expect(screen.getByText('Показано: Турсунов Б.')).toBeInTheDocument();
    expect(screen.queryByText('Согласование ТЗ')).not.toBeInTheDocument();
  });

  it('счётчик ступени — фильтр лестницы', async () => {
    serve('leader');
    renderPult();
    await screen.findByText('Согласование ТЗ');

    fireEvent.click(screen.getByRole('button', { name: 'Показать только: Ждёт решения' }));

    expect(screen.getByText('Согласование ТЗ')).toBeInTheDocument();
    expect(screen.queryByText('Справка для Кабмина')).not.toBeInTheDocument();
  });

  it('перенос срока «с прошлого визита» — было → стало', async () => {
    serve('leader');
    renderPult();
    expect(await screen.findByText('Срок 09.09.2026 → 16.09.2026')).toBeInTheDocument();
  });

  it('отчёт — вкладка Пульта: неделя по умолчанию, месяц по кнопке', async () => {
    const calls = serve('leader');
    renderPult();
    await screen.findByText('Согласование ТЗ');

    fireEvent.click(screen.getByRole('tab', { name: 'Отчёт' }));

    expect(await screen.findByText('Отчёт за неделю 21.09.2026 — 27.09.2026')).toBeInTheDocument();
    const closed = screen.getByText('закрыто задач').parentElement!;
    expect(within(closed).getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Поторопить: Справка для Кабмина')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Месяц' }));

    expect(await screen.findByText('Отчёт за месяц 01.09.2026 — 30.09.2026')).toBeInTheDocument();
    expect(calls.map((call) => call.path)).toContain('/api/v1/pult/report?period=month&offset=0');
  });
});

/**
 * Экран Пульта против ответа API: решение, отмена, вопрос помощника, фильтры.
 *
 * Порядок лестницы и счётчики считает сервер, и проверяются они там (`backend/tests/
 * test_pult.py`, `test_attention.py`). Здесь — что экран делает с ответом: какие кнопки
 * видит руководитель и помощник, что уходит на сервер по касанию и что делает «Отменить».
 * Сеть подменена на уровне `fetch`, как в тесте «Управления».
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import type { PultRow, PultView, ReportView } from './model';
import { PultSection } from './PultSection';
import { demoDevice } from './summary-demo';

/** Что подменяет `pushCapable`: в jsdom ни уведомлений, ни service worker нет. */
const PUSH_STUBS: [object, string][] = [
  [window, 'Notification'],
  [window, 'PushManager'],
  [navigator, 'serviceWorker'],
];

/**
 * Адрес вместо маршрутизатора: вкладка Пульта живёт в `?view=`, и сюда ведёт касание утренней
 * сводки. Подмена хранит строку поиска и перерисовывает экран, когда её меняют.
 */
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

/**
 * Подменить сеть. Возвращает список запросов, чтобы проверить, что ушло на сервер.
 *
 * `sendAt` — порог «Утренняя сводка» в ответе Управления. `fresh` — как настоящий сервер:
 * у каждого ответа Пульта своё `as_of`.
 */
function serve(
  role: 'leader' | 'assistant',
  view: PultView = VIEW,
  { sendAt = '08:30', fresh = false }: { sendAt?: string; fresh?: boolean } = {},
) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  let answered = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (path === '/api/v1/pult') {
      answered += 1;
      const as_of = fresh ? `2026-09-25T12:00:${String(answered).padStart(2, '0')}Z` : view.as_of;
      return Promise.resolve(reply(200, { ...view, as_of }));
    }
    if (path === '/api/v1/management') {
      return Promise.resolve(reply(200, { thresholds: [{ key: 'summary_at', value: sendAt }] }));
    }
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
  render(
    <QueryClientProvider client={client}>
      <PultSection />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(() => {
  // Сначала снять экран: сброс адреса ниже перерисовал бы смонтированный Пульт вне `act`.
  cleanup();
  vi.restoreAllMocks();
  // Не `vi.unstubAllGlobals()`: он снял бы и `matchMedia` общей подготовки (`test-setup.ts`).
  for (const [target, key] of PUSH_STUBS) Reflect.deleteProperty(target, key);
  route.set({});
  demoDevice.reset();
});

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

/** Пульт с одним сроком сегодня: строка «горит» с нулём дней до срока. */
const WITH_DUE: PultView = {
  ...VIEW,
  rows: [
    ...VIEW.rows,
    row({
      section: 'tasks',
      entity_id: 't-5',
      target_type: 'task',
      target_id: 't-5',
      title: 'Выгрузка данных в субплатформу',
      step: 'burning',
      deviation: 0,
      due_on: '2026-09-25',
    }),
    row({
      section: 'tasks',
      entity_id: 't-6',
      target_type: 'task',
      target_id: 't-6',
      title: 'Справка к совещанию',
      step: 'burning',
      deviation: 3,
    }),
  ],
};

/** Устройство, на котором уведомления можно включить: как Chrome на ноутбуке. */
function pushCapable(permission: NotificationPermission = 'default') {
  const values = [{ permission }, function PushManager() {}, {}];
  PUSH_STUBS.forEach(([target, key], index) =>
    Object.defineProperty(target, key, { value: values[index], configurable: true }),
  );
}

describe('утренняя сводка', () => {
  it('касание уведомления открывает вкладку: вид на экране блокировки и два пункта', async () => {
    route.set({ view: 'summary' });
    serve('leader', WITH_DUE);
    renderPult();

    expect(await screen.findByRole('tab', { name: 'Сводка' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      await screen.findByText('Ждут решения: 1, дольше всех — «Согласование ТЗ», 6 дн.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Срок сегодня: «Выгрузка данных в субплатформу».')).toBeInTheDocument();

    const awaiting = screen.getByRole('heading', { name: 'Ждут решения' }).closest('section')!;
    expect(within(awaiting).getByText('Согласование ТЗ')).toBeInTheDocument();
    expect(awaiting).toHaveTextContent('дольше всех: ждёт 6 дн');
    const due = screen.getByRole('heading', { name: 'Срок сегодня' }).closest('section')!;
    expect(within(due).getByText('Выгрузка данных в субплатформу')).toBeInTheDocument();
    // «Горит» через три дня — не сегодня (V26): его место на Пульте, а не в сводке.
    expect(screen.queryByText('Справка к совещанию')).not.toBeInTheDocument();
  });

  it('решение из сводки — то же касание, что на Пульте, с «Отменить»', async () => {
    route.set({ view: 'summary' });
    const calls = serve('leader', WITH_DUE);
    renderPult();

    const awaiting = (await screen.findByRole('heading', { name: 'Ждут решения' })).closest(
      'section',
    )!;
    fireEvent.click(within(awaiting).getByRole('button', { name: 'Утвердить' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Отменить' })).toBeVisible());
    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/v1/decisions',
      body: { target_type: 'milestone', target_id: 'm-1', kind: 'approve' },
    });
  });

  it('пустая сводка — фразы, а не нули и не «спокойно»', async () => {
    route.set({ view: 'summary' });
    // Просроченное в Пульте остаётся, в сводку оно не входит (V26): «спокойно» было бы
    // неправдой.
    serve('leader', {
      ...VIEW,
      rows: VIEW.rows.filter((each) => each.step !== 'awaiting_decision'),
    });
    renderPult();

    // Одна фраза — на экране блокировки, вторая — в пункте под ним.
    expect(await screen.findAllByText('Решений не ждёт.')).toHaveLength(2);
    expect(screen.getAllByText('Сроков сегодня нет.')).toHaveLength(2);
    expect(screen.queryByText(/спокойно/)).not.toBeInTheDocument();
  });

  it('решение без текста на экране блокировки названо вместе со своим объектом', async () => {
    route.set({ view: 'summary' });
    serve('leader', {
      ...VIEW,
      rows: [
        row({
          section: 'decisions',
          entity_id: 'd-2',
          target_type: 'task',
          target_id: 't-2',
          title: null,
          decision_kind: 'hurry',
          context: 'Справка для Кабмина',
          step: 'burning',
          deviation: 0,
          due_on: '2026-09-25',
        }),
      ],
    });
    renderPult();

    expect(
      await screen.findByText('Срок сегодня: «Поторопить: „Справка для Кабмина“».'),
    ).toBeInTheDocument();
  });

  it('время сводки — из порога в «Управлении»', async () => {
    route.set({ view: 'summary' });
    serve('assistant', VIEW, { sendAt: '09:15' });
    renderPult();

    const notice = (await screen.findByRole('heading', { name: 'Утренняя сводка' })).closest(
      'section',
    )!;
    expect(await within(notice).findByText('09:15')).toBeInTheDocument();
    expect(screen.getByText(/сводка в 09:15/)).toBeInTheDocument();
  });

  it('опрос Пульта не сворачивает строку и не стирает черновик вопроса', async () => {
    route.set({ view: 'summary' });
    const calls = serve('assistant', WITH_DUE, { fresh: true });
    const client = renderPult();

    const due = (await screen.findByRole('heading', { name: 'Срок сегодня' })).closest('section')!;
    fireEvent.click(within(due).getByRole('button', { name: 'Спросить' }));
    const draft = within(due).getByLabelText('Что нужно решить руководителю');
    fireEvent.change(draft, { target: { value: 'Переносим выгрузку?' } });

    const polled = calls.filter((each) => each.path === '/api/v1/pult').length;
    await act(() => client.invalidateQueries({ queryKey: ['pult'] }));
    await waitFor(() =>
      expect(calls.filter((each) => each.path === '/api/v1/pult').length).toBeGreaterThan(polled),
    );

    expect(within(due).getByLabelText('Что нужно решить руководителю')).toHaveValue(
      'Переносим выгрузку?',
    );
  });

  it('руководитель включает уведомления на этом устройстве', async () => {
    pushCapable();
    route.set({ view: 'summary' });
    serve('leader');
    renderPult();

    fireEvent.click(await screen.findByRole('button', { name: 'Включить уведомления' }));

    const card = screen
      .getByRole('heading', { name: 'Уведомления на этом устройстве' })
      .closest('section')!;
    expect(await within(card).findByText('Включены')).toBeInTheDocument();
    // В демо касание ничего не подписывает — и экран не обещает, что сводка придёт.
    expect(card).toHaveTextContent(/в демо: касание ничего не подписало/);
    expect(card).not.toHaveTextContent(/сводка придёт в/);
    expect(card).toHaveTextContent(/Уведомлений только два/);
    expect(screen.getByText(/Доставка и устройство руководителя пока вымышлены/)).toBeVisible();
    // «Пришла на iPhone» над «включите на этом устройстве» противоречило бы само себе.
    expect(screen.queryByText(/Пришла|Ещё не время/)).not.toBeInTheDocument();
  });

  it('запрещённые в настройках — подсказка, а не кнопка', async () => {
    pushCapable('denied');
    route.set({ view: 'summary' });
    serve('leader');
    renderPult();

    // jsdom — не iPhone: путь через настройки сайта, а не через «Настройки» телефона.
    expect(
      await screen.findByText(/Уведомления для ORBITA запрещены в браузере/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Включить уведомления' })).not.toBeInTheDocument();
  });

  it('помощник видит, дойдёт ли до руководителя, и где меняется время', async () => {
    route.set({ view: 'summary' });
    serve('assistant');
    renderPult();

    const leader = (await screen.findByRole('heading', { name: 'Кому приходит' })).closest(
      'section',
    )!;
    expect(leader).toHaveTextContent(/iPhone руководителя, с/);
    expect(screen.getByText(/порог «Утренняя сводка» в «Управлении»/)).toBeInTheDocument();
    expect(screen.getByText(/Пришла|Ещё не время/)).toBeInTheDocument();
    expect(screen.getByText(/Доставка и устройство руководителя пока вымышлены/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Включить уведомления' })).not.toBeInTheDocument();
  });

  it('вкладка переключается касанием и остаётся в адресе', async () => {
    setViewport({ width: 390 });
    serve('leader');
    renderPult();

    fireEvent.click(await screen.findByRole('tab', { name: 'Сводка' }));

    expect(route.get()).toEqual({ view: 'summary' });
    expect(await screen.findByRole('heading', { name: 'Утренняя сводка' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Сейчас' }));
    expect(route.get()).toEqual({});
  });
});

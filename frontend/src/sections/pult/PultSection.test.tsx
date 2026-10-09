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

import { keyBytes } from '@/app/notifications';
import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import type { PultRow, PultView, PushRow, ReportView, SoonRow, SummaryView } from './model';
import { PultSection } from './PultSection';

/**
 * Что подменяют `pushCapable` и тест iPhone: в jsdom ни уведомлений, ни service worker нет, а
 * браузер всегда называет себя одинаково.
 */
const PUSH_STUBS: [object, string][] = [
  [window, 'Notification'],
  [window, 'PushManager'],
  [navigator, 'serviceWorker'],
  [navigator, 'userAgent'],
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
  soon_days: 14,
  // Пусто по умолчанию: кнопки решений горизонта путали бы проверки лестницы, которые
  // ищут «Поторопить» и «Утвердить» по всему экрану. Горизонт проверяется своими данными.
  soon: [],
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

const SOON: SoonRow[] = [
  row({
    entity_id: 's-1',
    target_id: 's-1',
    title: 'Отбор участников пилота',
    step: 'burning',
    deviation: 2,
    due_on: '2026-09-27',
  }),
  {
    ...row({
      entity_id: 's-2',
      target_id: 's-2',
      title: 'Смета миссии',
      due_on: '2026-10-03',
      responsible: TURSUNOV,
    }),
    step: 'on_track',
    deviation: 0,
  },
];

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

/** Строка экрана блокировки — те поля строки лестницы, что сервер кладёт в `lock_screen`. */
function pushRow({ title, section, decision_kind, context, deviation }: PultRow): PushRow {
  return { title, section, decision_kind, context, deviation };
}

/** Открытый ключ сервера (VAPID): точка P-256, как её отдаёт `push_key`. */
const PUSH_KEY =
  'BCGMnF2SzmRBdUfjotw5UOjT7dzbfuITkzf-vQlO-Rd-5cgg6YnBwslxqINz5yASCxoEP3DM-cuaBxwvqOwwBq8';
/** Прежний ключ сервера: подписка, сделанная им, после смены ключа не доставляет ничего. */
const OLD_KEY =
  'BJwh8qcTbPeksWy4AoxZZKAjrLY3yan-9ydDcE8xTuBRa1OZLCzBku1Fvg_2YTz_xDlydszk5FG5SMcNZslhkd0';

/**
 * Ответ сводки. Экран блокировки собран из списков так же, как его собирает сервер: самое
 * давнее и первое по лестнице. Сама выборка — забота сервера и его тестов (`test_pult.py`).
 *
 * По умолчанию — рабочий контур, тот, что вызывает расписание: 10:00 по Ташкенту, сводка ушла
 * в 08:30 на iPhone руководителя, последний запуск утра — в 11:50.
 */
function summary(
  awaiting: PultRow[],
  due_today: PultRow[],
  overrides: Partial<SummaryView> = {},
): SummaryView {
  const [oldest] = awaiting;
  const [first] = due_today;
  return {
    as_of: '2026-09-25T05:00:00Z',
    send_at: '08:30',
    last_run: '11:50',
    sent_at: '2026-09-25T03:30:04Z',
    awaiting,
    due_today,
    lock_screen: {
      awaiting: oldest ? { count: awaiting.length, oldest: pushRow(oldest) } : null,
      due: first ? { count: due_today.length, first: pushRow(first) } : null,
    },
    leader_device: { name: 'iPhone', since: '2026-09-17' },
    push_key: PUSH_KEY,
    is_demo: false,
    ...overrides,
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

/** Что сервер отвечает на подписку: с какого дня доставляет и куда. */
const SUBSCRIBED = { since: '2026-09-21', device: 'Windows' };

/** Как настоящий сервер отвечает на подписку: записал и сказал, с какого дня доставляет. */
const saved = () => reply(200, SUBSCRIBED);

/**
 * Подменить сеть. Возвращает список запросов, чтобы проверить, что ушло на сервер.
 *
 * `summary` — ответ сводки. `fresh` — как настоящий сервер: у каждого ответа Пульта и сводки
 * своё `as_of`. `subscription` — ответ на запись подписки по номеру попытки, с первой.
 */
function serve(
  role: 'leader' | 'assistant',
  view: PultView = VIEW,
  {
    summary: body = SUMMARY,
    fresh = false,
    subscription = saved,
  }: {
    summary?: SummaryView;
    fresh?: boolean;
    subscription?: (attempt: number) => Response;
  } = {},
) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const answered = { pult: 0, summary: 0, subscription: 0 };
  const moment = (kind: keyof typeof answered, hour: string) => {
    answered[kind] += 1;
    return `2026-09-25T${hour}:00:${String(answered[kind]).padStart(2, '0')}Z`;
  };
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (path === '/api/v1/pult') {
      const as_of = fresh ? moment('pult', '12') : view.as_of;
      return Promise.resolve(reply(200, { ...view, as_of }));
    }
    if (path === '/api/v1/pult/summary') {
      const as_of = fresh ? moment('summary', '05') : body.as_of;
      return Promise.resolve(reply(200, { ...body, as_of }));
    }
    if (path === '/api/v1/push/subscription' && method === 'PUT') {
      answered.subscription += 1;
      return Promise.resolve(subscription(answered.subscription));
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

  it('длинная лестница — без кнопки: горящее в хвосте видно, свёрнута только норма', async () => {
    // ТЗ 4 сворачивает в строку только «по плану». Телефон рисует первые строки раньше
    // остальных, но хвост приходит сам, а не прячется за «Показать ещё».
    setViewport({ width: 390 });
    const overdue = Array.from({ length: 14 }, (_, at) =>
      row({ entity_id: `o-${at}`, target_id: `o-${at}`, title: `Просроченная ${at + 1}` }),
    );
    const burning = Array.from({ length: 3 }, (_, at) =>
      row({
        entity_id: `b-${at}`,
        target_id: `b-${at}`,
        title: `Горящая ${at + 1}`,
        step: 'burning',
        deviation: 0,
      }),
    );
    serve('leader', {
      ...VIEW,
      rows: [...overdue, ...burning],
      counts: { ...VIEW.counts, awaiting_decision: 0, overdue: 14, burning: 3 },
    });
    renderPult();

    // Хвост дорисовывается после первой отрисовки: под нагрузкой полного прогона это
    // дольше секунды ожидания по умолчанию (падало именно так).
    expect(await screen.findByText('Горящая 3', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText('Просроченная 14')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Показать ещё/ })).not.toBeInTheDocument();
    expect(screen.getByText('и ещё 21 по плану')).toBeInTheDocument();
  });

  it('«Что сорвётся за 14 дней?» — по датам, решение по строке нормы уходит по её объекту', async () => {
    const calls = serve('leader', { ...VIEW, soon: SOON });
    renderPult();

    expect(await screen.findByText('Что сорвётся за 14 дней?')).toBeInTheDocument();
    expect(screen.getByText('2 срока, ближайший — через 2 дн')).toBeInTheDocument();
    const quiet = screen.getByText('Смета миссии').closest('li')!;
    expect(within(quiet).getByText('По плану')).toBeInTheDocument();

    fireEvent.click(await within(quiet).findByRole('button', { name: 'Поторопить' }));

    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'POST',
        path: '/api/v1/decisions',
        body: { target_type: 'project', target_id: 's-2', kind: 'hurry' },
      }),
    );
  });

  it('пустой горизонт — фраза, а не пустая карточка', async () => {
    serve('leader');
    renderPult();
    expect(await screen.findByText('За 14 дней сроков нет.')).toBeInTheDocument();
  });

  it('на телефоне число изменений «с прошлого визита» — в шапке, без прокрутки', async () => {
    setViewport({ width: 390 });
    serve('leader');
    renderPult();
    expect(
      await screen.findByRole('button', { name: /1 изменение с прошлого визита/ }),
    ).toBeInTheDocument();
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

/** Ждёт решения дольше всех — строка Пульта. */
const AWAITING = VIEW.rows[0]!;

/** Срок сегодня: строка «горит» с нулём дней до срока. */
const DUE = row({
  section: 'tasks',
  entity_id: 't-5',
  target_type: 'task',
  target_id: 't-5',
  title: 'Выгрузка данных в субплатформу',
  step: 'burning',
  deviation: 0,
  due_on: '2026-09-25',
});

const SUMMARY = summary([AWAITING], [DUE]);

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/unit-1';
/** Ключи шифрования подписки: так их отдаёт `PushSubscription.toJSON()`. */
const KEYS = {
  p256dh: 'BJwh8qcTbPeksWy4AoxZZKAjrLY3yan-9ydDcE8xTuBRa1OZLCzBku1Fvg_2YTz_xDlydszk5FG5SMcNZslhkd0',
  auth: 'POIZrrDUbgme5CUOyHTnbw',
};

function define(target: object, key: string, value: unknown) {
  Object.defineProperty(target, key, { value, configurable: true });
}

/** Подписка браузера на пуши — то, что из неё читает экран. */
function subscriptionWith(key: Uint8Array, onUnsubscribe: () => void) {
  return {
    endpoint: ENDPOINT,
    options: { applicationServerKey: key.slice().buffer },
    toJSON: () => ({ endpoint: ENDPOINT, expirationTime: null, keys: KEYS }),
    unsubscribe: vi.fn(() => {
      onUnsubscribe();
      return Promise.resolve(true);
    }),
  };
}

/**
 * Устройство, на котором уведомления можно включить: как Chrome на ноутбуке.
 *
 * `answer` — что человек ответит на запрос разрешения; `subscribedWith` — ключ сервера, которым
 * устройство уже подписано; `worker: false` — страница без service worker, как на сервере
 * разработки.
 */
function pushCapable({
  permission = 'default',
  answer = 'granted',
  subscribedWith = null,
  worker = true,
}: {
  permission?: NotificationPermission;
  answer?: NotificationPermission;
  subscribedWith?: string | null;
  worker?: boolean;
} = {}) {
  let granted = permission;
  let registered = worker;
  let current: ReturnType<typeof subscriptionWith> | null = null;
  const unsubscribed = () => {
    current = null;
  };
  if (subscribedWith) current = subscriptionWith(keyBytes(subscribedWith), unsubscribed);
  const initial = current;

  const pushManager = {
    getSubscription: vi.fn(() => Promise.resolve(current)),
    subscribe: vi.fn((options: { applicationServerKey: Uint8Array }) => {
      current = subscriptionWith(options.applicationServerKey, unsubscribed);
      return Promise.resolve(current);
    }),
  };
  const requestPermission = vi.fn(() => {
    granted = answer;
    return Promise.resolve(granted);
  });

  define(window, 'Notification', {
    get permission() {
      return granted;
    },
    requestPermission,
  });
  define(window, 'PushManager', function PushManager() {});
  define(navigator, 'serviceWorker', {
    getRegistration: () => Promise.resolve(registered ? { active: {}, pushManager } : undefined),
  });

  return {
    pushManager,
    requestPermission,
    initial,
    /** Worker снят, пока карточка на экране. */
    dropWorker: () => {
      registered = false;
    },
  };
}

function section(name: string): HTMLElement {
  return screen.getByRole('heading', { name }).closest('section')!;
}

/**
 * Карточка устройства руководителя. Пока `/api/me` не ответил, вкладка показывает вид помощника,
 * и те же слова («Включены», «не настроены на сервере») нашлись бы в его карточках.
 */
async function deviceCard(): Promise<HTMLElement> {
  await screen.findByRole('heading', { name: 'Уведомления на этом устройстве' });
  return section('Уведомления на этом устройстве');
}

function subscriptionCalls(calls: ReturnType<typeof serve>) {
  return calls.filter((each) => each.path === '/api/v1/push/subscription');
}

describe('утренняя сводка', () => {
  it('касание уведомления открывает вкладку: вид на экране блокировки и два пункта', async () => {
    route.set({ view: 'summary' });
    serve('leader');
    renderPult();

    expect(await screen.findByRole('tab', { name: 'Сводка' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      await screen.findByText('Ждут решения: 1, дольше всех — «Согласование ТЗ», 6 дн.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Срок сегодня: «Выгрузка данных в субплатформу».')).toBeInTheDocument();

    const awaiting = section('Ждут решения');
    expect(within(awaiting).getByText('Согласование ТЗ')).toBeInTheDocument();
    expect(awaiting).toHaveTextContent('дольше всех: ждёт 6 дн');
    expect(
      within(section('Срок сегодня')).getByText('Выгрузка данных в субплатформу'),
    ).toBeVisible();
  });

  it('экран блокировки — ответ сервера, тот же, что уйдёт в пуш, а не пересчёт списков', async () => {
    route.set({ view: 'summary' });
    serve('leader', VIEW, {
      summary: {
        ...SUMMARY,
        lock_screen: {
          awaiting: {
            count: 4,
            oldest: { ...pushRow(AWAITING), title: 'Паспорт миссии', deviation: 9 },
          },
          due: { count: 3, first: pushRow(DUE) },
        },
      },
    });
    renderPult();

    expect(
      await screen.findByText('Ждут решения: 4, дольше всех — «Паспорт миссии», 9 дн.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Срок сегодня: 3 — «Выгрузка данных в субплатформу» и ещё 2.'),
    ).toBeInTheDocument();
  });

  it('решение из сводки — то же касание, что на Пульте, с «Отменить»', async () => {
    route.set({ view: 'summary' });
    const calls = serve('leader');
    renderPult();

    await screen.findByRole('heading', { name: 'Ждут решения' });
    fireEvent.click(within(section('Ждут решения')).getByRole('button', { name: 'Утвердить' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Отменить' })).toBeVisible());
    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/v1/decisions',
      body: { target_type: 'milestone', target_id: 'm-1', kind: 'approve' },
    });
  });

  it('пустая сводка — фразы, а не нули и не «спокойно»', async () => {
    route.set({ view: 'summary' });
    serve('leader', VIEW, { summary: summary([], []) });
    renderPult();

    // Одна фраза — на экране блокировки, вторая — в пункте под ним.
    expect(await screen.findAllByText('Решений не ждёт.')).toHaveLength(2);
    expect(screen.getAllByText('Сроков сегодня нет.')).toHaveLength(2);
    expect(screen.queryByText(/спокойно/)).not.toBeInTheDocument();
  });

  it('решение без текста на экране блокировки названо вместе со своим объектом', async () => {
    route.set({ view: 'summary' });
    const decision = row({
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
    });
    serve('leader', VIEW, { summary: summary([], [decision]) });
    renderPult();

    expect(
      await screen.findByText('Срок сегодня: «Поторопить: „Справка для Кабмина“».'),
    ).toBeInTheDocument();
  });

  it('время сводки — из ответа сервера: порог «Утренняя сводка»', async () => {
    route.set({ view: 'summary' });
    serve('assistant', VIEW, {
      summary: { ...SUMMARY, send_at: '09:15', as_of: '2026-09-25T03:00:00Z', sent_at: null },
    });
    renderPult();

    const notice = (await screen.findByRole('heading', { name: 'Утренняя сводка' })).closest(
      'section',
    )!;
    expect(await within(notice).findByText('09:15')).toBeInTheDocument();
    expect(notice).toHaveTextContent('придёт сегодня в 09:15 по Ташкенту');
    expect(screen.getByText(/сводка в 09:15/)).toBeInTheDocument();
  });

  it('опрос Пульта и сводки не сворачивает строку и не стирает черновик вопроса', async () => {
    route.set({ view: 'summary' });
    const calls = serve('assistant', VIEW, { fresh: true });
    const client = renderPult();

    await screen.findByRole('heading', { name: 'Срок сегодня' });
    fireEvent.click(within(section('Срок сегодня')).getByRole('button', { name: 'Спросить' }));
    fireEvent.change(screen.getByLabelText('Что нужно решить руководителю'), {
      target: { value: 'Переносим выгрузку?' },
    });

    const read = () => calls.filter((each) => each.path === '/api/v1/pult/summary').length;
    const polled = read();
    await act(() => client.invalidateQueries({ queryKey: ['pult'] }));
    await waitFor(() => expect(read()).toBeGreaterThan(polled));

    // С экрана, а не из старой секции: пересозданная вкладка оставила бы черновик в
    // отсоединённом узле, и проверка прошла бы зря.
    expect(screen.getByLabelText('Что нужно решить руководителю')).toHaveValue(
      'Переносим выгрузку?',
    );
  });

  describe('доставка — помощнику', () => {
    // «Сейчас» — `as_of` ответа: 03:29Z — это 08:29 по Ташкенту. Контур — рабочий, если в
    // случае не сказано иное: только его вызывает расписание.
    it.each([
      ['ушла — когда и куда', {}, 'Пришла', 'сегодня в 08:30 · iPhone'],
      [
        'до времени сводки — ещё не время',
        { as_of: '2026-09-25T03:29:00Z', sent_at: null },
        'Ещё не время',
        'придёт сегодня в 08:30 по Ташкенту',
      ],
      [
        'в минуту сводки — отправляется',
        { as_of: '2026-09-25T03:30:00Z', sent_at: null },
        'Отправляется',
        'время сводки 08:30, расписание проверяет каждые 10 минут',
      ],
      [
        'полчаса ещё отправляется',
        { as_of: '2026-09-25T03:59:00Z', sent_at: null },
        'Отправляется',
        'время сводки 08:30',
      ],
      [
        'через полчаса — не ушла',
        { as_of: '2026-09-25T04:00:00Z', sent_at: null },
        'Не ушла',
        'в 08:30 сводка не отправилась — расписание пробует снова, последний запуск в 11:50',
      ],
      [
        'в минуту последнего запуска — ещё пробует',
        { as_of: '2026-09-25T06:50:00Z', sent_at: null },
        'Не ушла',
        'последний запуск в 11:50',
      ],
      [
        'сразу после последнего запуска — ещё не «завтра»: GitHub запускает его с опозданием',
        { as_of: '2026-09-25T06:55:00Z', sent_at: null },
        'Не ушла',
        'последний запуск в 11:50',
      ],
      [
        'после последнего запуска и запаса на опоздание — уже завтра',
        { as_of: '2026-09-25T07:21:00Z', sent_at: null },
        'Сегодня не пришла',
        'следующая — завтра в 08:30',
      ],
      [
        'последний запуск — из ответа сервера, а не из текста',
        { as_of: '2026-09-25T07:11:00Z', sent_at: null, last_run: '11:40' },
        'Сегодня не пришла',
        'следующая — завтра в 08:30',
      ],
      [
        'до последнего запуска из ответа — пробует до него',
        { as_of: '2026-09-25T06:00:00Z', sent_at: null, last_run: '11:40' },
        'Не ушла',
        'последний запуск в 11:40',
      ],
      [
        'не рабочий контур — расписания нет, обещаний ко времени нет',
        { as_of: '2026-09-25T04:00:00Z', sent_at: null, is_demo: true },
        'Не по расписанию',
        'в этом контуре сводку по расписанию не шлют — приходит только пуш «ждёт вашего решения»',
      ],
      [
        'не рабочий контур, до времени сводки — то же, без «ещё не время»',
        { as_of: '2026-09-25T03:00:00Z', sent_at: null, is_demo: true },
        'Не по расписанию',
        'приходит только пуш «ждёт вашего решения»',
      ],
      [
        'не рабочий контур, сводку отправили вручную — пришла',
        { is_demo: true },
        'Пришла',
        'сегодня в 08:30 · iPhone',
      ],
      [
        'не рабочий контур без устройства — не придёт и вопрос',
        { leader_device: null, sent_at: null, is_demo: true },
        'Не придёт: у руководителя не включены уведомления',
        null,
      ],
      [
        'у руководителя не включены — не придёт',
        { leader_device: null, sent_at: null },
        'Не придёт: у руководителя не включены уведомления',
        null,
      ],
      [
        'на сервере нет ключа — не придёт',
        { push_key: null },
        'Не придёт: уведомления не настроены на сервере — ключ вводит заказчик',
        null,
      ],
    ] as const)('%s', async (_name, overrides, state, detail) => {
      route.set({ view: 'summary' });
      serve('assistant', VIEW, { summary: { ...SUMMARY, ...overrides } });
      renderPult();

      await screen.findByRole('heading', { name: 'Утренняя сводка' });
      const notice = section('Утренняя сводка');
      expect(within(notice).getByText(state)).toBeInTheDocument();
      if (detail) expect(notice).toHaveTextContent(detail);
      // Ни одно состояние, кроме «Не ушла», не обещает новых попыток.
      if (state !== 'Не ушла') expect(notice).not.toHaveTextContent('пробует снова');
    });
  });

  it('помощник видит, дойдёт ли до руководителя, и где меняется время', async () => {
    route.set({ view: 'summary' });
    serve('assistant');
    renderPult();

    await screen.findByRole('heading', { name: 'Кому приходит' });
    expect(section('Кому приходит')).toHaveTextContent('iPhone руководителя, с 17.09.2026');
    expect(screen.getByText(/порог «Утренняя сводка» в «Управлении»/)).toBeInTheDocument();
    expect(screen.getByText('Пришла')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Включить уведомления' })).not.toBeInTheDocument();
  });

  describe('устройство руководителя', () => {
    it('включает уведомления: разрешение, подписка ключом сервера, запись на сервере', async () => {
      const device = pushCapable();
      route.set({ view: 'summary' });
      const calls = serve('leader');
      renderPult();

      fireEvent.click(await screen.findByRole('button', { name: 'Включить уведомления' }));

      const card = await deviceCard();
      await within(card).findByText('Включены');
      expect(card).toHaveTextContent('с 21.09.2026 · сводка придёт в 08:30');
      expect(card).toHaveTextContent(/Уведомлений только два/);
      expect(device.requestPermission).toHaveBeenCalledTimes(1);
      expect(device.pushManager.subscribe).toHaveBeenCalledWith({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(PUSH_KEY),
      });
      // Серверу — адрес службы пушей и ключи шифрования; остальное из `toJSON()` не уходит.
      expect(calls).toContainEqual({
        method: 'PUT',
        path: '/api/v1/push/subscription',
        body: { endpoint: ENDPOINT, keys: KEYS },
      });
      // «Пришла на iPhone» над «включите на этом устройстве» противоречило бы само себе.
      expect(screen.queryByText(/Пришла|Ещё не время/)).not.toBeInTheDocument();
    });

    it('подписка, что уже есть, сверяется с сервером при открытии вкладки', async () => {
      const device = pushCapable({ permission: 'granted', subscribedWith: PUSH_KEY });
      route.set({ view: 'summary' });
      const calls = serve('leader');
      renderPult();

      const card = await deviceCard();
      await within(card).findByText('Включены');
      expect(card).toHaveTextContent('с 21.09.2026');
      expect(subscriptionCalls(calls)).toContainEqual({
        method: 'PUT',
        path: '/api/v1/push/subscription',
        body: { endpoint: ENDPOINT, keys: KEYS },
      });
      expect(device.pushManager.subscribe).not.toHaveBeenCalled();
      expect(
        screen.queryByRole('button', { name: 'Включить уведомления' }),
      ).not.toBeInTheDocument();
    });

    it('не рабочий контур: «Включены» без обещания сводки ко времени', async () => {
      pushCapable({ permission: 'granted', subscribedWith: PUSH_KEY });
      route.set({ view: 'summary' });
      serve('leader', VIEW, { summary: { ...SUMMARY, is_demo: true } });
      renderPult();

      const card = await deviceCard();
      await within(card).findByText('Включены');
      expect(card).toHaveTextContent(
        'с 21.09.2026 · здесь приходит только «ждёт вашего решения»: сводку по расписанию шлёт рабочий контур',
      );
      expect(card).not.toHaveTextContent('сводка придёт в');
    });

    it('подписку отозвала служба пушей (410): снимается, и снова есть кнопка', async () => {
      const device = pushCapable({ permission: 'granted', subscribedWith: PUSH_KEY });
      route.set({ view: 'summary' });
      // Первая запись — отозванный адрес: сервер его не восстанавливает. Новый — принимает.
      const calls = serve('leader', VIEW, {
        subscription: (attempt) =>
          attempt === 1
            ? reply(410, { detail: 'Этот адрес службы пушей больше не действует' })
            : saved(),
      });
      renderPult();

      const enable = await screen.findByRole('button', { name: 'Включить уведомления' });
      expect(device.initial?.unsubscribe).toHaveBeenCalledTimes(1);
      // Сама вкладка не подписывается: на iPhone подписка — только по касанию.
      expect(device.pushManager.subscribe).not.toHaveBeenCalled();
      const card = await deviceCard();
      expect(within(card).queryByText('Включены')).not.toBeInTheDocument();
      expect(within(card).queryByRole('alert')).not.toBeInTheDocument();

      fireEvent.click(enable);

      await within(card).findByText('Включены');
      expect(device.pushManager.subscribe).toHaveBeenCalledTimes(1);
      expect(subscriptionCalls(calls)).toHaveLength(3);
    });

    it('запись подписки сорвалась, а перечитанное состояние — «Включены»: отказа под ним нет', async () => {
      pushCapable();
      route.set({ view: 'summary' });
      serve('leader', VIEW, {
        subscription: (attempt) =>
          attempt === 1 ? reply(503, { detail: 'Сервер временно недоступен' }) : saved(),
      });
      renderPult();

      fireEvent.click(await screen.findByRole('button', { name: 'Включить уведомления' }));

      const card = await deviceCard();
      await within(card).findByText('Включены');
      await waitFor(() => expect(within(card).queryByRole('alert')).not.toBeInTheDocument());
      expect(card).not.toHaveTextContent('Сервер временно недоступен');
    });

    it('подписка прежним ключом сервера не считается: снимается, новая — нынешним', async () => {
      const device = pushCapable({ permission: 'granted', subscribedWith: OLD_KEY });
      route.set({ view: 'summary' });
      const calls = serve('leader');
      renderPult();

      fireEvent.click(await screen.findByRole('button', { name: 'Включить уведомления' }));

      await within(await deviceCard()).findByText('Включены');
      expect(device.initial?.unsubscribe).toHaveBeenCalledTimes(1);
      expect(device.pushManager.subscribe).toHaveBeenCalledWith({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(PUSH_KEY),
      });
      expect(subscriptionCalls(calls).length).toBeGreaterThan(0);
    });

    it('не разрешили — подсказка, как вернуть, и ничего не подписано', async () => {
      const device = pushCapable({ answer: 'denied' });
      route.set({ view: 'summary' });
      const calls = serve('leader');
      renderPult();

      fireEvent.click(await screen.findByRole('button', { name: 'Включить уведомления' }));

      // jsdom — не iPhone: путь через настройки сайта, а не через «Настройки» телефона.
      expect(
        await screen.findByText(/Уведомления для ORBITA запрещены в браузере/),
      ).toBeInTheDocument();
      expect(device.pushManager.subscribe).not.toHaveBeenCalled();
      expect(subscriptionCalls(calls)).toEqual([]);
    });

    it('запрещённые в настройках — подсказка, а не кнопка', async () => {
      pushCapable({ permission: 'denied' });
      route.set({ view: 'summary' });
      serve('leader');
      renderPult();

      expect(
        await screen.findByText(/Уведомления для ORBITA запрещены в браузере/),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Включить уведомления' }),
      ).not.toBeInTheDocument();
    });

    it('страница без service worker — факт вместо кнопки', async () => {
      pushCapable({ worker: false });
      route.set({ view: 'summary' });
      serve('leader');
      renderPult();

      expect(await screen.findByText(/фоновая служба ORBITA не запустилась/)).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Включить уведомления' }),
      ).not.toBeInTheDocument();
    });

    it('worker пропал к моменту касания — отказ словами, а не молча', async () => {
      const device = pushCapable();
      route.set({ view: 'summary' });
      serve('leader');
      renderPult();

      const enable = await screen.findByRole('button', { name: 'Включить уведомления' });
      device.dropWorker();
      fireEvent.click(enable);

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /фоновая служба ORBITA не запустилась/,
      );
      expect(device.pushManager.subscribe).not.toHaveBeenCalled();
    });

    it('сервер без ключа — факт вместо кнопки', async () => {
      pushCapable();
      route.set({ view: 'summary' });
      serve('leader', VIEW, { summary: { ...SUMMARY, push_key: null } });
      renderPult();

      const card = await deviceCard();
      expect(
        await within(card).findByText(/не настроены на сервере — ключ вводит заказчик/),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Включить уведомления' }),
      ).not.toBeInTheDocument();
    });

    it('iPhone в Safari: без ключа сервера шаги установки всё равно показаны', async () => {
      define(navigator, 'userAgent', IPHONE);
      route.set({ view: 'summary' });
      serve('leader', VIEW, { summary: { ...SUMMARY, push_key: null } });
      renderPult();

      // Установка на экран «Домой» нужна и сама по себе, а ключ заказчик введёт позже.
      expect(await screen.findByText(/Выберите «На экран «Домой»»/)).toBeInTheDocument();
    });
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

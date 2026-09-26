/**
 * Экран «Проекты» против ответа API: кто что может, пауза только с причиной, новый
 * проект за два поля, телефон без таблиц, «что если» и версии записей.
 *
 * Числа — ступени, готовность, отставание — считает сервер и проверяет
 * `backend/tests/test_projects.py`. Здесь — что экран делает с ответом и что уходит на
 * сервер по касанию. Сеть подменена на уровне `fetch`, как в тесте Пульта.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { localDay } from '@/shared/time';
import { setViewport } from '@/test-setup';

import type { ProjectCard, WhatIfResult } from './model';
import { ProjectsSection } from './ProjectsSection';
import { ITEMS, card, detail, view } from './test-data';

const BASE = '/api/v1/projects';

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

const WHAT_IF: WhatIfResult = {
  project: {
    before: { step: 'awaiting_decision', deviation: 2, lag_days: 20, due_on: '2026-11-04' },
    after: { step: 'awaiting_decision', deviation: 2, lag_days: 20, due_on: '2026-11-04' },
  },
  milestones: [
    { id: 'pr-geodata-m1', title: 'Согласование с министерствами', before: null, after: 'burning' },
  ],
  pult: {
    before: { awaiting_decision: 2, overdue: 3, burning: 5, blocked_by_others: 1, silent: 2 },
    after: { awaiting_decision: 2, overdue: 3, burning: 6, blocked_by_others: 1, silent: 2 },
  },
};

const STALE = 'Запись уже изменили, пока вы её редактировали';

/** Подменить сеть. Возвращает список запросов, чтобы проверить, что ушло на сервер. */
interface ServeOptions {
  stale?: boolean;
  /** Версия вехи в ответе карточки — тест меняет её, изображая чужую правку. */
  milestone?: { version: number };
}

function serve(role: 'leader' | 'assistant', { stale = false, milestone }: ServeOptions = {}) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const created: ProjectCard[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });

    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (method === 'GET' && path === BASE) return Promise.resolve(reply(200, view()));
    if (method === 'POST' && path === BASE) {
      const fresh = card({ id: 'pr-new', code: 'PRJ-2026-022', title: body.title });
      created.push(fresh);
      return Promise.resolve(reply(201, detail(fresh)));
    }
    if (method === 'GET' && path.startsWith(`${BASE}/`)) {
      const id = path.slice(BASE.length + 1);
      const found = [...ITEMS, ...created].find((each) => each.id === id) ?? card({ id });
      const body = detail(found);
      if (milestone) body.milestone_list[0]!.version = milestone.version;
      return Promise.resolve(reply(200, body));
    }
    if (method === 'POST' && path.endsWith('/what-if')) return Promise.resolve(reply(200, WHAT_IF));
    if (method === 'PUT' && stale) {
      return Promise.resolve(reply(409, { detail: STALE, type: 'stale-data' }));
    }
    if (method === 'PUT') return Promise.resolve(reply(204));
    return Promise.resolve(reply(404, { detail: `нет подмены ${method} ${path}` }));
  });
  return calls;
}

function renderProjects() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  rendered = client;
  return render(
    <QueryClientProvider client={client}>
      <ProjectsSection />
    </QueryClientProvider>,
  );
}

/** Перетаскивание плитки: jsdom не умеет DataTransfer, отдаём его руками. */
function drop(column: HTMLElement, id: string) {
  const dataTransfer = { getData: () => id, setData: () => undefined };
  fireEvent.dragOver(column, { dataTransfer });
  fireEvent.drop(column, { dataTransfer });
}

/** Клиент запросов последнего рендера — чтобы изобразить опрос карточки. */
let rendered: QueryClient;

afterEach(() => vi.restoreAllMocks());

describe('Проекты', () => {
  it('доска по статусам и пометка «вымышленные данные»', async () => {
    serve('assistant');
    renderProjects();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    for (const status of ['В работе', 'На паузе', 'Завершён', 'Отменён']) {
      expect(screen.getByRole('region', { name: status })).toBeInTheDocument();
    }
    const paused = screen.getByRole('region', { name: 'На паузе' });
    expect(within(paused).getByText('Причина: Сезон съёмки начинается в ноябре')).toBeVisible();
  });

  it('перенос в «На паузе» спрашивает причину и уходит на сервер с версией', async () => {
    const calls = serve('assistant');
    renderProjects();

    drop(await screen.findByRole('region', { name: 'На паузе' }), 'pr-geodata');

    const dialog = await screen.findByRole('dialog');
    const save = within(dialog).getByRole('button', { name: 'Сохранить' });
    expect(save).toBeDisabled();

    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'Ждём финансирование' },
    });
    fireEvent.click(save);

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(calls.find((call) => call.method === 'PUT')).toEqual({
      method: 'PUT',
      path: `${BASE}/pr-geodata/status`,
      body: { status: 'on_hold', reason: 'Ждём финансирование', version: 4 },
    });
  });

  it('перенос в «Завершён» причины не спрашивает', async () => {
    const calls = serve('assistant');
    renderProjects();

    drop(await screen.findByRole('region', { name: 'Завершён' }), 'pr-drought');

    await waitFor(() =>
      expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({
        status: 'done',
        reason: null,
        version: 1,
      }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('новый проект — название и тип, вехи из шаблона', async () => {
    const calls = serve('assistant');
    renderProjects();

    fireEvent.click(await screen.findByRole('button', { name: /Новый проект/ }));
    const form = await screen.findByRole('dialog');
    const submit = within(form).getByRole('button', { name: 'Завести проект' });
    expect(submit).toBeDisabled();

    fireEvent.change(within(form).getByLabelText(/Название/), {
      target: { value: 'Положение о спутниковых данных' },
    });
    fireEvent.change(within(form).getByLabelText(/Тип проекта/), {
      target: { value: 'regulation' },
    });
    expect(within(form).getByText('Вехи из шаблона')).toBeInTheDocument();
    expect(within(form).getByText('Внесение в Кабинет Министров')).toBeInTheDocument();
    fireEvent.click(submit);

    expect(await screen.findByText('Проект заведён: PRJ-2026-022')).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'POST' && call.path === BASE)?.body).toEqual({
      title: 'Положение о спутниковых данных',
      type_code: 'regulation',
      started_on: localDay('2026-09-25T07:00:00Z'),
      due_on: null,
      responsible_id: null,
      parent_id: null,
      is_multiyear: false,
    });
    const panel = await screen.findByRole('dialog');
    expect(
      await within(panel).findByRole('heading', { name: 'Положение о спутниковых данных' }),
    ).toBeInTheDocument();
  });

  it('руководитель смотрит: без «Нового проекта» и без смены статуса', async () => {
    serve('leader');
    renderProjects();

    await screen.findByText('Вымышленные данные');
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Новый проект/ })).not.toBeInTheDocument(),
    );

    fireEvent.click(screen.getAllByRole('button', { name: /Постановление о порядке/ })[0]!);
    const panel = await screen.findByRole('dialog');
    expect(await within(panel).findByText('Что если')).toBeInTheDocument();
    expect(within(panel).queryByText('Статус')).not.toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument();
  });

  it('«что если» считает на сервере, «применить» уходит с версиями', async () => {
    const calls = serve('assistant');
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    fireEvent.change(await within(panel).findByLabelText('Согласование с министерствами'), {
      target: { value: '2026-09-28' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Посчитать' }));

    expect(await within(panel).findByText(/Горит:\s*5 → 6/)).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith('/what-if'))?.body).toEqual({
      changes: [{ kind: 'milestone', id: 'pr-geodata-m1', due_on: '2026-09-28' }],
    });
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);

    fireEvent.click(within(panel).getByRole('button', { name: 'Применить' }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith('/dates'))?.body).toEqual({
        changes: [{ kind: 'milestone', id: 'pr-geodata-m1', due_on: '2026-09-28', version: 3 }],
      }),
    );
  });

  it('«применить» пишет с версией на момент расчёта, а не после опроса', async () => {
    const milestone = { version: 3 };
    const calls = serve('assistant', { milestone });
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    fireEvent.change(await within(panel).findByLabelText('Согласование с министерствами'), {
      target: { value: '2026-09-28' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Посчитать' }));
    await within(panel).findByText(/Горит:\s*5 → 6/);

    // Чужая правка: опрос приносит карточку с новой версией вехи.
    milestone.version = 9;
    await rendered.invalidateQueries({ queryKey: ['projects'] });
    await waitFor(() =>
      expect(calls.filter((call) => call.path === `${BASE}/pr-geodata`).length).toBeGreaterThan(1),
    );

    fireEvent.click(within(panel).getByRole('button', { name: 'Применить' }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith('/dates'))?.body).toEqual({
        changes: [{ kind: 'milestone', id: 'pr-geodata-m1', due_on: '2026-09-28', version: 3 }],
      }),
    );
  });

  it('«что мешает» правится с версией проекта', async () => {
    const calls = serve('assistant');
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    fireEvent.click(await within(panel).findByRole('button', { name: 'Снять' }));

    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith('/impediment'))?.body).toEqual({
        text: '',
        version: 4,
      }),
    );
  });

  it('отказ по версии в карточке сказан словами, а не проглочен', async () => {
    serve('assistant', { stale: true });
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    fireEvent.click(await within(panel).findByRole('button', { name: 'Завершён' }));

    expect(await within(panel).findByText(new RegExp(STALE))).toBeInTheDocument();
  });

  it('на телефоне — список по статусам, без таблицы и таймлайна', async () => {
    setViewport({ width: 390 });
    serve('assistant');
    renderProjects();

    const paused = await screen.findByRole('tab', { name: /На паузе/ });
    expect(screen.queryByRole('tab', { name: 'Таблица' })).not.toBeInTheDocument();

    fireEvent.click(paused);
    expect(screen.getByText('Цикл мониторинга: снежный покров')).toBeInTheDocument();
    expect(screen.queryByText('Цикл мониторинга: засуха-2026')).not.toBeInTheDocument();
  });
});

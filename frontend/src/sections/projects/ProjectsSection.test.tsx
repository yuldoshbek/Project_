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

import type { OrganizationRef, ProjectCard, ProjectDetail, WhatIfResult } from './model';
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

const ORGANIZATIONS: OrganizationRef[] = [
  {
    id: 'o-center',
    name: 'Центр космического мониторинга и геоинформационных технологий (МЧЖ)',
    short_name: 'Центр космического мониторинга',
    kind: 'company',
    is_founded_by_agency: true,
  },
  {
    id: 'o-ecology',
    name: 'Министерство экологии',
    short_name: null,
    kind: 'ministry',
    is_founded_by_agency: false,
  },
];

const entry = (code: string, ru: string) => ({
  id: code,
  code,
  name: { ru, uz_cyrl: ru, uz_latn: ru },
  sort_order: 1,
  is_active: true,
});

const DICTIONARIES = {
  project_types: [],
  task_types: [],
  directions: [entry('monitoring', 'Космический мониторинг')],
  regions: [entry('tashkent_city', 'город Ташкент')],
  project_statuses: [] as ReturnType<typeof entry>[],
  task_statuses: [],
};

/** Подменить сеть. Возвращает список запросов, чтобы проверить, что ушло на сервер. */
interface ServeOptions {
  stale?: boolean;
  /** Версия вехи в ответе карточки — тест меняет её, изображая чужую правку. */
  milestone?: { version: number };
}

type Membership = ProjectDetail['organizations'][number];

/**
 * Подменить сеть. «Сервер» помнит роли организаций и сведения проектов — ровно столько,
 * чтобы экран после записи перечитал то, что записал. Возвращает список запросов: тест
 * проверяет, что именно ушло на сервер.
 */
function serve(role: 'leader' | 'assistant', { stale = false, milestone }: ServeOptions = {}) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const created: ProjectCard[] = [];
  const catalog: OrganizationRef[] = [...ORGANIZATIONS];
  const memberships = new Map<string, Membership[]>();
  const details = new Map<string, Partial<ProjectDetail>>();

  /** Плитка с учётом записанного: роль Центра и чужое головное ведомство. */
  const cardOf = (base: ProjectCard): ProjectCard => {
    const orgs = memberships.get(base.id);
    const saved = details.get(base.id);
    return {
      ...base,
      ...(saved?.title ? { title: saved.title } : {}),
      ...(orgs
        ? {
            center_role: orgs.find((org) => org.is_center)?.role ?? null,
            lead_outside: orgs.some((org) => !org.is_center && org.role === 'lead_agency'),
          }
        : {}),
    };
  };
  const nameOf = (entries: typeof DICTIONARIES.directions, code: string | null) => {
    const found = entries.find((each) => each.code === code);
    return found ? { code: found.code, name: found.name.ru } : null;
  };

  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    const [bare = path] = path.split('?');
    const membership = /^\/api\/v1\/projects\/([^/]+)\/organizations\/([^/]+)$/.exec(bare);

    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (path === '/api/v1/dictionaries') return Promise.resolve(reply(200, DICTIONARIES));
    if (bare === '/api/v1/organizations' && method === 'GET') {
      return Promise.resolve(reply(200, catalog));
    }
    if (bare === '/api/v1/organizations' && method === 'POST') {
      const fresh: OrganizationRef = {
        id: `o-new-${catalog.length}`,
        name: body.name,
        short_name: null,
        kind: body.kind,
        is_founded_by_agency: false,
      };
      catalog.push(fresh);
      return Promise.resolve(reply(201, fresh));
    }
    if (method === 'GET' && path === BASE) {
      return Promise.resolve(reply(200, view([...ITEMS, ...created].map(cardOf))));
    }
    if (method === 'POST' && path === BASE) {
      const fresh = card({ id: 'pr-new', code: 'PRJ-2026-022', title: body.title });
      created.push(fresh);
      return Promise.resolve(reply(201, detail(fresh)));
    }
    if (membership && method === 'PUT' && !stale) {
      const [, projectId = '', organizationId = ''] = membership;
      const org = catalog.find((each) => each.id === organizationId)!;
      const list = [...(memberships.get(projectId) ?? [])];
      const existing = list.find((each) => each.id === organizationId);
      if (existing) {
        existing.role = body.role;
        existing.version += 1;
      } else {
        const next = {
          id: org.id,
          name: org.short_name ?? org.name,
          role: body.role,
          is_center: org.is_founded_by_agency,
          version: 1,
        };
        if (next.is_center) list.unshift(next);
        else list.push(next);
      }
      memberships.set(projectId, list);
      return Promise.resolve(reply(204));
    }
    if (membership && method === 'DELETE') {
      const [, projectId = '', organizationId = ''] = membership;
      memberships.set(
        projectId,
        (memberships.get(projectId) ?? []).filter((each) => each.id !== organizationId),
      );
      return Promise.resolve(reply(204));
    }
    if (method === 'PUT' && bare.endsWith('/details') && !stale) {
      const projectId = bare.slice(BASE.length + 1, -'/details'.length);
      details.set(projectId, {
        title: body.title,
        description: body.description,
        direction: nameOf(DICTIONARIES.directions, body.direction_code),
        region: nameOf(DICTIONARIES.regions, body.region_code),
      });
      return Promise.resolve(reply(204));
    }
    if (method === 'GET' && path.startsWith(`${BASE}/`)) {
      const id = path.slice(BASE.length + 1);
      const found = [...ITEMS, ...created].find((each) => each.id === id) ?? card({ id });
      const answer: ProjectDetail = {
        ...detail(cardOf(found)),
        ...details.get(id),
        organizations: memberships.get(id) ?? [],
      };
      if (milestone) answer.milestone_list[0]!.version = milestone.version;
      return Promise.resolve(reply(200, answer));
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

afterEach(() => {
  vi.restoreAllMocks();
  DICTIONARIES.project_statuses = [];
});

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

  it('статусы — из справочника: переименованный и переставленный в «Управлении»', async () => {
    DICTIONARIES.project_statuses = [
      { ...entry('in_progress', 'В работе'), sort_order: 20 },
      { ...entry('on_hold', 'Отложен до решения'), sort_order: 10 },
      { ...entry('done', 'Завершён'), sort_order: 30 },
      { ...entry('cancelled', 'Отменён'), sort_order: 40 },
    ];
    serve('assistant');
    renderProjects();

    const names = ['Отложен до решения', 'В работе', 'Завершён', 'Отменён'];
    await screen.findByRole('region', { name: 'Отложен до решения' });
    const columns = screen
      .getAllByRole('region')
      .map((region) => region.getAttribute('aria-label'))
      .filter((name): name is string => name !== null && names.includes(name));
    expect(columns).toEqual(names);
    expect(screen.queryByRole('region', { name: 'На паузе' })).not.toBeInTheDocument();
  });

  it('монитор: широкая колонка — «В работе», где бы она ни стояла', async () => {
    DICTIONARIES.project_statuses = [
      { ...entry('in_progress', 'В работе'), sort_order: 20 },
      { ...entry('on_hold', 'На паузе'), sort_order: 10 },
      { ...entry('done', 'Завершён'), sort_order: 30 },
      { ...entry('cancelled', 'Отменён'), sort_order: 40 },
    ];
    setViewport({ width: 2560 });
    serve('assistant');
    renderProjects();

    const working = await screen.findByRole('region', { name: 'В работе' });
    await waitFor(() =>
      expect(working.parentElement?.style.gridTemplateColumns).toBe('1fr 2fr 1fr 1fr'),
    );
  });

  it('телефон: вкладки статусов — названия и порядок справочника', async () => {
    DICTIONARIES.project_statuses = [
      { ...entry('in_progress', 'В работе'), sort_order: 20 },
      { ...entry('on_hold', 'Отложен до решения'), sort_order: 10 },
      { ...entry('done', 'Завершён'), sort_order: 30 },
      { ...entry('cancelled', 'Отменён'), sort_order: 40 },
    ];
    setViewport({ width: 390 });
    serve('assistant');
    renderProjects();

    await screen.findByRole('tab', { name: /Отложен до решения/ });
    const tabs = within(screen.getByRole('tablist', { name: 'Статус' })).getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent?.replace(/^\d+/, ''))).toEqual([
      'Отложен до решения',
      'В работе',
      'Завершён',
      'Отменён',
    ]);
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

  it('Центр — одним касанием; роль видна и на доске; смена и удаление — с версией', async () => {
    const calls = serve('assistant');
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    const organizations = (await within(panel).findByText('Организации')).closest('section')!;
    fireEvent.click(await within(organizations).findByRole('button', { name: 'исполнитель' }));

    expect(
      await within(organizations).findByRole('combobox', {
        name: 'Роль: Центр космического мониторинга',
      }),
    ).toHaveValue('executor');
    const board = screen.getByRole('region', { name: 'В работе' });
    const tile = within(board)
      .getByText('Постановление о порядке обмена геоданными')
      .closest('article')!;
    await waitFor(() => expect(within(tile).getByText('Центр — исполнитель')).toBeInTheDocument());
    expect(calls.find((call) => call.method === 'PUT')).toEqual({
      method: 'PUT',
      path: `${BASE}/pr-geodata/organizations/o-center`,
      body: { role: 'executor', version: null },
    });

    fireEvent.change(
      within(organizations).getByRole('combobox', { name: 'Роль: Центр космического мониторинга' }),
      { target: { value: 'co_executor' } },
    );
    await waitFor(() =>
      expect(calls.filter((call) => call.method === 'PUT').at(-1)?.body).toEqual({
        role: 'co_executor',
        version: 1,
      }),
    );

    fireEvent.click(
      await within(organizations).findByRole('button', {
        name: 'Убрать: Центр космического мониторинга',
      }),
    );
    await waitFor(() =>
      expect(calls.find((call) => call.method === 'DELETE')?.path).toBe(
        `${BASE}/pr-geodata/organizations/o-center?version=2`,
      ),
    );
    expect(await within(organizations).findByText('Организации не указаны')).toBeInTheDocument();
  });

  it('новая организация — название, вид и роль; головное ведомство одно', async () => {
    const calls = serve('assistant');
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    const organizations = (await within(panel).findByText('Организации')).closest('section')!;

    // Сначала чужое головное ведомство — из справочника.
    fireEvent.click(within(organizations).getByRole('button', { name: /Добавить организацию/ }));
    fireEvent.change(within(organizations).getByLabelText('Название организации'), {
      target: { value: 'эколог' },
    });
    fireEvent.click(
      await within(organizations).findByRole('button', { name: /Министерство экологии/ }),
    );
    fireEvent.change(within(organizations).getByLabelText('Роль'), {
      target: { value: 'lead_agency' },
    });
    fireEvent.click(within(organizations).getByRole('button', { name: 'Добавить' }));
    expect(
      await within(organizations).findByText(/Головное ведомство — не агентство/),
    ).toBeVisible();

    // Затем новая организация: головное ведомство уже занято.
    fireEvent.click(within(organizations).getByRole('button', { name: /Добавить организацию/ }));
    fireEvent.change(within(organizations).getByLabelText('Название организации'), {
      target: { value: 'Министерство здравоохранения' },
    });
    fireEvent.click(
      within(organizations).getByRole('button', {
        name: 'Новая организация «Министерство здравоохранения»',
      }),
    );
    const role = within(organizations).getByLabelText('Роль');
    expect(within(role).getByRole('option', { name: 'головное ведомство' })).toBeDisabled();
    fireEvent.click(within(organizations).getByRole('button', { name: 'Завести и добавить' }));

    expect(
      await within(organizations).findByRole('combobox', {
        name: 'Роль: Министерство здравоохранения',
      }),
    ).toHaveValue('customer');
    expect(
      calls.find((call) => call.method === 'POST' && call.path === '/api/v1/organizations')?.body,
    ).toEqual({
      name: 'Министерство здравоохранения',
      kind: 'ministry',
    });
    expect(calls.filter((call) => call.method === 'PUT').map((call) => call.body)).toEqual([
      { role: 'lead_agency', version: null },
      { role: 'customer', version: null },
    ]);
  });

  it('сведения — направление и регион из справочников', async () => {
    const calls = serve('assistant');
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    const details = (await within(panel).findByText('Сведения')).closest('section')!;
    fireEvent.click(within(details).getByRole('button', { name: 'Изменить' }));

    fireEvent.change(await within(details).findByLabelText('Направление'), {
      target: { value: 'monitoring' },
    });
    fireEvent.change(within(details).getByLabelText('Регион'), {
      target: { value: 'tashkent_city' },
    });
    fireEvent.change(within(details).getByLabelText('Описание'), {
      target: { value: 'Порядок обмена данными между ведомствами' },
    });
    fireEvent.click(within(details).getByRole('button', { name: 'Сохранить' }));

    // Сначала форма закрывается — иначе «Космический мониторинг» найдётся в её списке.
    await waitFor(() =>
      expect(within(details).queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument(),
    );
    expect(within(details).getByText('Космический мониторинг')).toBeInTheDocument();
    expect(within(details).getByText('город Ташкент')).toBeInTheDocument();
    expect(
      within(details).getByText('Порядок обмена данными между ведомствами'),
    ).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith('/details'))).toEqual({
      method: 'PUT',
      path: `${BASE}/pr-geodata/details`,
      body: {
        title: 'Постановление о порядке обмена геоданными',
        responsible_id: 'p-yusupova',
        direction_code: 'monitoring',
        region_code: 'tashkent_city',
        description: 'Порядок обмена данными между ведомствами',
        version: 4,
      },
    });
  });

  it('руководитель видит организации и сведения без правки', async () => {
    serve('leader');
    renderProjects();

    fireEvent.click(
      (await screen.findAllByRole('button', { name: /Постановление о порядке/ }))[0]!,
    );
    const panel = await screen.findByRole('dialog');
    await within(panel).findByText('Организации');
    expect(
      within(panel).queryByRole('button', { name: /Добавить организацию/ }),
    ).not.toBeInTheDocument();
    const details = within(panel).getByText('Сведения').closest('section')!;
    expect(within(details).queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument();
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

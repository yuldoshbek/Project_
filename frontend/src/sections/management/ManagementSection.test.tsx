/**
 * «Управление» против настоящего состава ответов бэкенда.
 *
 * Раздел падал целиком, когда бэкенд перестал отдавать приоритеты: интерфейс ждал старый
 * состав справочников. Здесь проверяется новый состав, скрытие действий записи у
 * руководителя и то, что расхождение одного ответа гасит одну карточку, а не раздел.
 *
 * Сеть подменена на уровне `fetch`: так проверяется и клиент API, а не только отрисовка.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type {
  CurrentUser,
  Dictionaries,
  DictionaryEntry,
  Health,
  StatusEntry,
} from '@/shared/api/orbita';

import { ManagementSection } from './ManagementSection';

function entry(code: string, ru: string): DictionaryEntry {
  return {
    id: `id-${code}`,
    code,
    name: { ru, uz_cyrl: ru, uz_latn: ru },
    sort_order: 1,
    is_active: true,
  };
}

function status(code: string, ru: string): StatusEntry {
  return { ...entry(code, ru), color: 'grey', is_terminal: false };
}

const DICTIONARIES: Dictionaries = {
  project_types: [
    entry('monitoring', 'Цикл мониторинга'),
    entry('normative', 'Нормативный акт'),
    entry('standard', 'Стандарт'),
    entry('platform', 'Платформа или ИТ'),
  ],
  task_types: [entry('tz', 'ТЗ'), entry('review', 'Рассмотрение и визирование')],
  directions: [entry('earth', 'Зондирование Земли')],
  regions: [entry('tashkent', 'Ташкент'), entry('samarkand', 'Самарканд')],
  project_statuses: [
    { ...status('active', 'В работе'), requires_reason: false },
    { ...status('paused', 'Приостановлен'), requires_reason: true },
  ],
  task_statuses: [status('new', 'Новая'), status('done', 'Сделана'), status('overdue', 'Ждёт')],
};

const HEALTH: Health = {
  status: 'ok',
  commit: 'c482ff4',
  env: 'test',
  time: new Date().toISOString(),
};

function user(canWrite: boolean): CurrentUser {
  return {
    id: 'user-1',
    full_name: canWrite ? 'Помощник' : 'Руководитель',
    role: canWrite ? 'assistant' : 'leader',
    locale: 'ru',
    timezone: 'Asia/Tashkent',
    can_write: canWrite,
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

/** Подменить сеть: путь → тело ответа. Неизвестный путь отвечает 404. */
function serve(routes: Record<string, unknown>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    return Promise.resolve(
      path in routes ? reply(200, routes[path]) : reply(404, { detail: `нет подмены ${path}` }),
    );
  });
}

function requestedPaths(fetchMock: ReturnType<typeof serve>): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ManagementSection />
    </QueryClientProvider>,
  );
}

/** Карточка по её заголовку: всё, что проверяется, проверяется внутри неё. */
function card(title: string): HTMLElement {
  const section = screen.getByRole('heading', { name: title }).closest('section');
  if (!section) throw new Error(`нет карточки «${title}»`);
  return section;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('справочники', () => {
  it('показаны плитками в составе ответа бэкенда, приоритетов нет', async () => {
    serve({
      '/api/me': user(true),
      '/api/v1/dictionaries': DICTIONARIES,
      '/api/health': HEALTH,
      '/api/access/sessions/assistant': [],
      '/api/access/sessions/leader': [],
    });
    renderSection();

    await screen.findByText('Типы проектов');
    const dictionaries = card('Справочники');

    const expected = [
      ['Типы проектов', '4', 'Цикл мониторинга, Нормативный акт, Стандарт'],
      ['Типы задач', '2', 'ТЗ, Рассмотрение и визирование'],
      ['Направления', '1', 'Зондирование Земли'],
      ['Регионы', '2', 'Ташкент, Самарканд'],
      ['Статусы проектов', '2', 'В работе, Приостановлен'],
      ['Статусы задач', '3', 'Новая, Сделана, Ждёт'],
    ] as const;

    for (const [label, count, preview] of expected) {
      const tile = within(dictionaries).getByText(label).parentElement;
      if (!tile) throw new Error(`нет плитки «${label}»`);
      expect(within(tile).getByText(count)).toBeInTheDocument();
      expect(within(tile).getByText(preview)).toBeInTheDocument();
    }

    expect(within(dictionaries).queryByText('Приоритеты')).not.toBeInTheDocument();
    expect(screen.queryByText(/⟨/)).not.toBeInTheDocument();
  });

  it('старый состав ответа гасит одну карточку, а не раздел', async () => {
    // React сообщает о пойманной ошибке в консоль — здесь это ожидаемый шум.
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    serve({
      '/api/me': user(true),
      '/api/v1/dictionaries': {
        directions: DICTIONARIES.directions,
        project_statuses: DICTIONARIES.project_statuses,
        task_statuses: DICTIONARIES.task_statuses,
        priorities: [entry('high', 'Высокий')],
      },
      '/api/health': HEALTH,
      '/api/access/sessions/assistant': [],
      '/api/access/sessions/leader': [],
    });
    renderSection();

    await screen.findByText(/Не удалось показать/);
    expect(within(card('Справочники')).getByRole('alert')).toBeInTheDocument();

    // Соседние карточки работают: состояние системы и ссылки на месте.
    expect(await within(card('Состояние системы')).findByText('c482ff4')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Перевыпустить ссылку' })).toHaveLength(2);
    expect(screen.queryByText('Something went wrong!')).not.toBeInTheDocument();
  });
});

describe('действия записи', () => {
  it('помощник видит перевыпуск ссылок и устройства', async () => {
    const fetchMock = serve({
      '/api/me': user(true),
      '/api/v1/dictionaries': DICTIONARIES,
      '/api/health': HEALTH,
      '/api/access/sessions/assistant': [],
      '/api/access/sessions/leader': [],
    });
    renderSection();

    expect(await screen.findAllByRole('button', { name: 'Перевыпустить ссылку' })).toHaveLength(2);
    expect(requestedPaths(fetchMock)).toContain('/api/access/sessions/assistant');
    expect(screen.queryByText('Ссылки доступа и устройства ведёт помощник.')).toBeNull();
  });

  it('руководителю их не показывают и не запрашивают: без кнопок и отказов 403', async () => {
    const fetchMock = serve({
      '/api/me': user(false),
      '/api/v1/dictionaries': DICTIONARIES,
      '/api/health': HEALTH,
    });
    renderSection();

    await screen.findByText('Ссылки доступа и устройства ведёт помощник.');
    await within(card('Справочники')).findByText('Типы проектов');
    await within(card('Состояние системы')).findByText('c482ff4');

    expect(screen.queryByRole('button', { name: 'Перевыпустить ссылку' })).toBeNull();
    expect(screen.queryByText('Устройства с открытым доступом')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(requestedPaths(fetchMock).filter((path) => path.startsWith('/api/access/'))).toEqual([]);
  });
});

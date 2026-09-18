/**
 * Доска проектов (ORB-019).
 *
 * Пять обещаний доски, и каждое ломается так, что доска выглядит рабочей.
 *
 * **Перенос доходит до сервера.** Карточка, переехавшая только на экране, после первой же
 * перезагрузки оказывается на старом месте — и это обнаруживается через день.
 *
 * **Отказ возвращает карточку.** Иначе на доске проект в одной колонке, в базе — в другой, и
 * отчёт руководителю строится по базе.
 *
 * **Пауза и отмена спрашивают причину до переноса.** Проверяется и то, что отказ от ввода
 * ничего не отправляет: запрос без причины сервер отклонит, а карточка успеет прыгнуть туда
 * и обратно.
 *
 * **Перенос возможен без перетаскивания.** Перетаскивание недоступно с клавиатуры, и
 * доска, где его нечем заменить, закрыта для части людей (WCAG 2.2, 2.5.7). Поэтому все
 * переносы здесь делаются полем на карточке — тем самым путём, которым пользуется
 * клавиатура. Само перетаскивание мышью проверяется вживую: в jsdom у элементов нет
 * размеров, и тест «перетащил» проверял бы только подделку координат.
 *
 * **Руководитель ничего не переносит** (ADR-0011).
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Mode } from '../../shared/mode/ModeContext';
import { WithMode } from '../../testing/WithMode';
import type { Project } from './api';
import { ProjectsPage } from './ProjectsPage';

const NAMES = (ru: string) => ({ ru, uz_cyrl: ru, uz_latn: ru });

const DICTIONARIES = {
  directions: [{ id: 'dir-1', code: 'space', name: NAMES('Космический мониторинг') }],
  // Порядок в ответе — порядок колонок. Намеренно не алфавитный: доска обязана брать его
  // из справочника, а не сортировать сама.
  project_statuses: [
    { id: 's-1', code: 'initiation', name: NAMES('Инициация'), requires_reason: false },
    { id: 's-2', code: 'in_progress', name: NAMES('В работе'), requires_reason: false },
    { id: 's-3', code: 'on_hold', name: NAMES('Приостановлен'), requires_reason: true },
  ],
  task_statuses: [],
  priorities: [{ id: 'pr-1', code: 'urgent', name: NAMES('Срочно') }],
};

const STATION: Project = {
  id: 'p-1',
  code: 'PRJ-2026-001',
  title: 'Приёмная станция ДЗЗ',
  description: null,
  kind: 'project',
  share_externally: true,
  status_code: 'in_progress',
  status_reason: null,
  priority_code: 'urgent',
  direction_id: 'dir-1',
  curator_person_id: null,
  started_on: '2026-01-15',
  due_on: '2026-08-28',
  finished_on: null,
  progress_pct: 80,
  progress_mode: 'auto',
  budget_note: null,
  impediment: null,
  impediment_updated_at: null,
  impediment_is_stale: false,
  impediment_is_active: false,
  health: 'red',
};

const CATALOG: Project = {
  ...STATION,
  id: 'p-2',
  code: 'PRJ-2026-005',
  title: 'Каталог спутниковых снимков',
  status_code: 'initiation',
  health: 'green',
};

const fetchMock = vi.fn();

/** Проекты «на сервере». Изменение через PATCH меняет их — как настоящая база. */
let stored: Project[] = [];
/** Ответ сервера на следующий PATCH, если тест хочет отказ. */
let refusal: { status: number; detail: string } | null = null;

function answer(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function patches(): { url: string; body: Record<string, unknown> }[] {
  return fetchMock.mock.calls
    .filter((call) => (call[1] as RequestInit | undefined)?.method === 'PATCH')
    .map((call) => ({
      url: String(call[0]),
      body: JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>,
    }));
}

function renderAt(path: string, session: Mode = 'leader') {
  const router = createMemoryRouter([{ path: '/projects', element: <ProjectsPage /> }], {
    initialEntries: [path],
  });
  render(
    <WithMode mode={session}>
      <RouterProvider router={router} />
    </WithMode>,
  );
  return router;
}

function asAssistant(path: string) {
  // Помощник — сессия по умолчанию у обёртки.
  const router = createMemoryRouter([{ path: '/projects', element: <ProjectsPage /> }], {
    initialEntries: [path],
  });
  render(
    <WithMode>
      <RouterProvider router={router} />
    </WithMode>,
  );
  return router;
}

const column = (name: string) => screen.getByRole('region', { name });

beforeEach(() => {
  stored = [structuredClone(STATION), structuredClone(CATALOG)];
  refusal = null;
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes('/dictionaries')) return answer(DICTIONARIES);
    if (init?.method === 'PATCH') {
      if (refusal !== null) {
        return answer(
          { type: '/problems/rule-violation', title: 'Отказ', detail: refusal.detail },
          refusal.status,
        );
      }
      const id = url.split('/projects/')[1];
      const body = JSON.parse(String(init.body)) as Partial<Project>;
      stored = stored.map((item) => (item.id === id ? { ...item, ...body } : item));
      return answer(stored.find((item) => item.id === id));
    }
    return answer(stored);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('доска проектов', () => {
  it('открывается по ссылке: вид живёт в адресе', async () => {
    asAssistant('/projects?view=board');

    await screen.findByText('Каталог спутниковых снимков');
    expect(
      within(column('Инициация')).getByText('Каталог спутниковых снимков'),
    ).toBeInTheDocument();
    expect(within(column('В работе')).getByText('Приёмная станция ДЗЗ')).toBeInTheDocument();
  });

  it('переключатель вида пишет вид в адрес, а список не оставляет параметра', async () => {
    const user = userEvent.setup();
    const router = asAssistant('/projects');

    await screen.findByText('Приёмная станция ДЗЗ');
    await user.click(screen.getByRole('button', { name: 'Доска' }));
    await waitFor(() => {
      expect(router.state.location.search).toContain('view=board');
    });

    await user.click(screen.getByRole('button', { name: 'Список' }));
    await waitFor(() => {
      expect(router.state.location.search).not.toContain('view');
    });
  });

  it('вид не уходит на сервер вместе с фильтрами', async () => {
    asAssistant('/projects?view=board&health=red');

    await screen.findByText('Приёмная станция ДЗЗ');
    const listCall = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .find((url) => url.includes('/projects') && !url.includes('/dictionaries'));
    expect(listCall).toContain('health=red');
    expect(listCall).not.toContain('view=');
  });

  it('колонки идут в порядке справочника и считают свои карточки', async () => {
    asAssistant('/projects?view=board');

    await screen.findByText('Приёмная станция ДЗЗ');
    const names = screen.getAllByRole('region').map((region) => region.getAttribute('aria-label'));
    expect(names).toEqual(['Инициация', 'В работе', 'Приостановлен']);
    expect(within(column('Приостановлен')).getByText('Пусто')).toBeInTheDocument();
  });

  it('перенос уходит на сервер, и карточка переезжает', async () => {
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Каталог спутниковых снимков')).closest('article');
    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'in_progress',
    );

    await waitFor(() => {
      expect(
        within(column('В работе')).getByText('Каталог спутниковых снимков'),
      ).toBeInTheDocument();
    });
    expect(patches()).toEqual([
      { url: '/api/v1/projects/p-2', body: { status_code: 'in_progress' } },
    ]);
  });

  it('отказ сервера возвращает карточку и объясняет словами сервера', async () => {
    const user = userEvent.setup();
    refusal = { status: 422, detail: 'Плановый срок завершения не может быть раньше даты начала' };
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Каталог спутниковых снимков')).closest('article');
    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'in_progress',
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Каталог спутниковых снимков');
    expect(alert).toHaveTextContent('не может быть раньше даты начала');
    await waitFor(() => {
      expect(
        within(column('Инициация')).getByText('Каталог спутниковых снимков'),
      ).toBeInTheDocument();
    });
  });

  it('пауза спрашивает причину, а отказ от ввода не отправляет ничего', async () => {
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Приёмная станция ДЗЗ')).closest('article');
    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'on_hold',
    );

    const dialog = await screen.findByRole('dialog', { name: 'Причина статуса «Приостановлен»' });
    await user.click(within(dialog).getByRole('button', { name: 'Не переносить' }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(patches()).toEqual([]);
    expect(within(column('В работе')).getByText('Приёмная станция ДЗЗ')).toBeInTheDocument();
  });

  it('пустую или пробельную причину отправить нельзя', async () => {
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Приёмная станция ДЗЗ')).closest('article');
    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'on_hold',
    );

    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Перенести' });
    expect(confirm).toBeDisabled();

    await user.type(within(dialog).getByLabelText('Причина'), '   ');
    expect(confirm).toBeDisabled();
  });

  it('причина уходит вместе с переносом и видна на карточке', async () => {
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Приёмная станция ДЗЗ')).closest('article');
    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'on_hold',
    );

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Причина'), 'Ждём разъяснений Минюста');
    await user.click(within(dialog).getByRole('button', { name: 'Перенести' }));

    await waitFor(() => {
      expect(
        within(column('Приостановлен')).getByText('Причина: Ждём разъяснений Минюста'),
      ).toBeInTheDocument();
    });
    expect(patches()).toEqual([
      {
        url: '/api/v1/projects/p-1',
        body: { status_code: 'on_hold', status_reason: 'Ждём разъяснений Минюста' },
      },
    ]);
  });

  it('руководителю доска открывается только для чтения', async () => {
    renderAt('/projects?view=board', 'leader');

    await screen.findByText('Приёмная станция ДЗЗ');
    expect(screen.queryByLabelText('Перенести в колонку')).toBeNull();
    // Смотреть — его работа: карточки и светофор на месте.
    expect(screen.getByRole('img', { name: 'Красная зона' })).toBeInTheDocument();
  });

  it('срок на карточке — по времени агентства и в привычном виде', async () => {
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Приёмная станция ДЗЗ')).closest('article');
    expect(within(card as HTMLElement).getByText('28.08.2026')).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText('80%')).toBeInTheDocument();
  });
  it('карточка переезжает сразу, не дожидаясь ответа сервера', async () => {
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Каталог спутниковых снимков')).closest('article');

    // Ответ на перенос не придёт никогда: переехать карточка может только сама.
    const answering = fetchMock.getMockImplementation() as (
      url: string,
      init?: RequestInit,
    ) => Promise<Response>;
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      init?.method === 'PATCH' ? new Promise<Response>(() => {}) : answering(url, init),
    );

    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'in_progress',
    );

    await waitFor(() => {
      expect(
        within(column('В работе')).getByText('Каталог спутниковых снимков'),
      ).toBeInTheDocument();
    });
  });

  it('связь пропала — карточка возвращается, даже когда портфель перечитать нельзя', async () => {
    // Самый вероятный отказ — не ответ сервера «нельзя», а отсутствие связи. Тогда не
    // удаётся и перечитать портфель, и вернуть карточку на место может только сама доска.
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Каталог спутниковых снимков')).closest('article');
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));

    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'in_progress',
    );

    expect(
      await screen.findByText(/Не удалось перенести «Каталог спутниковых снимков»/),
    ).toBeInTheDocument();
    expect(
      within(column('Инициация')).getByText('Каталог спутниковых снимков'),
    ).toBeInTheDocument();
  });

  it('Escape закрывает вопрос о причине и ничего не переносит', async () => {
    const user = userEvent.setup();
    asAssistant('/projects?view=board');

    const card = (await screen.findByText('Приёмная станция ДЗЗ')).closest('article');
    await user.selectOptions(
      within(card as HTMLElement).getByLabelText('Перенести в колонку'),
      'on_hold',
    );
    await screen.findByRole('dialog');

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(patches()).toEqual([]);
  });
});

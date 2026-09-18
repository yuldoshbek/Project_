/**
 * База задач (ORB-020).
 *
 * Три обещания экрана, и каждое ломается незаметно.
 *
 * Первое: просрочка — выделение, а не статус (ADR-0004). Сломать его легко и соблазнительно:
 * достаточно написать в колонке «Статус» слово «просрочена», и экран станет читаться лучше,
 * а система потеряет, чем задача была до наступления срока. Поэтому проверяется не цвет, а
 * то, что рядом с пометкой о просрочке стоит собственный статус задачи.
 *
 * Второе: вид живёт в адресе. Отфильтрованная выборка — это то, что помощник присылает
 * руководителю ссылкой; сортировка и набор колонок туда же, иначе по ссылке открывается
 * что-то другое.
 *
 * Третье: файл собирает сервер. Браузеру нечем проверить гриф (ADR-0007), и собери он файл
 * сам из того, что уже на странице, — проверка оказалась бы нигде.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ACTOR_HEADER } from '../../shared/api/client';
import { WithMode } from '../../testing/WithMode';
import { TasksPage } from './TasksPage';

const DICTIONARIES = {
  directions: [
    {
      id: 'dir-1',
      code: 'space_monitoring',
      name: { ru: 'Космический мониторинг', uz_cyrl: 'Космик мониторинг', uz_latn: 'Kosmik' },
    },
  ],
  project_statuses: [],
  task_statuses: [
    {
      id: 'ts-1',
      code: 'in_progress',
      name: { ru: 'В работе', uz_cyrl: 'Ишда', uz_latn: 'Ishda' },
    },
    { id: 'ts-2', code: 'new', name: { ru: 'Новая', uz_cyrl: 'Янги', uz_latn: 'Yangi' } },
  ],
  priorities: [
    {
      id: 'pr-1',
      code: 'urgent',
      name: { ru: 'Срочно', uz_cyrl: 'Шошилинч', uz_latn: 'Shoshilinch' },
    },
  ],
};

const PEOPLE = [{ id: 'per-1', full_name: 'Рахимов Р.' }];

const OVERDUE = {
  id: 't-1',
  code: 'TSK-00001',
  project_id: 'p-1',
  title: 'Смонтировать антенну',
  assignee_person_id: 'per-1',
  status: 'in_progress' as const,
  priority_code: 'urgent',
  due_at: '2026-09-01T12:00:00Z',
  completed_at: null,
  is_control: false,
  is_overdue: true,
  days_overdue: 3,
  checklist_done: 1,
  checklist_total: 4,
  checklist_percent: 25,
};

const ON_TIME = {
  ...OVERDUE,
  id: 't-2',
  code: 'TSK-00002',
  title: 'Согласовать смету',
  status: 'new' as const,
  is_overdue: false,
  days_overdue: 0,
  // Задача без чек-листа: доля отсутствует, а не равна нулю.
  checklist_done: 0,
  checklist_total: 0,
  checklist_percent: null,
};

const fetchMock = vi.fn();

function renderAt(path: string) {
  const router = createMemoryRouter([{ path: '/tasks', element: <TasksPage /> }], {
    initialEntries: [path],
  });
  render(
    <WithMode>
      <RouterProvider router={router} />
    </WithMode>,
  );
  return router;
}

/** Адрес последнего запроса за задачами. Именно он показывает, что фильтры дошли. */
function lastTasksUrl(): string {
  const calls = fetchMock.mock.calls.filter(
    (call) => typeof call[0] === 'string' && (call[0] as string).includes('/tasks'),
  );
  return (calls.at(-1)?.[0] ?? '') as string;
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string) => {
    if (url.includes('/dictionaries')) {
      return Promise.resolve(new Response(JSON.stringify(DICTIONARIES), { status: 200 }));
    }
    if (url.includes('/people')) {
      return Promise.resolve(new Response(JSON.stringify(PEOPLE), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify([OVERDUE, ON_TIME]), { status: 200 }));
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('база задач', () => {
  it('показывает задачу с номером, названием и сроком', async () => {
    renderAt('/tasks');

    const row = (await screen.findByText('TSK-00001')).closest('tr');
    expect(row).not.toBeNull();

    expect(within(row as HTMLElement).getByText('Смонтировать антенну')).toBeInTheDocument();
    // Срок — по времени агентства и в привычном виде, а не срезанной строкой UTC.
    expect(within(row as HTMLElement).getByText('01.09.2026')).toBeInTheDocument();
  });

  it('просроченная задача сохраняет свой статус, а не подменяет его', async () => {
    renderAt('/tasks');

    const row = (await screen.findByText('Смонтировать антенну')).closest('tr');
    expect(row).not.toBeNull();

    // Пометка о просрочке есть...
    expect(within(row as HTMLElement).getByText(/Просрочена на 3 дня/)).toBeInTheDocument();
    // ...и статус при этом остался собственным: задача «в работе» и просрочена сразу.
    expect(within(row as HTMLElement).getByText('В работе')).toBeInTheDocument();
  });

  it('просрочка — выделение строки, а не отдельная запись в списке статусов', async () => {
    renderAt('/tasks');

    await screen.findByText('Смонтировать антенну');

    const overdueRow = screen.getByText('Смонтировать антенну').closest('tr');
    const onTimeRow = screen.getByText('Согласовать смету').closest('tr');
    expect(overdueRow?.className).not.toBe(onTimeRow?.className);

    // Название колонки звучит на экране трижды — фильтром, заголовком сортировки и
    // галочкой видимости, — поэтому запрос уточняется ролью.
    const statuses = within(screen.getByRole('combobox', { name: 'Статус' })).getAllByRole(
      'option',
    );
    expect(statuses.map((option) => option.textContent)).toEqual([
      'Все статусы',
      'В работе',
      'Новая',
    ]);
  });

  it('фильтры из адреса применяются при открытии и сочетаются между собой', async () => {
    renderAt('/tasks?status=in_progress&priority_code=urgent&overdue=true');

    await waitFor(() => {
      expect(lastTasksUrl()).toContain('status=in_progress');
    });
    expect(lastTasksUrl()).toContain('priority_code=urgent');
    expect(lastTasksUrl()).toContain('overdue=true');
  });

  it('фильтр по куратору проекта — отдельный от исполнителя', async () => {
    const user = userEvent.setup();
    const router = renderAt('/tasks');

    await screen.findByText('TSK-00001');
    await user.selectOptions(screen.getByLabelText('Куратор проекта'), 'per-1');

    await waitFor(() => {
      expect(router.state.location.search).toContain('curator_person_id=per-1');
    });
    expect(router.state.location.search).not.toContain('assignee_person_id');
  });

  it('сортировка по колонке попадает в адрес и повторный щелчок разворачивает её', async () => {
    const user = userEvent.setup();
    const router = renderAt('/tasks');

    await screen.findByText('TSK-00001');
    const header = screen.getByRole('button', { name: 'Приоритет' });

    await user.click(header);
    await waitFor(() => {
      expect(router.state.location.search).toContain('sort_by=priority_code');
    });
    expect(router.state.location.search).toContain('descending=false');

    await user.click(header);
    await waitFor(() => {
      expect(router.state.location.search).toContain('descending=true');
    });
  });

  it('направление сортировки объявлено в разметке, а не только цветом', async () => {
    renderAt('/tasks?sort_by=due_at&descending=true');

    const header = await screen.findByRole('columnheader', { name: /Срок/ });

    expect(header).toHaveAttribute('aria-sort', 'descending');
  });

  it('снятая колонка исчезает из таблицы и остаётся снятой по ссылке', async () => {
    const user = userEvent.setup();
    const router = renderAt('/tasks');

    await screen.findByText('TSK-00001');
    expect(screen.getByRole('button', { name: 'Исполнитель' })).toBeInTheDocument();

    const group = screen.getByRole('group', { name: 'Видимые колонки' });
    await user.click(within(group).getByLabelText('Исполнитель'));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Исполнитель' })).not.toBeInTheDocument();
    });
    expect(router.state.location.search).toContain('hide=assignee');
  });

  it('снятый набор колонок восстанавливается из адреса', async () => {
    renderAt('/tasks?hide=priority,assignee');

    await screen.findByText('TSK-00001');

    expect(screen.queryByRole('button', { name: 'Приоритет' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Исполнитель' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Название' })).toBeInTheDocument();
  });

  it('прогресс чек-листа виден в списке числом и полосой', async () => {
    renderAt('/tasks');

    const row = (await screen.findByText('Смонтировать антенну')).closest('tr');
    expect(row).not.toBeNull();

    expect(within(row as HTMLElement).getByText('1/4')).toBeInTheDocument();
    expect(within(row as HTMLElement).getByRole('progressbar')).toHaveAttribute(
      'aria-valuenow',
      '25',
    );
  });

  it('у задачи без чек-листа ячейка пуста, а не «0 %»', async () => {
    renderAt('/tasks');

    await screen.findByText('Смонтировать антенну');
    const row = screen.getByText('Согласовать смету').closest('tr');

    // Ноль означает «взялись и не сделали» — тревожный знак. Отсутствие чек-листа не
    // сообщает ни о чём, и рисовать вместо него пустую полосу нельзя.
    expect(within(row as HTMLElement).queryByRole('progressbar')).not.toBeInTheDocument();
    expect(within(row as HTMLElement).queryByText('0/0')).not.toBeInTheDocument();
  });

  it('заголовок чек-листа не притворяется кнопкой сортировки', async () => {
    renderAt('/tasks');

    await screen.findByText('TSK-00001');

    // Сортировать по «1 из 2» и «50 из 100» нет порядка, полезного человеку. Кнопка,
    // которая молча ничего не делает, читается как поломка.
    expect(screen.queryByRole('button', { name: 'Чек-лист' })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Чек-лист' })).toBeInTheDocument();
  });

  it('файл просит у сервера с теми же фильтрами, а не собирает из строк на экране', async () => {
    const user = userEvent.setup();
    renderAt('/tasks?status=in_progress');

    await screen.findByText('TSK-00001');
    await user.click(screen.getByRole('button', { name: 'Выгрузить в файл' }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (item) => typeof item[0] === 'string' && (item[0] as string).includes('export.csv'),
      );
      expect(call?.[0]).toContain('status=in_progress');
    });
  });

  it('запрос за файлом уходит подписанным: иначе выгрузка окажется в журнале ничьей', async () => {
    const user = userEvent.setup();
    renderAt('/tasks');

    await screen.findByText('TSK-00001');
    await user.click(screen.getByRole('button', { name: 'Выгрузить в файл' }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (item) => typeof item[0] === 'string' && (item[0] as string).includes('export.csv'),
      );
      expect(call).toBeDefined();
      const headers = (call?.[1] as RequestInit | undefined)?.headers as Record<string, string>;
      expect(headers[ACTOR_HEADER]).toBe('assistant');
    });
  });

  it('несобранный файл объясняется словами, а не тишиной', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('export.csv')) {
        return Promise.resolve(new Response('{}', { status: 500 }));
      }
      if (url.includes('/dictionaries')) {
        return Promise.resolve(new Response(JSON.stringify(DICTIONARIES), { status: 200 }));
      }
      if (url.includes('/people')) {
        return Promise.resolve(new Response(JSON.stringify(PEOPLE), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify([OVERDUE]), { status: 200 }));
    });

    renderAt('/tasks');
    await screen.findByText('TSK-00001');
    await user.click(screen.getByRole('button', { name: 'Выгрузить в файл' }));

    expect(await screen.findByText(/Не удалось собрать файл/)).toBeInTheDocument();
  });
});

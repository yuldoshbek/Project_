/**
 * Портфель проектов (ORB-019).
 *
 * Главное здесь — не таблица, а адрес. Отфильтрованный список это то, что помощник
 * присылает руководителю ссылкой; состояние, которое нельзя передать ссылкой,
 * приходится пересказывать словами.
 *
 * Второе — цвет светофора приходит с сервера и не пересчитывается здесь: два места с
 * одним правилом однажды разойдутся, и два экрана начнут показывать разное (ADR-0005).
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { WithMode } from '../../testing/WithMode';
import { ProjectsPage } from './ProjectsPage';

const DICTIONARIES = {
  directions: [
    {
      id: 'dir-1',
      code: 'space_monitoring',
      name: { ru: 'Космический мониторинг', uz_cyrl: 'Космик мониторинг', uz_latn: 'Kosmik' },
    },
  ],
  project_statuses: [
    {
      id: 'st-1',
      code: 'in_progress',
      name: { ru: 'В работе', uz_cyrl: 'Ишда', uz_latn: 'Ishda' },
    },
  ],
  priorities: [
    {
      id: 'pr-1',
      code: 'urgent',
      name: { ru: 'Срочно', uz_cyrl: 'Шошилинч', uz_latn: 'Shoshilinch' },
    },
  ],
};

const PROJECT = {
  id: 'p-1',
  code: 'PRJ-2026-001',
  title: 'Приёмная станция ДЗЗ',
  status_code: 'in_progress',
  priority_code: 'urgent',
  direction_id: 'dir-1',
  due_on: '2026-08-28',
  progress_pct: 80,
  impediment: 'Подрядчик не вышел на площадку',
  impediment_updated_at: '2026-09-09T10:00:00Z',
  impediment_is_stale: false,
  impediment_is_active: true,
  health: 'red' as const,
};

const fetchMock = vi.fn();

function renderAt(path: string) {
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

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string) =>
    Promise.resolve(
      new Response(JSON.stringify(url.includes('/dictionaries') ? DICTIONARIES : [PROJECT]), {
        status: 200,
      }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('портфель проектов', () => {
  it('показывает проект с номером, сроком и цветом, пришедшим с сервера', async () => {
    renderAt('/projects');

    expect(await screen.findByText('PRJ-2026-001')).toBeInTheDocument();
    expect(screen.getByText('Приёмная станция ДЗЗ')).toBeInTheDocument();
    // Срок — по времени агентства и в привычном виде, а не строкой ISO.
    expect(screen.getByText('28.08.2026')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '80');
  });

  it('строка «что мешает» видна прямо в списке', async () => {
    renderAt('/projects');

    expect(await screen.findByText('Подрядчик не вышел на площадку')).toBeInTheDocument();
  });

  it('фильтр из адреса применяется при открытии, а не только по клику', async () => {
    renderAt('/projects?health=red&search=станц');

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const projectCall = fetchMock.mock.calls.find(
      (call) => typeof call[0] === 'string' && (call[0] as string).includes('/projects'),
    );
    expect(projectCall?.[0]).toContain('health=red');
    expect(projectCall?.[0]).toContain('search=');
  });

  it('выбор фильтра попадает в адрес: ссылкой можно поделиться', async () => {
    const user = userEvent.setup();
    const router = renderAt('/projects');

    await screen.findByText('PRJ-2026-001');
    await user.selectOptions(screen.getByLabelText('Статус'), 'in_progress');

    await waitFor(() => {
      expect(router.state.location.search).toContain('status_code=in_progress');
    });
  });

  it('снятый фильтр исчезает из адреса, а не остаётся пустым', async () => {
    const user = userEvent.setup();
    const router = renderAt('/projects?status_code=in_progress');

    await screen.findByText('PRJ-2026-001');
    await user.selectOptions(screen.getByLabelText('Статус'), '');

    await waitFor(() => {
      expect(router.state.location.search).not.toContain('status_code');
    });
  });
});

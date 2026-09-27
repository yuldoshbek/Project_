/**
 * Экран «Задачи» против ответа API: строка с разбором, «Кто перегружен?» как фильтр,
 * карточка со статусом и чек-листом, руководитель без ввода, телефон без таблицы.
 *
 * Числа, группы и сам разбор строки считает сервер и проверяет `backend/tests/test_tasks.py`
 * и `test_capture.py`. Здесь — что экран делает с ответом и что уходит на сервер по касанию.
 * Сеть подменена на уровне `fetch`; «сервер» помнит статусы и чек-листы.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import type { ChecklistItem, ParsedLine, TaskCard } from './model';
import { TasksSection } from './TasksSection';
import { CHECKLISTS, ITEMS, detailOf, task, TRANSITIONS, view } from './test-data';

const BASE = '/api/v1/tasks';

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

const PARSED: ParsedLine = {
  title: 'Справка по паводкам',
  type_code: 'analytical_note',
  due_on: '2026-09-28',
  assignee_id: 'p-rakhimov',
  matched: { type: 'справк', due: 'завтра', assignee: 'Рахимову' },
};

function serve(role: 'leader' | 'assistant') {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const items: TaskCard[] = ITEMS.map((each) => ({ ...each }));
  const checklists: Record<string, ChecklistItem[]> = Object.fromEntries(
    Object.entries(CHECKLISTS).map(([id, list]) => [id, list.map((item) => ({ ...item }))]),
  );

  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    const [bare = path] = path.split('?');
    const item = /^\/api\/v1\/tasks\/([^/]+)\/checklist\/([^/]+)$/.exec(bare);

    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (method === 'GET' && path === BASE) return Promise.resolve(reply(200, view(items)));
    if (method === 'POST' && path === `${BASE}/parse`) return Promise.resolve(reply(200, PARSED));
    if (method === 'POST' && path === BASE) {
      const fresh = task({ id: 't-99', title: body.title, status: 'new' });
      items.push(fresh);
      return Promise.resolve(reply(201, detailOf(fresh)));
    }
    if (method === 'PUT' && bare.endsWith('/status')) {
      const id = bare.slice(BASE.length + 1, -'/status'.length);
      const found = items.find((each) => each.id === id)!;
      found.status = body.status;
      found.version += 1;
      return Promise.resolve(reply(204));
    }
    if (item && method === 'PUT') {
      const [, taskId = '', itemId = ''] = item;
      const found = checklists[taskId]!.find((each) => each.id === itemId)!;
      found.is_done = body.is_done;
      found.version += 1;
      return Promise.resolve(reply(204));
    }
    if (method === 'GET' && path.startsWith(`${BASE}/`)) {
      const id = path.slice(BASE.length + 1);
      const found = items.find((each) => each.id === id)!;
      return Promise.resolve(reply(200, detailOf(found, checklists[id] ?? [])));
    }
    return Promise.resolve(reply(404, { detail: `нет подмены ${method} ${path}` }));
  });
  return calls;
}

function renderTasks() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TasksSection />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('Задачи', () => {
  it('список по сроку и пометка «вымышленные данные»', async () => {
    serve('assistant');
    renderTasks();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Просрочено' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Без срока' })).toBeInTheDocument();
    // Готовые свёрнуты: список дел — про то, что делать.
    expect(screen.queryByText('Разработка ТЗ спутниковой группировки')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Показать готовые и отменённые: 1/ }));
    expect(screen.getByText('Разработка ТЗ спутниковой группировки')).toBeInTheDocument();
  });

  it('строка разбирается на сервере; поправленная подсказка уходит в новую задачу', async () => {
    const calls = serve('assistant');
    renderTasks();

    const line = await screen.findByLabelText('Новая задача строкой');
    fireEvent.change(line, { target: { value: 'завтра справка по паводкам, Рахимову' } });

    expect(
      await screen.findByText('Понято: Справка по паводкам', {}, { timeout: 2000 }),
    ).toBeInTheDocument();
    expect(calls.find((call) => call.path === `${BASE}/parse`)?.body).toEqual({
      text: 'завтра справка по паводкам, Рахимову',
    });
    const form = line.closest('form')!;
    const [type, assignee] = within(form).getAllByRole('combobox');
    expect(type).toHaveValue('analytical_note');
    expect(assignee).toHaveValue('p-rakhimov');

    fireEvent.change(assignee!, { target: { value: 'p-yusupova' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Добавить' }));

    expect(await screen.findByText(/Задача заведена: TSK-2026-0099/)).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'POST' && call.path === BASE)?.body).toEqual({
      title: 'Справка по паводкам',
      type_code: 'analytical_note',
      due_on: '2026-09-28',
      assignee_id: 'p-yusupova',
      project_id: null,
    });
    expect(line).toHaveValue('');
  });

  it('«Кто перегружен?» — касание оставляет задачи человека', async () => {
    serve('assistant');
    renderTasks();

    fireEvent.click(await screen.findByRole('button', { name: 'Показать задачи: Турсунов Б.' }));
    expect(await screen.findByText('Показаны задачи: Турсунов Б.')).toBeInTheDocument();
    expect(screen.getByText('Договор с исполнителем аэрофотосъёмки')).toBeInTheDocument();
    expect(screen.queryByText('Выезд на полигон в Джизаке')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Показать все' }));
    expect(await screen.findByText('Выезд на полигон в Джизаке')).toBeInTheDocument();
  });

  it('карточка: переходы от сервера, отметка и статус уходят с версией', async () => {
    const calls = serve('assistant');
    renderTasks();

    fireEvent.click(await screen.findByText('Выезд на полигон в Джизаке'));
    const panel = await screen.findByRole('dialog');
    const status = (await within(panel).findByText('Статус')).closest('section')!;
    expect(
      within(status)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(
      TRANSITIONS.in_progress.map(
        (each) =>
          ({ new: 'Новая', in_review: 'На проверке', done: 'Готова', cancelled: 'Отменена' })[
            each as 'new'
          ],
      ),
    );

    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Приборы калибровки' }));
    await waitFor(() => expect(within(panel).getByText('чек-лист 2/3')).toBeInTheDocument());
    expect(calls.find((call) => call.path.endsWith('/checklist/c-2'))).toEqual({
      method: 'PUT',
      path: `${BASE}/t-3/checklist/c-2`,
      body: { is_done: true, version: 1 },
    });

    fireEvent.click(within(status).getByRole('button', { name: 'На проверке' }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith('/status'))?.body).toEqual({
        status: 'in_review',
        version: 5,
      }),
    );
    await waitFor(() =>
      expect(
        within(status)
          .getAllByRole('button')
          .map((button) => button.textContent),
      ).toEqual(['В работе', 'Готова', 'Отменена']),
    );
  });

  it('руководитель смотрит: без строки ввода, смены статуса и отметок', async () => {
    serve('leader');
    renderTasks();

    await screen.findByText('Вымышленные данные');
    await waitFor(() =>
      expect(screen.queryByLabelText('Новая задача строкой')).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('Выезд на полигон в Джизаке'));
    const panel = await screen.findByRole('dialog');
    await within(panel).findByText('Чек-лист');
    expect(within(panel).queryByText('Статус')).not.toBeInTheDocument();
    expect(within(panel).getByRole('checkbox', { name: 'Транспорт' })).toBeDisabled();
    expect(within(panel).queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument();
  });

  it('на телефоне — без таблицы', async () => {
    setViewport({ width: 390 });
    serve('assistant');
    renderTasks();

    await screen.findByRole('region', { name: 'Просрочено' });
    expect(screen.queryByRole('tab', { name: 'Таблица' })).not.toBeInTheDocument();
  });
});

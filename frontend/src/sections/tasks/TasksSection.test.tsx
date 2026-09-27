/**
 * Экран «Задачи»: строка с разбором, «Кто перегружен?» как фильтр, карточка со статусом и
 * чек-листом, руководитель без ввода, телефон без таблицы.
 *
 * Данные — вымышленный сервер `demo.ts`; сеть подменена только для `/api/me`, откуда экран
 * узнаёт, помощник это или руководитель.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { demoTasks } from './demo';
import { TasksSection } from './TasksSection';

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

function serve(role: 'leader' | 'assistant') {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const found = path === '/api/me';
    return Promise.resolve({
      ok: found,
      status: found ? 200 : 404,
      statusText: '',
      json: () => Promise.resolve(found ? user(role) : { detail: `нет подмены ${path}` }),
    } as unknown as Response);
  });
}

function renderTasks() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TasksSection />
    </QueryClientProvider>,
  );
}

beforeEach(() => demoTasks.reset());
afterEach(() => vi.restoreAllMocks());

describe('Задачи', () => {
  it('список по сроку и пометка «вымышленные данные»', async () => {
    serve('assistant');
    renderTasks();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Просрочено' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Без срока' })).toBeInTheDocument();
    // Готовые свёрнуты: список дел — про то, что делать.
    expect(
      screen.getByRole('button', { name: /Показать готовые и отменённые/ }),
    ).toBeInTheDocument();
  });

  it('строка разбирается и заводит задачу с понятыми полями', async () => {
    serve('assistant');
    renderTasks();

    const line = await screen.findByLabelText('Новая задача строкой');
    fireEvent.change(line, {
      target: { value: 'завтра справка по паводкам, Рахимову' },
    });

    expect(
      await screen.findByText('Понято: Справка по паводкам', {}, { timeout: 2000 }),
    ).toBeInTheDocument();
    const form = line.closest('form')!;
    const [type, assignee] = within(form).getAllByRole('combobox');
    expect(type).toHaveValue('analytical_note');
    expect(assignee).toHaveValue('p-rakhimov');

    // Подсказку можно поправить до сохранения.
    fireEvent.change(assignee!, { target: { value: 'p-yusupova' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Добавить' }));

    expect(await screen.findByText(/Задача заведена: TSK-2026-/)).toBeInTheDocument();
    const created = demoTasks.view().items.find((task) => task.title === 'Справка по паводкам')!;
    expect(created).toMatchObject({
      assignee: { id: 'p-yusupova' },
      type: { code: 'analytical_note' },
      horizon: 'tomorrow',
    });
    expect(line).toHaveValue('');
  });

  it('«Кто перегружен?» — касание оставляет задачи человека', async () => {
    serve('assistant');
    renderTasks();

    fireEvent.click(await screen.findByRole('button', { name: 'Показать задачи: Турсунов Б.' }));

    expect(await screen.findByText('Показаны задачи: Турсунов Б.')).toBeInTheDocument();
    const own = demoTasks
      .view()
      .items.filter((task) => task.assignee?.id === 'p-tursunov' && task.horizon !== 'closed');
    for (const task of own) expect(screen.getByText(task.title)).toBeInTheDocument();
    expect(screen.queryByText('Выезд на полигон в Джизаке')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Показать все' }));
    expect(await screen.findByText('Выезд на полигон в Джизаке')).toBeInTheDocument();
  });

  it('карточка: статус — только разрешённые переходы, чек-лист отмечается касанием', async () => {
    serve('assistant');
    renderTasks();

    fireEvent.click(await screen.findByText('Выезд на полигон в Джизаке'));
    const panel = await screen.findByRole('dialog');

    const status = (await within(panel).findByText('Статус')).closest('section')!;
    // Из «В работе»: новая, на проверке, готова, отменена — и ничего больше.
    expect(
      within(status)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Новая', 'На проверке', 'Готова', 'Отменена']);

    const item = within(panel).getByRole('checkbox', { name: 'Приборы калибровки' });
    fireEvent.click(item);
    await waitFor(() => expect(within(panel).getByText('чек-лист 2/3')).toBeInTheDocument());

    fireEvent.click(within(status).getByRole('button', { name: 'На проверке' }));
    await waitFor(() =>
      expect(
        within(status)
          .getAllByRole('button')
          .map((button) => button.textContent),
      ).toEqual(['В работе', 'Готова', 'Отменена']),
    );
  });

  it('руководитель смотрит: без строки ввода, без смены статуса и отметок', async () => {
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

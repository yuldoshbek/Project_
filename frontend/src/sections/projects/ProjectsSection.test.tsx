/**
 * Экран «Проекты»: кто что может, пауза только с причиной, новый проект за два поля,
 * телефон без таблиц.
 *
 * Данные — вымышленный сервер `demo.ts`; сеть подменена только для `/api/me`, откуда экран
 * узнаёт, помощник это или руководитель.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { demoProjects } from './demo';
import { ProjectsSection } from './ProjectsSection';

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
    const body = path === '/api/me' ? user(role) : { detail: `нет подмены ${path}` };
    return Promise.resolve({
      ok: path === '/api/me',
      status: path === '/api/me' ? 200 : 404,
      statusText: '',
      json: () => Promise.resolve(body),
    } as unknown as Response);
  });
}

function renderProjects() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

beforeEach(() => demoProjects.reset());
afterEach(() => vi.restoreAllMocks());

describe('Проекты', () => {
  it('доска по статусам и пометка «вымышленные данные»', async () => {
    serve('assistant');
    renderProjects();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    for (const status of ['В работе', 'На паузе', 'Завершён', 'Отменён']) {
      expect(screen.getByRole('region', { name: status })).toBeInTheDocument();
    }
  });

  it('перенос в «На паузе» спрашивает причину и без неё не сохраняет', async () => {
    serve('assistant');
    renderProjects();

    const card = demoProjects.view().items.find((each) => each.status === 'in_progress')!;
    drop(await screen.findByRole('region', { name: 'На паузе' }), card.id);

    const dialog = await screen.findByRole('dialog');
    const save = within(dialog).getByRole('button', { name: 'Сохранить' });
    expect(save).toBeDisabled();

    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'Ждём финансирование' },
    });
    fireEvent.click(save);

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const paused = screen.getByRole('region', { name: 'На паузе' });
    expect(within(paused).getByText(card.title)).toBeInTheDocument();
    expect(within(paused).getByText('Причина: Ждём финансирование')).toBeInTheDocument();
  });

  it('новый проект — название и тип, вехи из шаблона', async () => {
    serve('assistant');
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
    fireEvent.click(submit);

    expect(await screen.findByText(/Проект заведён: PRJ-/)).toBeInTheDocument();
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
  });

  it('на телефоне — список по статусам, без таблицы и таймлайна', async () => {
    setViewport({ width: 390 });
    serve('assistant');
    renderProjects();

    const paused = await screen.findByRole('tab', { name: /На паузе/ });
    expect(screen.queryByRole('tab', { name: 'Таблица' })).not.toBeInTheDocument();

    fireEvent.click(paused);
    const onHold = demoProjects.view().items.filter((card) => card.status === 'on_hold');
    for (const card of onHold) expect(screen.getByText(card.title)).toBeInTheDocument();
  });
});

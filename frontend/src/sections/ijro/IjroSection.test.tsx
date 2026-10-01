/**
 * Ижро — обещания экрана на утверждение.
 *
 * Двенадцать вопросов с датой таблицы и действием; действие открывает тот же список, что
 * посчитан в ответе; на телефоне — список, не таблица; контрольная отметка — одно касание;
 * карточка показывает содержание и написание ФИО как в источнике; загрузку видит только
 * помощник, и повторное применение таблицы ничего не меняет.
 *
 * Сеть подменена на уровне `fetch`: `/api/v1/ijro…`, решения и вопросы по поручению отвечает
 * сервер в памяти (`test-server.ts`) по правилам настоящего, сессию — заготовка.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { IjroSection } from './IjroSection';
import { QUESTIONS } from './model';
import { FakeIjro, handle } from './test-server';

/** Адрес вместо маршрутизатора: вкладка раздела живёт в `?view=`. */
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

function user(role: 'assistant' | 'leader'): CurrentUser {
  return {
    id: `u-${role}`,
    full_name: role,
    role,
    locale: 'ru',
    timezone: 'Asia/Tashkent',
    can_write: role === 'assistant',
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

let server = new FakeIjro();

function serve(role: 'assistant' | 'leader') {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const raw = init?.body;
    // Файл таблицы уходит как есть, остальное — JSON.
    const body = raw instanceof Blob ? raw : raw ? (JSON.parse(String(raw)) as unknown) : undefined;
    const answer = handle(server, method, path, body, role);
    if (answer) return Promise.resolve(reply(answer[0], answer[1]));
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
}

function renderIjro() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IjroSection />
    </QueryClientProvider>,
  );
}

/** Строки реестра на экране: строки таблицы без заголовка. */
function tableRows() {
  return screen.getAllByRole('row').slice(1);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  route.set({});
  server = new FakeIjro();
});

describe('Ижро', () => {
  it('двенадцать вопросов, у каждого дата таблицы; руководитель «Загрузку» не видит', async () => {
    serve('leader');
    renderIjro();

    expect(
      await screen.findByRole('heading', { name: 'Что горит и что просрочено?' }),
    ).toBeVisible();
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getAllByRole('heading', { level: 2 })).toHaveLength(QUESTIONS.length);
    expect(within(panel).getAllByText(/^по таблице от \d{2}\.\d{2}\.\d{4}$/)).toHaveLength(
      QUESTIONS.length,
    );
    expect(screen.getByText('горит 4 · просрочено 3')).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByRole('tab', { name: 'Загрузка' })).not.toBeInTheDocument(),
    );
  });

  it('действие вопроса открывает тот же список, что посчитан в ответе', async () => {
    serve('leader');
    renderIjro();

    fireEvent.click(await screen.findByRole('button', { name: 'Кого поторопить' }));

    expect(screen.getByRole('tab', { name: 'Поручения' })).toHaveAttribute('aria-selected', 'true');
    expect(tableRows()).toHaveLength(7);
    expect(route.get()).toEqual({ view: 'assignments' });

    // Снятый отбор возвращает весь реестр.
    fireEvent.click(
      screen.getByRole('button', { name: 'Убрать отбор: Что горит и что просрочено?' }),
    );
    expect(tableRows().length).toBeGreaterThan(7);
  });

  it('на телефоне — список, таблицы нет (ТЗ 6)', async () => {
    setViewport({ width: 390 });
    route.set({ view: 'assignments' });
    serve('leader');
    renderIjro();

    expect(await screen.findByText(/^ПФ-155 · 3-банд$/)).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('контрольная отметка — одно касание в строке, и молчавший уходит из списка', async () => {
    serve('leader');
    renderIjro();

    fireEvent.click(await screen.findByRole('button', { name: 'Контрольная отметка' }));
    const before = tableRows().length;

    fireEvent.click(within(tableRows()[0]!).getByRole('button', { name: 'Связался' }));

    await waitFor(() => expect(tableRows()).toHaveLength(before - 1));
  });

  it('карточка: содержание и написание ФИО как в источнике, сопоставляет человек', async () => {
    route.set({ view: 'assignments' });
    serve('assistant');
    renderIjro();

    fireEvent.click(
      await screen.findByRole('button', { name: /^Алоқа операторлари билан сунъий йўлдош/ }),
    );

    const card = await screen.findByRole('dialog', { name: 'Карточка поручения' });
    expect(
      await within(card).findByText(
        'Алоқа операторлари билан сунъий йўлдош каналларидан фойдаланиш бўйича ҳамкорлик меморандуми имзолансин.',
      ),
    ).toBeVisible();
    expect(within(card).getByText('в таблице: «Н.Абдуллаев»')).toBeVisible();
    expect(within(card).getByText('Сотрудник не сопоставлен')).toBeVisible();

    fireEvent.click(within(card).getByRole('button', { name: 'Это Абдуллаев Н.' }));

    await waitFor(() =>
      expect(within(card).queryByText('Сотрудник не сопоставлен')).not.toBeInTheDocument(),
    );
    // Написание из таблицы остаётся рядом с сопоставленным (инвариант 6).
    expect(within(card).getByText('в таблице: «Н.Абдуллаев»')).toBeVisible();
  });

  it('руководитель решает в карточке и может отменить', async () => {
    route.set({ view: 'assignments' });
    serve('leader');
    renderIjro();

    fireEvent.click(
      await screen.findByRole('button', { name: /^Дастурни амалга ошириш бўйича идоралараро/ }),
    );
    const card = await screen.findByRole('dialog', { name: 'Карточка поручения' });
    expect(await within(card).findByText('Утвердить состав рабочей группы?')).toBeVisible();

    fireEvent.click(await within(card).findByRole('button', { name: 'Утвердить' }));
    expect(await within(card).findByText('Решение: Утвердить')).toBeVisible();

    fireEvent.click(within(card).getByRole('button', { name: 'Отменить' }));
    expect(await within(card).findByRole('button', { name: 'Утвердить' })).toBeVisible();
  });

  it('помощник: предпросмотр таблицы, применение, и повтор ничего не меняет', async () => {
    route.set({ view: 'upload' });
    serve('assistant');
    renderIjro();

    const file = new File(['PK'], 'АП топшириқлари 4-чорак.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    fireEvent.change(await screen.findByLabelText('Выбрать файл Word'), {
      target: { files: [file] },
    });

    expect(await screen.findByText('срок сдвинут: 3')).toBeVisible();
    expect(screen.getByText('новые: 2')).toBeVisible();
    expect(screen.getByText('не распознано: 1')).toBeVisible();

    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Подтверждаю перенос' })[0]!);
    fireEvent.click(screen.getByRole('button', { name: 'Применить' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Применено: новых 2, изменено 3, продлений записано 1, ждут подтверждения 2.',
    );
    expect(await screen.findByText(/Эта таблица уже применена .* — изменений нет\./)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Применить' })).not.toBeInTheDocument();
  });

  it('руководитель по адресу загрузки видит вопросы: вкладка — только помощнику', async () => {
    route.set({ view: 'upload' });
    serve('leader');
    renderIjro();

    expect(
      await screen.findByRole('heading', { name: 'Что горит и что просрочено?' }),
    ).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByRole('tab', { name: 'Загрузка' })).not.toBeInTheDocument(),
    );
    expect(screen.queryByText('Загрузка таблицы')).not.toBeInTheDocument();
  });

  it('стена документов: сколько сдано и кого вызвать с отчётом', async () => {
    route.set({ view: 'documents' });
    serve('leader');
    renderIjro();

    expect(await screen.findAllByText(/^сдано \d+ из \d+$/)).toHaveLength(4);
    expect(screen.getAllByText(/^Вызвать с отчётом: .+ — открытых \d+$/).length).toBeGreaterThan(0);
  });
});

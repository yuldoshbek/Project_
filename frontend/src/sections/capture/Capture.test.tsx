/**
 * Захват: тип одним касанием, разбор фразы у задачи, запись — задача настоящим API
 * «Задач», остальное во входящие вымышленного сервера; руководителю — два своих типа; фото
 * названо, когда заработает; недавние показывают, куда ушла запись.
 *
 * Разбор фразы считает сервер (`backend/tests/test_capture.py`); здесь — что экран делает
 * с ответом и что уходит на сервер. Сеть подменена на уровне `fetch`.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  configure,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import i18next from 'i18next';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { detailOf, task, view } from '@/sections/tasks/test-data';
import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { CaptureForm } from './CaptureForm';
import { demoCaptures } from './demo';
import type { Capture } from './model';
import { agoText, metaText } from './text';

const NOW = new Date('2026-09-28T07:00:00Z');

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

interface Call {
  method: string;
  path: string;
  body: unknown;
}

interface Options {
  /** Ответ на заведение задачи: по умолчанию — заведена. */
  createTask?: () => Promise<Response>;
}

function serve(role: 'leader' | 'assistant' = 'assistant', options: Options = {}) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (method === 'GET' && path === '/api/v1/tasks') return Promise.resolve(reply(200, view()));
    if (method === 'POST' && path === '/api/v1/tasks/parse') {
      const text = String(body.text);
      const friday = text.includes('к пятнице');
      return Promise.resolve(
        reply(200, {
          title: text.replace('к пятнице ', '').replace(', Каримов', ''),
          type_code: text.includes('справк') ? 'analytical_note' : null,
          due_on: friday ? '2026-10-02' : text.includes('10 октября') ? '2026-10-10' : null,
          assignee_id: text.includes('Каримов') ? 'p-karimov' : null,
          matched: { type: null, due: friday ? 'к пятнице' : null, assignee: null },
        }),
      );
    }
    if (method === 'POST' && path === '/api/v1/tasks') {
      if (options.createTask) return options.createTask();
      const fresh = task({ id: 't-new', title: body.title, code: 'TSK-2026-0999' });
      return Promise.resolve(reply(201, detailOf(fresh)));
    }
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
  return calls;
}

function renderCapture() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CaptureForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
  demoCaptures.reset();
  localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// Разбор идёт после паузы набора (250 мс) и через сеть — ожидание с запасом.
beforeAll(() => configure({ asyncUtilTimeout: 3_000 }));
afterAll(() => configure({ asyncUtilTimeout: 1_000 }));

describe('Захват', () => {
  it('помощник: пять типов, задача — по умолчанию, фраза разобрана до записи', async () => {
    const calls = serve();
    renderCapture();

    const kinds = await screen.findByRole('group', { name: 'Что это' });
    expect(within(kinds).getAllByRole('radio')).toHaveLength(5);
    await waitFor(() => expect(within(kinds).getByLabelText('Задача')).toBeChecked());

    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'к пятнице справка по паводкам для Кабмина, Каримов' },
    });
    expect(await screen.findByText('Понято: справка по паводкам для Кабмина')).toBeInTheDocument();
    expect(screen.getByLabelText('Срок')).toHaveValue('2026-10-02');
    expect(screen.getByLabelText('Ответственный')).toHaveValue('p-karimov');
    expect(screen.getByLabelText('Тип')).toHaveValue('analytical_note');

    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Задача заведена: TSK-2026-0999 — она в «Задачах».',
    );
    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/v1/tasks',
      body: {
        title: 'справка по паводкам для Кабмина',
        type_code: 'analytical_note',
        due_on: '2026-10-02',
        assignee_id: 'p-karimov',
        project_id: null,
      },
    });
    // Поле очищено и снова в фокусе: следующее дело — сразу.
    expect(screen.getByRole('textbox', { name: 'Текст записи' })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: 'Текст записи' })).toHaveFocus();
    const recent = screen.getByRole('heading', { name: 'Недавние записи' }).closest('section')!;
    expect(within(recent).getByText('справка по паводкам для Кабмина')).toBeInTheDocument();
  });

  it('идея — во входящие, без разбора и без записи в «Задачи»', async () => {
    const calls = serve();
    renderCapture();
    fireEvent.click(await screen.findByLabelText('Идея'));
    expect(screen.getByText(/раздел «Идеи и карты» появится в блоке 3/)).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'Мониторинг пастбищ для Минсельхоза' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Идея во входящих.');
    // Справочник «Задач» мог загрузиться, пока был выбран тип «Задача»; записи и разбора — нет.
    expect(calls.filter((call) => call.method === 'POST')).toEqual([]);

    const recent = screen.getByRole('heading', { name: 'Недавние записи' }).closest('section')!;
    const first = within(recent).getAllByRole('listitem')[0]!;
    expect(first).toHaveTextContent('Мониторинг пастбищ для Минсельхоза');
    expect(first).toHaveTextContent('во входящих до «Идей и карт»');
  });

  it('у письма один срок — срок ответа', async () => {
    serve();
    renderCapture();
    fireEvent.click(await screen.findByLabelText('Письмо'));
    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'Минэкологии просит данные, ответ до 10 октября' },
    });
    await waitFor(() => expect(screen.getByLabelText('Срок ответа')).toHaveValue('2026-10-10'));
    expect(screen.queryByLabelText('Ответственный')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    const recent = screen.getByRole('heading', { name: 'Недавние записи' }).closest('section')!;
    await waitFor(() =>
      expect(within(recent).getAllByRole('listitem')[0]!).toHaveTextContent('ответ до 10.10.2026'),
    );
  });

  it('руководитель: два своих типа — просьба и идея; по умолчанию идея', async () => {
    serve('leader');
    renderCapture();
    const kinds = await screen.findByRole('group', { name: 'Что это' });
    await waitFor(() =>
      expect(
        within(kinds)
          .getAllByRole('radio')
          .map((radio) => radio.closest('label')?.textContent),
      ).toEqual(['Просьба руководителя', 'Идея']),
    );
    expect(within(kinds).getByLabelText('Идея')).toBeChecked();

    fireEvent.click(within(kinds).getByLabelText('Просьба руководителя'));
    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'к пятнице справка по паводкам для Кабмина' },
    });
    expect(await screen.findByLabelText('Кому')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Просьба записана');
  });

  it('тип запоминается: в следующий раз открывается последний', async () => {
    serve();
    renderCapture();
    fireEvent.click(await screen.findByLabelText('Мероприятие'));
    expect(localStorage.getItem('orbita.capture.kind')).toBe('event');

    cleanup();
    renderCapture();
    const kinds = await screen.findByRole('group', { name: 'Что это' });
    await waitFor(() => expect(within(kinds).getByLabelText('Мероприятие')).toBeChecked());
  });

  it('запомненный тип чужой роли не выбирается: руководителю — его идея', async () => {
    localStorage.setItem('orbita.capture.kind', 'task');
    serve('leader');
    renderCapture();
    const kinds = await screen.findByRole('group', { name: 'Что это' });
    await waitFor(() => expect(within(kinds).getAllByRole('radio')).toHaveLength(2));
    expect(within(kinds).getByLabelText('Идея')).toBeChecked();
  });

  it('Enter записывает, Shift+Enter — нет', async () => {
    serve();
    renderCapture();
    fireEvent.click(await screen.findByLabelText('Идея'));
    const field = screen.getByRole('textbox', { name: 'Текст записи' });
    fireEvent.change(field, { target: { value: 'Мониторинг пастбищ' } });

    fireEvent.keyDown(field, { key: 'Enter', shiftKey: true });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    fireEvent.keyDown(field, { key: 'Enter' });
    expect(await screen.findByRole('status')).toHaveTextContent('Идея во входящих.');
    expect(field).toHaveValue('');
  });

  it('ошибка прошлой записи не остаётся рядом с успехом следующей', async () => {
    serve('assistant', {
      createTask: () => Promise.resolve(reply(503, { detail: 'сервер недоступен' })),
    });
    renderCapture();
    const kinds = await screen.findByRole('group', { name: 'Что это' });
    await waitFor(() => expect(within(kinds).getByLabelText('Задача')).toBeChecked());
    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'Позвонить в Минфин' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    fireEvent.click(within(kinds).getByLabelText('Идея'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Идея во входящих.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('набранное, пока запись шла по сети, не стирается', async () => {
    let answer: ((response: Response) => void) | null = null;
    serve('assistant', {
      createTask: () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    });
    renderCapture();
    const kinds = await screen.findByRole('group', { name: 'Что это' });
    await waitFor(() => expect(within(kinds).getByLabelText('Задача')).toBeChecked());
    const field = screen.getByRole('textbox', { name: 'Текст записи' });
    fireEvent.change(field, { target: { value: 'Позвонить в Минфин' } });
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    // Запрос уходит не в том же такте, что касание: ждём, пока он в пути.
    await waitFor(() => expect(answer).not.toBeNull());

    fireEvent.change(field, { target: { value: 'Следующее дело' } });
    answer!(reply(201, detailOf(task({ id: 't-new', title: 'Позвонить в Минфин' }))));
    expect(await screen.findByRole('status')).toHaveTextContent('Задача заведена');
    expect(field).toHaveValue('Следующее дело');
  });

  it('экран на вымышленных данных так и помечен — и сказано, что живёт до перезагрузки', async () => {
    serve();
    renderCapture();
    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    expect(
      screen.getByText(/недавние записи выдуманы и живут до перезагрузки/),
    ).toBeInTheDocument();
  });

  it('фото названо честно: кнопка есть и говорит, когда заработает', async () => {
    serve();
    renderCapture();
    const photo = await screen.findByRole('button', { name: 'Фото' });
    expect(photo).toBeDisabled();
    expect(photo).toHaveAccessibleDescription('Фото — вместе с хранилищем файлов в блоке 2.');
  });

  it('на телефоне — подсказка про диктовку', async () => {
    setViewport({ width: 390 });
    serve();
    renderCapture();
    expect(
      await screen.findByText('Надиктовать — кнопка микрофона на клавиатуре телефона.'),
    ).toBeInTheDocument();
  });
});

describe('подписи недавних записей', () => {
  const t = i18next.t.bind(i18next);

  it('«вчера» — по календарю Ташкента, а не по 24 часам', () => {
    // 09:00 по Ташкенту; запись — позавчера в 23:00, прошло 34 часа.
    expect(agoText(t, '2026-09-26T18:00:00Z', '2026-09-28T04:00:00Z')).toBe('2 дн назад');
    // 23:00; запись — вчера в 00:30, прошло 46,5 часа.
    expect(agoText(t, '2026-09-26T19:30:00Z', '2026-09-28T18:00:00Z')).toBe('вчера');
    expect(agoText(t, '2026-09-28T02:00:00Z', '2026-09-28T07:00:00Z')).toBe('5 ч назад');
  });

  it('просьба на вымышленных данных — «встанет в «Задачи»», а не «в «Задачах»»', () => {
    const request: Capture = {
      id: 'cp-1',
      kind: 'request',
      text: 'Справка по паводкам',
      due_on: null,
      author: 'leader',
      created_at: '2026-09-28T06:00:00Z',
      destination: 'tasks',
    };
    const asOf = '2026-09-28T07:00:00Z';
    expect(metaText(t, request, asOf, true)).toContain('встанет в «Задачи» после утверждения');
    expect(metaText(t, request, asOf, false)).toContain('в «Задачах»');
    expect(metaText(t, { ...request, kind: 'task' }, asOf, true)).toContain('в «Задачах»');
  });
});

/**
 * Захват: тип одним касанием, разбор фразы у задачи и просьбы, запись — `POST
 * /api/v1/captures` только с полями типа; руководителю — два своих типа; фото названо, когда
 * заработает; недавние показывают, куда ушла запись.
 *
 * Разбор фразы считает сервер (`backend/tests/test_capture.py`), куда уходит запись и кто
 * что пишет — тоже (`backend/tests/test_captures.py`); здесь — что экран делает с ответом и
 * что уходит на сервер. Сеть подменена на уровне `fetch`.
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

import { view } from '@/sections/tasks/test-data';
import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { CaptureForm } from './CaptureForm';
import type { Capture, NewCapture, SavedCapture } from './model';
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

const EARLIER: Capture[] = [
  {
    id: 'cp-1',
    kind: 'letter',
    text: 'Минэкологии просит данные мониторинга засухи за август',
    due_on: '2026-10-10',
    author: 'assistant',
    created_at: '2026-09-28T05:00:00Z',
    destination: 'inbox',
  },
  {
    id: 'cp-2',
    kind: 'idea',
    text: 'Спутниковый мониторинг пастбищ',
    due_on: null,
    author: 'leader',
    created_at: '2026-09-27T05:00:00Z',
    destination: 'inbox',
  },
];

interface Call {
  method: string;
  path: string;
  body: unknown;
}

interface Options {
  /** Свой ответ на запись; `null` — ответ по умолчанию. */
  save?: (body: NewCapture) => Promise<Response> | null;
  demo?: boolean;
  /** Сколько первых загрузок фото падает: проверка «запись есть, фото — ещё раз». */
  failUploads?: number;
}

/** Сервер Захвата в памяти: недавние, запись по правилу V17, разбор фразы. */
function serve(role: 'leader' | 'assistant' = 'assistant', options: Options = {}) {
  const calls: Call[] = [];
  const recent = [...EARLIER];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    // Фото уходит телом-файлом, остальное — JSON.
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body;
    calls.push({ method, path, body });
    if (method === 'POST' && path === '/api/v1/files/photos') {
      const file_id = `f-${calls.length}`;
      return Promise.resolve(
        reply(201, {
          file_id,
          upload: { url: `/api/v1/files/${file_id}/content`, method: 'PUT', headers: {} },
        }),
      );
    }
    if (method === 'PUT' && path.startsWith('/api/v1/files/')) {
      if ((options.failUploads ?? 0) > 0) {
        options.failUploads = (options.failUploads ?? 0) - 1;
        return Promise.resolve(reply(503, { detail: 'хранилище недоступно' }));
      }
      return Promise.resolve(reply(204));
    }
    if (method === 'POST' && path.endsWith('/complete')) return Promise.resolve(reply(204));
    if (method === 'GET' && path.startsWith('/api/v1/files/photos')) {
      return Promise.resolve(reply(200, []));
    }
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (method === 'GET' && path === '/api/v1/tasks') return Promise.resolve(reply(200, view()));
    if (method === 'GET' && path === '/api/v1/captures') {
      return Promise.resolve(
        reply(200, { as_of: NOW.toISOString(), recent, is_demo: options.demo ?? false }),
      );
    }
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
    if (method === 'POST' && path === '/api/v1/captures') {
      const own = options.save?.(body);
      if (own) return own;
      const input = body as NewCapture;
      const toTasks = input.kind === 'task' || input.kind === 'request';
      const saved: SavedCapture = {
        id: `cp-new-${calls.length}`,
        kind: input.kind,
        text: input.text,
        due_on: input.due_on ?? null,
        author: role,
        created_at: NOW.toISOString(),
        destination: toTasks ? 'tasks' : 'inbox',
        task_code: toTasks ? 'TSK-2026-0999' : null,
        photo_owner: toTasks
          ? { owner_type: 'task', owner_id: 't-new' }
          : { owner_type: input.kind === 'idea' ? 'idea' : 'capture', owner_id: 'i-new' },
      };
      recent.unshift(saved);
      return Promise.resolve(reply(201, saved));
    }
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
  return calls;
}

function posted(calls: Call[]): unknown[] {
  return calls
    .filter((call) => call.method === 'POST' && call.path === '/api/v1/captures')
    .map((call) => call.body);
}

function renderCapture() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CaptureForm />
    </QueryClientProvider>,
  );
}

function recentList() {
  return screen.getByRole('heading', { name: 'Недавние записи' }).closest('section')!;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
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
    expect(posted(calls)).toEqual([
      {
        kind: 'task',
        text: 'справка по паводкам для Кабмина',
        due_on: '2026-10-02',
        assignee_id: 'p-karimov',
        type_code: 'analytical_note',
        project_id: null,
      },
    ]);
    // Поле очищено и снова в фокусе: следующее дело — сразу.
    expect(screen.getByRole('textbox', { name: 'Текст записи' })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: 'Текст записи' })).toHaveFocus();
    await waitFor(() =>
      expect(within(recentList()).getAllByRole('listitem')[0]!).toHaveTextContent(
        'справка по паводкам для Кабмина',
      ),
    );
  });

  it('идея — во входящие, без разбора и без полей', async () => {
    const calls = serve();
    renderCapture();
    fireEvent.click(await screen.findByLabelText('Идея'));
    expect(screen.getByText(/Ляжет наброском в «Идеи и карты»/)).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'Мониторинг пастбищ для Минсельхоза' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Идея записана наброском в «Идеях и картах».',
    );
    expect(calls.some((call) => call.path === '/api/v1/tasks/parse')).toBe(false);
    expect(posted(calls)).toEqual([{ kind: 'idea', text: 'Мониторинг пастбищ для Минсельхоза' }]);

    await waitFor(() => {
      const first = within(recentList()).getAllByRole('listitem')[0]!;
      expect(first).toHaveTextContent('Мониторинг пастбищ для Минсельхоза');
      expect(first).toHaveTextContent('в «Идеях и картах»');
    });
  });

  it('у письма один срок — срок ответа', async () => {
    const calls = serve();
    renderCapture();
    fireEvent.click(await screen.findByLabelText('Письмо'));
    fireEvent.change(screen.getByRole('textbox', { name: 'Текст записи' }), {
      target: { value: 'Минэкологии просит данные, ответ до 10 октября' },
    });
    await waitFor(() => expect(screen.getByLabelText('Срок ответа')).toHaveValue('2026-10-10'));
    expect(screen.queryByLabelText('Ответственный')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Письмо во входящих.');
    expect(posted(calls)).toEqual([
      {
        kind: 'letter',
        text: 'Минэкологии просит данные, ответ до 10 октября',
        due_on: '2026-10-10',
      },
    ]);
  });

  it('недавние: кто, когда, срок и куда ушло', async () => {
    serve();
    renderCapture();
    const items = await within(await screen.findByRole('list')).findAllByRole('listitem');
    expect(items[0]).toHaveTextContent(
      'Помощник · 2 ч назад · ответ до 10.10.2026 · во входящих до «Взаимодействия»',
    );
    expect(items[1]).toHaveTextContent('Руководитель · вчера · в «Идеях и картах»');
  });

  it('руководитель: два своих типа — просьба и идея; по умолчанию идея', async () => {
    const calls = serve('leader');
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
    await waitFor(() => expect(screen.getByLabelText('Срок')).toHaveValue('2026-10-02'));
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Просьба записана: TSK-2026-0999 — в «Задачах» с пометкой «просьба руководителя».',
    );
    expect(posted(calls)).toEqual([
      {
        kind: 'request',
        text: 'справка по паводкам для Кабмина',
        due_on: '2026-10-02',
        assignee_id: null,
      },
    ]);
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
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Идея записана наброском в «Идеях и картах».',
    );
    expect(field).toHaveValue('');
  });

  it('Enter до ответа разбора ждёт его: срок и ответственный не теряются', async () => {
    const calls = serve();
    renderCapture();
    const kinds = await screen.findByRole('group', { name: 'Что это' });
    await waitFor(() => expect(within(kinds).getByLabelText('Задача')).toBeChecked());
    const field = screen.getByRole('textbox', { name: 'Текст записи' });
    fireEvent.change(field, { target: { value: 'к пятнице справка по паводкам, Каримов' } });
    fireEvent.keyDown(field, { key: 'Enter' });

    expect(await screen.findByRole('status')).toHaveTextContent('Задача заведена');
    expect(posted(calls)).toEqual([
      {
        kind: 'task',
        text: 'справка по паводкам',
        due_on: '2026-10-02',
        assignee_id: 'p-karimov',
        type_code: 'analytical_note',
        project_id: null,
      },
    ]);
  });

  it('ошибка прошлой записи не остаётся рядом с успехом следующей', async () => {
    serve('assistant', {
      save: (body) =>
        body.kind === 'task' ? Promise.resolve(reply(503, { detail: 'сервер недоступен' })) : null,
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
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Идея записана наброском в «Идеях и картах».',
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('набранное, пока запись шла по сети, не стирается', async () => {
    let answer: ((response: Response) => void) | null = null;
    serve('assistant', {
      save: () =>
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
    const saved: SavedCapture = {
      id: 'cp-new',
      kind: 'task',
      text: 'Позвонить в Минфин',
      due_on: null,
      author: 'assistant',
      created_at: NOW.toISOString(),
      destination: 'tasks',
      task_code: 'TSK-2026-0999',
      photo_owner: { owner_type: 'task', owner_id: 't-new' },
    };
    answer!(reply(201, saved));
    expect(await screen.findByRole('status')).toHaveTextContent('Задача заведена');
    expect(field).toHaveValue('Следующее дело');
  });

  it('вымышленные данные помечены видимой строкой, настоящие — нет', async () => {
    serve('assistant', { demo: true });
    renderCapture();
    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    expect(screen.getByText(/записи сохраняются, но в рабочую систему не попадают/)).toBeVisible();

    cleanup();
    vi.restoreAllMocks();
    serve();
    renderCapture();
    await screen.findByRole('heading', { name: 'Недавние записи' });
    expect(screen.queryByText('Вымышленные данные')).not.toBeInTheDocument();
  });

  it('кнопка «Фото» работает — снимок прикладывается к записи (V18)', async () => {
    serve();
    renderCapture();
    expect(await screen.findByRole('button', { name: 'Фото' })).toBeEnabled();
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

  it('задача и просьба — «в «Задачах»», срок мероприятия — просто дата', () => {
    const request: Capture = {
      id: 'cp-1',
      kind: 'request',
      text: 'Справка по паводкам',
      due_on: '2026-10-02',
      author: 'leader',
      created_at: '2026-09-28T06:00:00Z',
      destination: 'tasks',
    };
    const asOf = '2026-09-28T07:00:00Z';
    expect(metaText(t, request, asOf)).toBe(
      'Руководитель · 1 ч назад · срок 02.10.2026 · в «Задачах»',
    );
    expect(
      metaText(t, { ...request, kind: 'event', destination: 'inbox', author: 'assistant' }, asOf),
    ).toBe('Помощник · 1 ч назад · 02.10.2026 · во входящих до «Докладов и мероприятий»');
  });
});

describe('фото из Захвата (V18)', () => {
  beforeEach(() => {
    // jsdom не умеет показывать выбранный файл — миниатюре нужен только адрес.
    URL.createObjectURL = vi.fn(() => 'blob:photo');
    URL.revokeObjectURL = vi.fn();
  });

  async function pickAndSave(text: string) {
    const field = await screen.findByRole('textbox', { name: 'Текст записи' });
    fireEvent.change(field, { target: { value: text } });
    const photo = new File(['jpeg'], 'доска.jpg', { type: 'image/jpeg' });
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [photo] },
    });
    expect(screen.getByRole('img', { name: 'Выбранное фото' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));
  }

  it('фото уходит следом за записью — к задаче, которую она завела', async () => {
    const calls = serve('assistant');
    renderCapture();

    await pickAndSave('Позвонить в Минфин');

    expect(await screen.findByText(/Фото приложено/)).toBeInTheDocument();
    expect(calls).toContainEqual({
      method: 'POST',
      path: '/api/v1/files/photos',
      body: {
        owner_type: 'task',
        owner_id: 't-new',
        name: 'доска.jpg',
        content_type: 'image/jpeg',
        size: 4,
      },
    });
    const put = calls.findIndex((call) => call.method === 'PUT');
    const done = calls.findIndex((call) => call.path.endsWith('/complete'));
    expect(put).toBeGreaterThan(-1);
    expect(done).toBeGreaterThan(put);
    // Фото ушло — следующая запись начинается без него.
    expect(screen.queryByRole('img', { name: 'Выбранное фото' })).not.toBeInTheDocument();
  });

  it('фото не загрузилось — запись уже есть, фото отправляется ещё раз без второй записи', async () => {
    const calls = serve('assistant', { failUploads: 1 });
    renderCapture();

    await pickAndSave('Позвонить в Минфин');

    expect(await screen.findByText(/Запись сохранена, а фото не загрузилось/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));

    expect(await screen.findByText(/Фото приложено/)).toBeInTheDocument();
    const saves = calls.filter(
      (call) => call.method === 'POST' && call.path === '/api/v1/captures',
    );
    expect(saves).toHaveLength(1);
  });
});

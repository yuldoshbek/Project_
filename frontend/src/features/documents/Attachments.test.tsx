/**
 * Панель вложений (ORB-017).
 *
 * Четыре обещания панели, и каждое ломается так, что экран выглядит рабочим.
 *
 * **Предпросмотр без скачивания.** Проверяется, что содержимое встаёт в разметку по
 * адресу из хранилища, а не приезжает через приложение: подменить это на «скачали и
 * показали» легко и незаметно — на глаз результат тот же, а обработчик занят на всё
 * время передачи.
 *
 * **Ссылка не запоминается.** Она живёт минуты. Экран, сохранивший её в состоянии,
 * работает весь первый час и перестаёт работать на втором — то есть никогда не ломается
 * при проверке.
 *
 * **Повторная загрузка того же файла.** Сервер отвечает «ничего не создано», и без
 * надписи это выглядит как не сработавшая кнопка. Человек нажмёт ещё раз.
 *
 * **Отказ объясняется словами сервера.** Там сказано, сколько весит файл и каков предел.
 * Замена на своё «ошибка загрузки» выбрасывает единственное, что объясняет отказ.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LEADER, sessionOf } from '../../testing/profiles';
import { WithSession } from '../../testing/WithSession';
import { Attachments } from './Attachments';
import { humanSize } from './api';

const ESTIMATE = {
  id: 'doc-1',
  entity_type: 'project' as const,
  entity_id: 'p-1',
  name: 'Смета работ.xlsx',
  current_version: 2,
  created_at: '2026-09-10T06:00:00Z',
  version: {
    id: 'ver-2',
    number: 2,
    size_bytes: 1_258_291,
    content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    sha256: 'a'.repeat(64),
    uploaded_at: '2026-09-10T06:00:00Z',
    uploaded_by: 'u-1',
    preview_state: 'ready' as const,
  },
};

const SCAN = {
  ...ESTIMATE,
  id: 'doc-2',
  name: 'Схема антенны.png',
  current_version: 1,
  version: {
    ...ESTIMATE.version,
    id: 'ver-3',
    number: 1,
    content_type: 'image/png',
    size_bytes: 240_000,
    preview_state: 'native' as const,
  },
};

const CONVERTING = {
  ...ESTIMATE,
  id: 'doc-3',
  name: 'Письмо.docx',
  current_version: 1,
  version: {
    ...ESTIMATE.version,
    id: 'ver-4',
    number: 1,
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    preview_state: 'pending' as const,
  },
};

const LINK = {
  url: 'http://127.0.0.1:59000/orbita/orbita/project/p-1/doc-1/v2.xlsx.preview.pdf?X-Amz-Signature=1',
  expires_in: 300,
  filename: 'Смета работ.xlsx.pdf',
};

const fetchMock = vi.fn();

function answer(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function serve(documents: unknown[]): void {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if ((init?.method ?? 'GET') === 'POST')
      return answer({ created: true, document: ESTIMATE }, 201);
    if (url.includes('/link')) return answer(LINK);
    if (url.includes('/versions'))
      return answer([ESTIMATE.version, { ...ESTIMATE.version, id: 'ver-1', number: 1 }]);
    return answer(documents);
  });
}

function show(
  node = <Attachments target="project" entityId="p-1" />,
  value?: Parameters<typeof WithSession>[0]['value'],
) {
  return render(
    value === undefined ? (
      <WithSession>{node}</WithSession>
    ) : (
      <WithSession value={value}>{node}</WithSession>
    ),
  );
}

/** Адреса всех запросов — по ним видно, что и в каком порядке спрашивали. */
function urls(): string[] {
  return fetchMock.mock.calls.map((call) => String(call[0]));
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  serve([ESTIMATE, SCAN]);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('панель вложений', () => {
  it('показывает имя файла, его размер и номер версии', async () => {
    show();

    const row = (await screen.findByText('Смета работ.xlsx')).closest('li');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText('версия 2')).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText(humanSize(1_258_291))).toBeInTheDocument();
  });

  it('у файла одной версии номер не показывается', async () => {
    show();

    const row = (await screen.findByText('Схема антенны.png')).closest('li');
    expect(within(row as HTMLElement).queryByText(/версия/)).toBeNull();
  });

  it('картинка показывается по адресу хранилища, а не через приложение', async () => {
    const user = userEvent.setup();
    show();

    const row = (await screen.findByText('Схема антенны.png')).closest('li');
    await user.click(within(row as HTMLElement).getByRole('button', { name: 'Показать' }));

    const image = await screen.findByRole('img', { name: 'Схема антенны.png' });
    expect(image).toHaveAttribute('src', LINK.url);
  });

  it('таблица показывается производным PDF в рамке просмотра', async () => {
    const user = userEvent.setup();
    show();

    const row = (await screen.findByText('Смета работ.xlsx')).closest('li');
    await user.click(within(row as HTMLElement).getByRole('button', { name: 'Показать' }));

    const frame = await screen.findByTitle('Смета работ.xlsx');
    expect(frame).toHaveAttribute('src', LINK.url);
  });

  it('ссылка берётся заново при каждом показе, а не запоминается', async () => {
    const user = userEvent.setup();
    show();

    const row = (await screen.findByText('Схема антенны.png')).closest('li');
    const button = within(row as HTMLElement).getByRole('button', { name: 'Показать' });

    await user.click(button);
    await screen.findByRole('img', { name: 'Схема антенны.png' });
    await user.click(within(row as HTMLElement).getByRole('button', { name: 'Скрыть' }));
    await user.click(within(row as HTMLElement).getByRole('button', { name: 'Показать' }));
    await screen.findByRole('img', { name: 'Схема антенны.png' });

    const asked = urls().filter((url) => url.includes('/link'));
    expect(asked.length).toBe(2);
  });

  it('за предпросмотром идёт запрос inline, за скачиванием — нет', async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    vi.stubGlobal('open', open);
    show();

    const row = (await screen.findByText('Схема антенны.png')).closest('li');
    await user.click(within(row as HTMLElement).getByRole('button', { name: 'Показать' }));
    await screen.findByRole('img', { name: 'Схема антенны.png' });
    await user.click(within(row as HTMLElement).getByRole('button', { name: 'Скачать' }));

    await waitFor(() => {
      expect(open).toHaveBeenCalled();
    });

    const asked = urls().filter((url) => url.includes('/link'));
    expect(asked.some((url) => url.includes('inline=true'))).toBe(true);
    expect(asked.some((url) => !url.includes('inline=true'))).toBe(true);
  });

  it('пока строится предпросмотр, кнопки показа нет, а причина написана', async () => {
    serve([CONVERTING]);
    show();

    const row = (await screen.findByText('Письмо.docx')).closest('li');
    expect(within(row as HTMLElement).getByText('предпросмотр готовится')).toBeInTheDocument();
    expect(within(row as HTMLElement).queryByRole('button', { name: 'Показать' })).toBeNull();
    // Скачать можно всегда: исходный файл на месте, ждёт только его отпечаток.
    expect(within(row as HTMLElement).getByRole('button', { name: 'Скачать' })).toBeInTheDocument();
  });

  it('несостоявшийся предпросмотр не выдаётся за готовящийся', async () => {
    serve([{ ...CONVERTING, version: { ...CONVERTING.version, preview_state: 'failed' } }]);
    show();

    const row = (await screen.findByText('Письмо.docx')).closest('li');
    expect(within(row as HTMLElement).getByText('предпросмотр не построен')).toBeInTheDocument();
  });

  it('повторная загрузка того же файла объясняет, почему ничего не появилось', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        return answer({ created: false, document: ESTIMATE }, 201);
      }
      return answer([ESTIMATE]);
    });
    show();

    await screen.findByText('Смета работ.xlsx');
    const file = new File(['таблица'], 'Смета работ.xlsx', { type: 'application/octet-stream' });
    await user.upload(screen.getByLabelText('Перетащите файл сюда или выберите'), file);

    expect(
      await screen.findByText('Этот файл уже приложен — под именем «Смета работ.xlsx»'),
    ).toBeInTheDocument();
  });

  it('отказ показывается словами сервера, а не своими', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        return answer(
          {
            type: '/problems/rule-violation',
            title: 'Данные не прошли проверку',
            detail: 'Файл весит 62,0 МБ, а предел — 50,0 МБ. Положите файл в общую папку',
            status: 422,
          },
          422,
        );
      }
      return answer([]);
    });
    show();

    const file = new File(['x'], 'Большой.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText('Перетащите файл сюда или выберите'), file);

    expect(await screen.findByText(/62,0 МБ, а предел — 50,0 МБ/)).toBeInTheDocument();
  });

  it('руководителю загрузка и удаление не предлагаются', async () => {
    show(undefined, sessionOf(LEADER, 'signed-in'));

    await screen.findByText('Смета работ.xlsx');
    expect(screen.queryByLabelText('Перетащите файл сюда или выберите')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Удалить' })).toBeNull();
    // Смотреть — его работа (ADR-0011).
    expect(screen.getAllByRole('button', { name: 'Показать' }).length).toBeGreaterThan(0);
  });

  it('история версий открывается только у файла, у которого она есть', async () => {
    const user = userEvent.setup();
    show();

    const single = (await screen.findByText('Схема антенны.png')).closest('li');
    expect(within(single as HTMLElement).queryByRole('button', { name: 'Версии' })).toBeNull();

    const many = (await screen.findByText('Смета работ.xlsx')).closest('li');
    await user.click(within(many as HTMLElement).getByRole('button', { name: 'Версии' }));

    const rows = await screen.findAllByText(/версия [12]/);
    expect(rows.length).toBeGreaterThan(1);
  });

  it('пустой список говорит, что делать', async () => {
    serve([]);
    show();

    expect(await screen.findByText('Файлов пока нет')).toBeInTheDocument();
  });
});

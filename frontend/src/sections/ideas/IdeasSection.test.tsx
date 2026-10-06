/**
 * Идеи и карты — обещания экрана.
 *
 * «Что ждёт моего „да“?» — ответ числом, старшая идея и действие; руководитель решает идею в
 * проект одним действием, и идея показывает выросший проект (критерий 1 блока 3); помощник
 * не решает, а отправляет на рассмотрение; на мониторе правки нет; карта — полотно на
 * ноутбуке и контур на телефоне. Правка по устаревшей версии получает честный конфликт, а
 * свои быстрые шаги — нет (инвариант 15).
 *
 * Сеть подменена на уровне `fetch`: `/api/v1/ideas…` и `/api/v1/maps…` отвечает сервер в
 * памяти (`test-server.ts`) с версиями и отказами настоящего, сессию — заготовка.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { IdeasSection } from './IdeasSection';
import { FakeIdeas, STALE_MESSAGE, handle } from './test-server';

let search: Record<string, unknown> = {};

vi.mock('@tanstack/react-router', async () => {
  const { useSyncExternalStore } = await import('react');
  const listeners = new Set<() => void>();
  return {
    useSearch: () =>
      useSyncExternalStore(
        (notify) => {
          listeners.add(notify);
          return () => listeners.delete(notify);
        },
        () => search,
      ),
    useNavigate: () => (options: { search: Record<string, unknown> }) => {
      search = options.search;
      listeners.forEach((notify) => notify());
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

let server = new FakeIdeas();

function serve(role: 'assistant' | 'leader') {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const body = init?.body
      ? (JSON.parse(String(init.body)) as Record<string, unknown>)
      : undefined;
    const answer = handle(server, method, path, body, role);
    if (answer) return Promise.resolve(reply(answer[0], answer[1]));
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
}

/** Клиент запросов возвращается: тест сам вызывает перечитывание, которое в жизни делает опрос. */
function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IdeasSection />
    </QueryClientProvider>,
  );
  return client;
}

/** Открытая карта «Мониторинг сельского хозяйства» на ноутбуке помощника. */
async function openBoard() {
  setViewport({ width: 1440 });
  search = { view: 'maps', map: 'm-agro' };
  serve('assistant');
  const client = renderSection();
  const canvas = await screen.findByRole('region', { name: 'Полотно карты' });
  return { client, canvas };
}

function choose(canvas: HTMLElement, name: string) {
  fireEvent.click(within(canvas).getByRole('button', { name }));
  return screen.getByRole('region', { name: 'Узел' });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  server = new FakeIdeas();
  search = {};
});

describe('Идеи', () => {
  it('«Что ждёт моего „да“?» — сколько и сколько ждёт старшая', async () => {
    serve('leader');
    renderSection();

    expect(await screen.findByText('2 идеи ждут вашего «да»')).toBeVisible();
    expect(screen.getByText('дольше всех — 9 дней')).toBeVisible();
    const waiting = screen.getByRole('region', { name: 'На рассмотрении' });
    const rows = within(waiting).getAllByRole('listitem');
    // Дольше всех ждущая — первой.
    expect(rows[0]).toHaveTextContent('Открытый каталог снимков для вузов');
  });

  it('руководитель решает старшую идею в проект одним действием', async () => {
    serve('leader');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Решить старшую' }));
    const sheet = await screen.findByRole('dialog', { name: 'Решение по идее' });
    expect(within(sheet).getByText('Открытый каталог снимков для вузов')).toBeVisible();
    fireEvent.click(within(sheet).getByRole('button', { name: 'В проект' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText('1 идея ждёт вашего «да»')).toBeVisible();
    const decided = screen.getByRole('region', { name: 'Решено' });
    expect(within(decided).getByText(/Проект PR-0\d+ · Открытый каталог/)).toBeVisible();
    // Подставной сервер, как настоящий, без типа и версии проект не заводит.
    expect(server.idea('i-catalogue').link?.type).toBe('project');
  });

  it('решение по устаревшей версии — честный конфликт, а не молчаливая перезапись', async () => {
    serve('leader');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: 'Решить старшую' }));
    const sheet = await screen.findByRole('dialog', { name: 'Решение по идее' });
    // Пока лист открыт, помощник поправил идею.
    Object.assign(server.idea('i-catalogue'), { text: 'Каталог снимков для вузов', version: 2 });
    fireEvent.click(within(sheet).getByRole('button', { name: 'В задачу' }));

    expect(await within(sheet).findByRole('alert')).toHaveTextContent(STALE_MESSAGE);
    expect(server.idea('i-catalogue').step).toBe('review');
  });

  it('помощник не решает, а отправляет набросок на рассмотрение', async () => {
    const fetch = serve('assistant');
    renderSection();

    const drafts = await screen.findByRole('region', { name: 'Наброски' });
    fireEvent.click(within(drafts).getByRole('button', { name: 'На рассмотрение' }));
    expect(await screen.findByText('3 идеи ждут вашего «да»')).toBeVisible();

    // Роль проверяется, когда пользователь уже пришёл: до ответа /api/me экран и руководителю
    // показывает «Показать», и отсутствие «Решить» ничего бы не доказывало.
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/me', expect.anything()));
    expect(await screen.findByRole('button', { name: 'Показать' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Решить' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Решить старшую' })).toBeNull();
  });

  it('новая идея записывается наброском', async () => {
    serve('leader');
    renderSection();

    fireEvent.change(await screen.findByLabelText('Идея'), {
      target: { value: 'Снимки для учебников географии' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Записать' }));

    const drafts = screen.getByRole('region', { name: 'Наброски' });
    expect(await within(drafts).findByText('Снимки для учебников географии')).toBeVisible();
  });

  it('даты — по Ташкенту; у решённой видно, когда решено', async () => {
    serve('leader');
    renderSection();

    // Записана 04.10 в 20:30 UTC — в Ташкенте уже 05.10.
    const drafts = await screen.findByRole('region', { name: 'Наброски' });
    expect(within(drafts).getByRole('listitem')).toHaveTextContent('05.10.2026');
    // Решена 03.10 в 21:00 UTC — в Ташкенте 04.10.
    const decided = screen.getByRole('region', { name: 'Решено' });
    expect(within(decided).getByText(/решено 04\.10\.2026/)).toBeVisible();

    fireEvent.click(screen.getByRole('tab', { name: 'Карты' }));
    // Изменена 04.10 в 22:00 UTC — в Ташкенте 05.10.
    expect(
      await screen.findByRole('button', { name: /Мониторинг сельского хозяйства/ }),
    ).toHaveTextContent('05.10.2026');
  });

  it('текст наброска правится; правка помнит версию, с которой её начали', async () => {
    serve('assistant');
    const client = renderSection();

    const drafts = await screen.findByRole('region', { name: 'Наброски' });
    fireEvent.click(within(drafts).getByRole('button', { name: 'Изменить' }));
    fireEvent.change(within(drafts).getByLabelText('Текст идеи'), {
      target: { value: 'Спутниковый мониторинг пастбищ и лугов' },
    });
    fireEvent.click(within(drafts).getByRole('button', { name: 'Сохранить' }));
    expect(await within(drafts).findByText('Спутниковый мониторинг пастбищ и лугов')).toBeVisible();
    expect(server.idea('i-pasture').version).toBe(2);

    // Вторая правка: пока поле открыто, руководитель поменял текст, и опрос принёс новую
    // версию. Запрос уходит с версией начала правки — и получает конфликт.
    fireEvent.click(within(drafts).getByRole('button', { name: 'Изменить' }));
    Object.assign(server.idea('i-pasture'), { text: 'Пастбища: пилот на весну', version: 3 });
    await client.invalidateQueries({ queryKey: ['ideas'] });
    fireEvent.change(within(drafts).getByLabelText('Текст идеи'), {
      target: { value: 'Пастбища — опечатка исправлена' },
    });
    fireEvent.click(within(drafts).getByRole('button', { name: 'Сохранить' }));

    expect(await within(drafts).findByRole('alert')).toHaveTextContent(STALE_MESSAGE);
    expect(within(drafts).getByText('Пастбища: пилот на весну')).toBeVisible();
    expect(server.idea('i-pasture').text).toBe('Пастбища: пилот на весну');
  });

  it('монитор: без записи и правки идей, решение руководителя остаётся', async () => {
    setViewport({ width: 2560 });
    serve('leader');
    renderSection();

    expect(await screen.findByRole('button', { name: 'Решить старшую' })).toBeVisible();
    expect(screen.getAllByRole('button', { name: 'Решить' }).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('Идея')).toBeNull();
    expect(screen.queryByRole('button', { name: 'На рассмотрение' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Изменить' })).toBeNull();
  });
});

describe('Карты', () => {
  it('ноутбук: узел добавляется под выбранным и превращается в задачу', async () => {
    setViewport({ width: 1440 });
    search = { view: 'maps' };
    serve('assistant');
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: /Мониторинг сельского хозяйства/ }));
    const canvas = await screen.findByRole('region', { name: 'Полотно карты' });
    // Структура: связанный узел показывает ступень Пульта, несвязанный — «не связан».
    expect(within(canvas).getByText('Просрочено')).toBeVisible();
    expect(within(canvas).getAllByText('не связан')).toHaveLength(2);
    // Скринридер слышит код и ступень: подпись узла их не прячет.
    const drought = within(canvas).getByRole('button', { name: 'Засуха' });
    expect(drought).toHaveAccessibleDescription(/PR-003/);
    expect(drought).toHaveAccessibleDescription(/Просрочено/);

    fireEvent.click(within(canvas).getByRole('button', { name: 'Пастбища' }));
    fireEvent.change(screen.getByLabelText('Новый узел под «Пастбища»'), {
      target: { value: 'Пилот на весну' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить узел' }));
    expect(await within(canvas).findByRole('button', { name: 'Пилот на весну' })).toBeVisible();
    // Под выбранным — значит, родитель ушёл в запрос, а не только стоит в подписи поля.
    const added = server.nodes['m-agro']?.find((each) => each.text === 'Пилот на весну');
    expect(added?.parent_id).toBe('n-pasture');

    const panel = screen.getByRole('region', { name: 'Узел' });
    fireEvent.click(within(panel).getByRole('button', { name: 'В задачу' }));
    expect(await within(panel).findByText(/Задача Т-0\d+/)).toBeVisible();
  });

  it('узел переносится в другую ветвь', async () => {
    const { canvas } = await openBoard();

    const panel = choose(canvas, 'Пастбища');
    fireEvent.change(within(panel).getByLabelText('Родитель'), {
      target: { value: 'n-drought' },
    });

    await waitFor(() => expect(server.node('m-agro', 'n-pasture').parent_id).toBe('n-drought'));
    await waitFor(() => expect(within(panel).getByLabelText('Родитель')).toHaveValue('n-drought'));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('кольцо по устаревшей картине — отказ словами, а не тихая поломка дерева', async () => {
    const { canvas } = await openBoard();

    const panel = choose(canvas, 'Засуха');
    // Экран ещё видит «Пастбища» соседом «Засухи», а второй человек уже перенёс их под неё:
    // сделать «Пастбища» родителем «Засухи» значит замкнуть кольцо.
    Object.assign(server.node('m-agro', 'n-pasture'), { parent_id: 'n-drought', version: 2 });
    fireEvent.change(within(panel).getByLabelText('Родитель'), {
      target: { value: 'n-pasture' },
    });

    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'Узел не может стать потомком самого себя',
    );
    expect(server.node('m-agro', 'n-drought').parent_id).toBe('n-root');
  });

  it('ветвь убирается целиком; узел, добавленный вторым, — повод для конфликта, а не для молчания', async () => {
    server.addNode('m-agro', { text: 'Пилот на весну', parent_id: 'n-pasture', x: 560, y: 300 });
    const { canvas } = await openBoard();

    const panel = choose(canvas, 'Пастбища');
    fireEvent.click(within(panel).getByRole('button', { name: 'Убрать узел' }));
    expect(within(panel).getByText('Убрать 2 узла вместе с ветвью?')).toBeVisible();
    // Пока вопрос на экране, руководитель добавил под «Пастбища» ещё узел.
    server.addNode('m-agro', { text: 'Летние пастбища', parent_id: 'n-pasture', x: 560, y: 400 });
    fireEvent.click(within(panel).getByRole('button', { name: 'Убрать' }));

    expect(await within(panel).findByRole('alert')).toHaveTextContent(STALE_MESSAGE);
    expect(server.nodes['m-agro']).toHaveLength(5);
    // Перечитанная карта честно называет новое число — его и подтверждают.
    expect(await within(panel).findByText('Убрать 3 узла вместе с ветвью?')).toBeVisible();
    fireEvent.click(within(panel).getByRole('button', { name: 'Убрать' }));

    await waitFor(() => expect(server.nodes['m-agro']).toHaveLength(2));
    await waitFor(() =>
      expect(within(canvas).queryByRole('button', { name: 'Пастбища' })).toBeNull(),
    );
    expect(screen.queryByRole('region', { name: 'Узел' })).toBeNull();
  });

  it('подпись узла сохраняется; по версии, устаревшей с начала правки, — конфликт', async () => {
    const { client, canvas } = await openBoard();

    let panel = choose(canvas, 'Засуха');
    fireEvent.change(within(panel).getByLabelText('Подпись'), {
      target: { value: 'Засуха 2026' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Сохранить' }));
    expect(await within(canvas).findByRole('button', { name: 'Засуха 2026' })).toBeVisible();

    panel = screen.getByRole('region', { name: 'Узел' });
    fireEvent.change(within(panel).getByLabelText('Подпись'), {
      target: { value: 'Засуха: мониторинг' },
    });
    // Посреди правки второй человек переименовал узел, и опрос принёс его версию.
    Object.assign(server.node('m-agro', 'n-drought'), { text: 'Засуха и суховеи', version: 3 });
    await client.invalidateQueries({ queryKey: ['maps'] });
    expect(await within(canvas).findByRole('button', { name: 'Засуха и суховеи' })).toBeVisible();
    expect(within(panel).getByLabelText('Подпись')).toHaveValue('Засуха: мониторинг');
    fireEvent.click(within(panel).getByRole('button', { name: 'Сохранить' }));

    expect(await within(panel).findByRole('alert')).toHaveTextContent(STALE_MESSAGE);
    expect(server.node('m-agro', 'n-drought').text).toBe('Засуха и суховеи');
    expect(within(panel).getByLabelText('Подпись')).toHaveValue('Засуха и суховеи');
  });

  it('стрелки: быстрые шаги уходят по очереди, без ложного конфликта', async () => {
    const { canvas } = await openBoard();

    const pasture = within(canvas).getByRole('button', { name: 'Пастбища' });
    fireEvent.keyDown(pasture, { key: 'ArrowRight' });
    fireEvent.keyDown(pasture, { key: 'ArrowRight' });
    fireEvent.keyDown(pasture, { key: 'ArrowRight' });

    await waitFor(() => expect(server.node('m-agro', 'n-pasture').x).toBe(360));
    // Первый шаг ушёл сразу, второй и третий — одной целью после ответа.
    expect(server.node('m-agro', 'n-pasture').version).toBe(3);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('неудачный перенос не остаётся на экране', async () => {
    const { canvas } = await openBoard();

    const pasture = within(canvas).getByRole('button', { name: 'Пастбища' });
    const before = pasture.style.left;
    server.outage = /^PUT .*\/position$/;
    fireEvent.keyDown(pasture, { key: 'ArrowRight' });

    expect(await screen.findByRole('alert')).toHaveTextContent('Сервис временно недоступен');
    expect(within(canvas).getByRole('button', { name: 'Пастбища' }).style.left).toBe(before);
    expect(server.node('m-agro', 'n-pasture').x).toBe(300);
  });

  it('режим меняется на полотне', async () => {
    const { canvas } = await openBoard();

    const modes = screen.getByRole('group', { name: 'Режим карты' });
    fireEvent.click(within(modes).getByRole('button', { name: 'Набросок' }));

    await waitFor(() => expect(within(canvas).queryByText('не связан')).toBeNull());
    expect(server.maps[0]?.mode).toBe('sketch');
    expect(within(modes).getByRole('button', { name: 'Набросок' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('сбой фонового опроса не прячет полотно', async () => {
    const { client, canvas } = await openBoard();

    choose(canvas, 'Пастбища');
    server.outage = /^GET \/api\/v1\/maps\//;
    await client.invalidateQueries({ queryKey: ['maps'] });

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Карта не обновилась: Сервис временно недоступен',
    );
    expect(screen.getByRole('region', { name: 'Полотно карты' })).toBe(canvas);
    expect(screen.getByRole('region', { name: 'Узел' })).toBeVisible();
  });

  it('телефон: карта — контур, без полотна', async () => {
    setViewport({ width: 390 });
    search = { view: 'maps', map: 'm-agro' };
    serve('leader');
    renderSection();

    const outline = await screen.findByRole('region', { name: 'Контур карты' });
    expect(within(outline).getByText('Засуха')).toBeVisible();
    expect(within(outline).getByText('PR-003')).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Полотно карты' })).toBeNull();
  });
});

/**
 * Управление: обход недели, пороги, справочники, доступ — обещания экрана на утверждение.
 *
 * Обход — пункт уходит только действием, меняющим данные; кнопки «всё нормально» нет.
 * Пороги — в границах, с предпросмотром до записи. Справочники — переименовать, порядок,
 * выключить, добавить; у статусов только переименование; у типа проекта — шаблон вех.
 * Доступ — настоящий API блока 0: перевыпуск переспрашивает. Руководитель смотрит пороги и
 * справочники без правки и не запрашивает `/api/access`.
 *
 * Данные раздела — вымышленный сервер `demo.ts`; сеть (сессия, устройства, перевыпуск,
 * состояние) подменена на уровне `fetch`.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type * as Router from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CurrentUser, DeviceSession, Health } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import { demoManagement } from './demo';
import { ManagementSection } from './ManagementSection';

// Маршрутизатор здесь не участвует: название пункта обхода — обычная ссылка.
vi.mock('@tanstack/react-router', async (original) => ({
  ...(await original<typeof Router>()),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

const HEALTH: Health = {
  status: 'ok',
  commit: 'c482ff4',
  env: 'test',
  time: new Date().toISOString(),
};

const DEVICE: DeviceSession = {
  user_agent: 'iPhone Safari',
  ip: null,
  last_seen_at: '2026-09-28T13:40:00Z',
  expires_at: '2026-10-28T13:40:00Z',
};

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

function serve(role: 'assistant' | 'leader' = 'assistant') {
  const calls: { method: string; path: string }[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    calls.push({ method, path });
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (path === '/api/health') return Promise.resolve(reply(200, HEALTH));
    if (path.startsWith('/api/access/sessions/')) return Promise.resolve(reply(200, [DEVICE]));
    if (method === 'POST' && path.startsWith('/api/access/links/')) {
      return Promise.resolve(
        reply(200, {
          url: 'https://orbita.test/api/access/новая',
          issued_at: '2026-09-29T04:00:00Z',
        }),
      );
    }
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
  return calls;
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ManagementSection />
    </QueryClientProvider>,
  );
}

async function openTab(name: string) {
  fireEvent.click(await screen.findByRole('tab', { name: new RegExp(`^${name}`) }));
}

/** Пункт обхода или строка по заголовку — всё проверяется внутри неё. */
function itemOf(title: string): HTMLElement {
  const found = screen.getByText(title).closest('li');
  if (!found) throw new Error(`нет строки «${title}»`);
  return found;
}

beforeEach(() => demoManagement.reset());
afterEach(() => vi.restoreAllMocks());

describe('обход недели', () => {
  it('помощнику открыт обход: причина у каждого пункта, кнопки «всё нормально» нет', async () => {
    serve();
    renderSection();

    await waitFor(() =>
      expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
        'Обход12',
        'Справочники',
        'Пороги',
        'Доступ',
      ]),
    );
    expect(screen.getByRole('tab', { name: /^Обход/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('осталось 12')).toBeInTheDocument();
    expect(screen.getByText('сделано на неделе: 3')).toBeInTheDocument();

    const item = itemOf('Приёмка опытного образца платформы');
    expect(item).toHaveTextContent('Срок вехи прошёл 9 дн назад, а она не отмечена пройденной.');
    expect(item).toHaveTextContent('Геопортал агентства · Турсунов Б.');
    expect(screen.queryByRole('button', { name: /нормально/i })).not.toBeInTheDocument();
    expect(screen.getByText('Вымышленные данные')).toBeInTheDocument();
  });

  it('действие меняет данные: пункт уходит, неделя его засчитывает', async () => {
    serve();
    renderSection();
    const item = await screen.findByText('Приёмка опытного образца платформы');
    fireEvent.click(within(item.closest('li')!).getByRole('button', { name: 'Пройдена' }));

    // Подпись — что именно сделано, а не общее «сделано».
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Пройдена: Приёмка опытного образца платформы',
    );
    expect(screen.queryByText('Приёмка опытного образца платформы')).not.toBeInTheDocument();
    expect(screen.getByText('осталось 11')).toBeInTheDocument();
    expect(screen.getByText('сделано на неделе: 4')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^Обход/ })).toHaveTextContent('Обход11');
  });

  it('молчащий проект, который сделан, закрывается одним касанием', async () => {
    serve();
    renderSection();
    await screen.findByText('Учебная лаборатория ДЗЗ в вузе');
    fireEvent.click(
      within(itemOf('Учебная лаборатория ДЗЗ в вузе')).getByRole('button', { name: 'Завершён' }),
    );
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Завершён: Учебная лаборатория ДЗЗ в вузе',
    );
  });

  it('«Записать, что мешает» просит строку, пустую не записывает', async () => {
    serve();
    renderSection();
    await screen.findByText('Учебная лаборатория ДЗЗ в вузе');
    const item = itemOf('Учебная лаборатория ДЗЗ в вузе');
    fireEvent.click(within(item).getByRole('button', { name: 'Записать, что мешает' }));

    const field = within(item).getByLabelText('Что мешает');
    expect(field).toHaveFocus();
    const save = within(item).getByRole('button', { name: 'Записать' });
    expect(save).toBeDisabled();
    fireEvent.change(field, { target: { value: 'Вуз не подписал договор аренды помещения' } });
    fireEvent.click(save);
    await waitFor(() =>
      expect(screen.queryByText('Учебная лаборатория ДЗЗ в вузе')).not.toBeInTheDocument(),
    );
  });

  it('задаче без ответственного — назначить из списка людей', async () => {
    serve();
    renderSection();
    await screen.findByText('Проект письма в Минсельхоз об итогах пилота');
    const item = itemOf('Проект письма в Минсельхоз об итогах пилота');
    expect(item).toHaveTextContent('ответственный не назначен');
    fireEvent.click(within(item).getByRole('button', { name: 'Назначить' }));
    fireEvent.change(within(item).getByLabelText('Кому'), { target: { value: 'p-karimov' } });
    fireEvent.click(within(item).getByRole('button', { name: 'Записать' }));
    await waitFor(() =>
      expect(
        screen.queryByText('Проект письма в Минсельхоз об итогах пилота'),
      ).not.toBeInTheDocument(),
    );
  });
});

describe('пороги', () => {
  it('меняются в границах, и до записи видно, сколько строк загорится', async () => {
    serve();
    renderSection();
    await openTab('Пороги');

    const burn = itemOf('Горит');
    expect(within(burn).getByLabelText('Значение: Горит')).toHaveValue(7);
    expect(burn).toHaveTextContent('Сейчас горят строк: 11');
    for (let step = 0; step < 3; step += 1) {
      fireEvent.click(within(burn).getByRole('button', { name: 'Больше: Горит' }));
    }
    expect(within(burn).getByLabelText('Значение: Горит')).toHaveValue(10);
    expect(await within(burn).findByText('→ станет 15')).toBeInTheDocument();

    fireEvent.click(within(burn).getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Порог «Горит» сохранён');
    await waitFor(() => expect(itemOf('Горит')).toHaveTextContent('Сейчас горят строк: 15'));
    expect(
      within(itemOf('Горит')).getByRole('button', { name: 'Вернуть 7 дн' }),
    ).toBeInTheDocument();
    expect(itemOf('Горит')).toHaveTextContent('по ТЗ — 7 дн');
  });

  it('«по ТЗ» — только у значений из ТЗ; у горячего дня — допущение', async () => {
    serve();
    renderSection();
    await openTab('Пороги');
    expect(itemOf('Горячий день')).toHaveTextContent('по умолчанию — 3 (допущение)');
    expect(itemOf('Горячий день')).not.toHaveTextContent('по ТЗ');
  });

  it('порог управляет обходом: подняли «молчит» — молчащие меньше порога ушли', async () => {
    serve();
    renderSection();
    await openTab('Пороги');
    const quiet = itemOf('Молчит');
    fireEvent.change(within(quiet).getByLabelText('Значение: Молчит'), { target: { value: '25' } });
    fireEvent.click(within(quiet).getByRole('button', { name: 'Сохранить' }));
    await screen.findByRole('status');

    await openTab('Обход');
    expect(
      screen.queryByText('Заказ услуги: аэрофотосъёмка Ферганской долины'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('Согласование проекта постановления с Минэкологии'),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Учебная лаборатория ДЗЗ в вузе')).toBeInTheDocument();
    expect(screen.getByText('осталось 10')).toBeInTheDocument();
  });

  it('порог изменили с другого устройства: отказ, набранное не пропало', async () => {
    serve();
    renderSection();
    await openTab('Пороги');
    const burn = () => itemOf('Горит');
    fireEvent.click(within(burn()).getByRole('button', { name: 'Больше: Горит' }));
    fireEvent.click(within(burn()).getByRole('button', { name: 'Больше: Горит' }));
    // Второе устройство успело записать своё.
    demoManagement.setThreshold('burn_days', 8, 1);

    fireEvent.click(within(burn()).getByRole('button', { name: 'Сохранить' }));
    expect(await within(burn()).findByRole('alert')).toHaveTextContent(/Порог изменили.*сейчас 8/);
    expect(within(burn()).getByLabelText('Значение: Горит')).toHaveValue(9);
  });

  it('за границей порог не записывается', async () => {
    serve();
    renderSection();
    await openTab('Пороги');
    const quiet = itemOf('Молчит');
    fireEvent.change(within(quiet).getByLabelText('Значение: Молчит'), { target: { value: '0' } });
    expect(within(quiet).getByRole('button', { name: 'Сохранить' })).toBeDisabled();
    expect(within(quiet).getByText('от 1 до 180')).toHaveClass('text-burn-ink');
  });
});

describe('справочники', () => {
  it('переименовать, выключить, поставить выше, добавить', async () => {
    serve();
    renderSection();
    await openTab('Справочники');
    fireEvent.click(screen.getByRole('button', { name: /^Типы задач/ }));

    fireEvent.click(screen.getByRole('button', { name: 'Переименовать: Прочее' }));
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Прочее и разное' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Прочее и разное')).toBeInTheDocument();

    fireEvent.click(
      within(itemOf('Выгрузка в субплатформу')).getByRole('button', { name: 'Выключить' }),
    );
    await waitFor(() => expect(itemOf('Выгрузка в субплатформу')).toHaveTextContent('выключено'));

    fireEvent.click(screen.getByRole('button', { name: 'Выше: Согласование' }));
    await waitFor(() => {
      const names = screen.getAllByRole('listitem').map((item) => item.textContent ?? '');
      const approval = names.findIndex((text) => text.startsWith('Согласование'));
      const review = names.findIndex((text) => text.startsWith('Рассмотрение и визирование'));
      expect(approval).toBeLessThan(review);
    });

    fireEvent.change(screen.getByLabelText('Новое значение'), {
      target: { value: 'Подготовка презентации' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));
    await waitFor(() => expect(itemOf('Подготовка презентации')).toHaveTextContent('записей: 0'));
  });

  it('статусы — без добавления и выключения: объяснено почему', async () => {
    serve();
    renderSection();
    await openTab('Справочники');
    fireEvent.click(screen.getByRole('button', { name: /^Статусы задач/ }));
    expect(screen.getByText(/Набор статусов задан правилами переходов/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Выключить' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Новое значение')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Переименовать: На проверке' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Выше: На проверке' })).toBeInTheDocument();
  });

  it('вид организации исправляется правкой', async () => {
    serve();
    renderSection();
    await openTab('Справочники');
    fireEvent.click(screen.getByRole('button', { name: /^Организации/ }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Переименовать: Агентство по гидрометеорологии' }),
    );
    fireEvent.change(screen.getByLabelText('Вид: Агентство по гидрометеорологии'), {
      target: { value: 'ministry' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() =>
      expect(itemOf('Агентство по гидрометеорологии')).toHaveTextContent('министерство'),
    );
  });

  it('недописанное «новое значение» не переезжает в соседний справочник', async () => {
    serve();
    renderSection();
    await openTab('Справочники');
    fireEvent.click(screen.getByRole('button', { name: /^Типы задач/ }));
    fireEvent.change(screen.getByLabelText('Новое значение'), { target: { value: 'Черновик' } });
    fireEvent.click(screen.getByRole('button', { name: /^Направления/ }));
    expect(screen.getByLabelText('Новое значение')).toHaveValue('');
  });

  it('у типа проекта — шаблон вех, по порядку сроков', async () => {
    serve();
    renderSection();
    await openTab('Справочники');
    fireEvent.click(
      within(itemOf('Нормативный акт')).getByRole('button', { name: 'Вехи шаблона' }),
    );

    const template = screen
      .getByRole('heading', { name: 'Вехи шаблона: Нормативный акт' })
      .closest('section')!;
    const steps = () =>
      within(template)
        .getAllByRole('listitem')
        .map((item) => item.textContent);
    expect(steps()).toEqual([
      expect.stringContaining('Разработка проекта акта'),
      expect.stringContaining('Согласование с министерствами и ведомствами'),
      expect.stringContaining('Внесение в Кабинет Министров'),
      expect.stringContaining('Принятие'),
    ]);

    fireEvent.change(within(template).getByPlaceholderText('Веха'), {
      target: { value: 'Экспертиза' },
    });
    fireEvent.change(within(template).getByLabelText('Через сколько дней от начала'), {
      target: { value: '45' },
    });
    fireEvent.click(within(template).getByRole('button', { name: 'Добавить веху' }));
    await waitFor(() => expect(steps()[1]).toContain('Экспертизачерез 45 дн'));

    fireEvent.click(within(template).getByRole('button', { name: 'Убрать: Принятие' }));
    await waitFor(() => expect(steps()).toHaveLength(4));
    expect(within(template).queryByText('Принятие')).not.toBeInTheDocument();
  });

  it('на телефоне — сначала список справочников, касание открывает один', async () => {
    setViewport({ width: 390 });
    serve();
    renderSection();
    await openTab('Справочники');
    fireEvent.click(screen.getByRole('button', { name: /^Регионы/ }));
    expect(screen.getByRole('heading', { name: 'Регионы' })).toBeInTheDocument();
    expect(screen.getByText(/Регионов четырнадцать/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Все справочники' }));
    expect(screen.getByRole('button', { name: /^Типы проектов/ })).toBeInTheDocument();
  });
});

describe('доступ', () => {
  it('дата выпуска и последний вход; перевыпуск переспрашивает', async () => {
    const calls = serve();
    renderSection();
    await openTab('Доступ');

    const assistant = screen.getByRole('heading', { name: 'Помощник' }).closest('section')!;
    await within(assistant).findByText('iPhone Safari');
    expect(assistant).toHaveTextContent(/Ссылка выпущена .* · последний вход/);
    expect(screen.getByText(/Устройства и перевыпуск — настоящие/)).toBeInTheDocument();

    fireEvent.click(within(assistant).getByRole('button', { name: 'Перевыпустить ссылку' }));
    expect(within(assistant).getByText(/перестанут работать сразу/)).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'POST')).toBe(false);

    fireEvent.click(within(assistant).getByRole('button', { name: 'Перевыпустить' }));
    expect(await within(assistant).findByText(/Ссылка показывается один раз/)).toBeInTheDocument();
    expect(calls).toContainEqual({ method: 'POST', path: '/api/access/links/assistant' });
    // Дата настоящего перевыпуска остаётся и после смены вкладки.
    await waitFor(() =>
      expect(demoManagement.view().links[0]?.issued_at).toBe('2026-09-29T04:00:00Z'),
    );
    expect(screen.getByText(/Загрузка таблиц Ижро — вместе с разделом Ижро/)).toBeInTheDocument();
  });
});

describe('последний вход', () => {
  it('виден и без открытых сессий: после перевыпуска или истечения он остаётся', async () => {
    serve();
    vi.mocked(globalThis.fetch).mockImplementation((input) => {
      const path =
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (path === '/api/me') return Promise.resolve(reply(200, user('assistant')));
      if (path === '/api/health') return Promise.resolve(reply(200, HEALTH));
      if (path.startsWith('/api/access/sessions/')) return Promise.resolve(reply(200, []));
      return Promise.resolve(reply(404, { detail: path }));
    });
    renderSection();
    await openTab('Доступ');
    const leader = screen.getByRole('heading', { name: 'Руководитель' }).closest('section')!;
    await within(leader).findByText('Открытых сессий нет');
    expect(leader).toHaveTextContent(/последний вход/);
    expect(leader).not.toHaveTextContent(/ни разу/);
  });
});

describe('руководитель', () => {
  it('пороги и справочники без правки; обход и доступ — помощника, /api/access не трогается', async () => {
    const calls = serve('leader');
    renderSection();

    await waitFor(() =>
      expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
        'Пороги',
        'Справочники',
      ]),
    );
    expect(screen.getByText(/Управление ведёт помощник/)).toBeInTheDocument();
    expect(itemOf('Горит')).toHaveTextContent('7 дн');
    expect(screen.queryByRole('button', { name: 'Больше: Горит' })).not.toBeInTheDocument();

    await openTab('Справочники');
    expect(screen.queryByRole('button', { name: /^Переименовать/ })).not.toBeInTheDocument();
    expect(calls.filter((call) => call.path.startsWith('/api/access/'))).toEqual([]);
  });
});

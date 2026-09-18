/**
 * Формы создания и правки проекта (ORB-086).
 *
 * Проверяется не то, что поля отрисовались, а четыре обещания, каждое из которых
 * ломается незаметно.
 *
 * **Создание доходит до сервера теми полями, что показаны.** Форма, которая теряет одно
 * поле из четырнадцати, выглядит рабочей: проект создаётся, и пропажа обнаруживается
 * через неделю на чужом вопросе «а где куратор».
 *
 * **После сохранения открывается карточка, а не список.** Список не отвечает на вопрос
 * «сохранилось ли то, что я вводил», и человек открывает запись сам — каждый раз.
 *
 * **Переключатель выдачи наружу есть и показывает умолчание.** Без него каждый новый
 * проект уходит наружу молча — ADR-0024 называет это плохим последствием прямо, и
 * закрыть его должна была именно эта карточка.
 *
 * **Правка приходит заполненной и не теряет того, чего не трогали.** Форма правки,
 * открывшаяся пустой, стирает проект одним нажатием «Сохранить».
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Mode } from '../../shared/mode/ModeContext';
import { WithMode } from '../../testing/WithMode';
import { ProjectCardPage } from './ProjectCardPage';
import { EditProjectPage, NewProjectPage } from './ProjectFormPage';

const NAMES = (ru: string) => ({ ru, uz_cyrl: ru, uz_latn: ru });

const DICTIONARIES = {
  directions: [
    { id: 'dir-1', code: 'space', name: NAMES('Космический мониторинг') },
    { id: 'dir-2', code: 'geo', name: NAMES('Геоинформатика') },
  ],
  // Порядок намеренно не алфавитный: форма обязана брать его из справочника.
  project_statuses: [
    { id: 's-1', code: 'initiation', name: NAMES('Инициация'), requires_reason: false },
    { id: 's-2', code: 'in_progress', name: NAMES('В работе'), requires_reason: false },
    { id: 's-3', code: 'on_hold', name: NAMES('Приостановлен'), requires_reason: true },
  ],
  task_statuses: [],
  // «Срочно» стоит первым, как в настоящем справочнике: форма обязана открыться на
  // «обычном», иначе через месяц срочно всё.
  priorities: [
    { id: 'pr-1', code: 'urgent', name: NAMES('Срочно') },
    { id: 'pr-2', code: 'normal', name: NAMES('Обычный') },
  ],
};

const PEOPLE = [
  { id: 'per-1', full_name: 'Каримов А.', position: 'Начальник отдела', department: null },
  { id: 'per-2', full_name: 'Юсупова Д.', position: null, department: null },
];

const STATION = {
  id: 'p-1',
  code: 'PRJ-2026-001',
  title: 'Приёмная станция ДЗЗ',
  description: 'Строительство станции приёма данных',
  kind: 'project' as const,
  share_externally: false,
  direction_id: 'dir-2',
  curator_person_id: 'per-1',
  status_code: 'on_hold',
  status_reason: 'Ждём поставку антенны',
  priority_code: 'urgent',
  started_on: '2026-01-15',
  due_on: '2026-08-28',
  finished_on: null,
  progress_pct: 40,
  progress_mode: 'manual' as const,
  budget_note: '12 млрд сум',
  impediment: null,
  impediment_updated_at: null,
  impediment_is_stale: false,
  impediment_is_active: false,
  health: 'yellow' as const,
};

const fetchMock = vi.fn();

/** Что ответит сервер на запись. По умолчанию — созданный проект. */
let saveResponse: { body: unknown; status: number } = {
  body: { ...STATION, id: 'p-new', code: 'PRJ-2026-007' },
  status: 201,
};

function answer(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

/**
 * Приложение с настоящим маршрутизатором, а не форма в пустоте.
 *
 * Иначе главное обещание — «после сохранения открывается карточка» — проверить нечем:
 * переход это и есть проверяемое поведение, и подменённый `useNavigate` подтвердил бы
 * только то, что его вызвали.
 */
function renderAt(path: string, value: Mode = 'assistant') {
  const router = createMemoryRouter(
    [
      { path: '/projects/new', element: <NewProjectPage /> },
      { path: '/projects/:id/edit', element: <EditProjectPage /> },
      { path: '/projects/:id', element: <ProjectCardPage /> },
      { path: '/403', element: <p>Нет доступа</p> },
    ],
    { initialEntries: [path] },
  );
  render(
    <WithMode mode={value}>
      <RouterProvider router={router} />
    </WithMode>,
  );
  return router;
}

/** Тела всех записывающих запросов — по ним видно, что именно ушло на сервер. */
function writes(): { url: string; method: string; body: Record<string, unknown> }[] {
  return fetchMock.mock.calls
    .filter((call) => {
      const method = (call[1] as RequestInit | undefined)?.method;
      return method === 'POST' || method === 'PATCH';
    })
    .map((call) => ({
      url: String(call[0]),
      method: String((call[1] as RequestInit).method),
      body: JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>,
    }));
}

beforeEach(() => {
  saveResponse = {
    body: { ...STATION, id: 'p-new', code: 'PRJ-2026-007' },
    status: 201,
  };

  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  // Подделка отвечает по идентификатору, а не одним проектом на любой адрес. Иначе
  // карточка созданного проекта показывала бы чужие данные, а тест этого не заметил бы:
  // проверка «открылась карточка» прошла бы на записи, которую никто не создавал.
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      return answer(saveResponse.body, saveResponse.status);
    }
    if (url.includes('/dictionaries')) return answer(DICTIONARIES);
    if (url.includes('/people')) return answer(PEOPLE);
    if (url.includes('/projects/p-new')) return answer(saveResponse.body);
    if (url.includes('/projects/p-1')) return answer(STATION);
    return answer([STATION]);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('создание проекта', () => {
  it('заполненная форма доходит до сервера теми полями, что в ней показаны', async () => {
    const user = userEvent.setup();
    renderAt('/projects/new');

    await user.type(await screen.findByLabelText(/Название/), 'Наземный комплекс');
    await user.selectOptions(screen.getByLabelText(/Направление/), 'dir-2');
    await user.selectOptions(screen.getByLabelText(/Куратор/), 'per-1');
    await user.type(screen.getByLabelText(/Срок/), '2026-12-31');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => {
      expect(writes()).toHaveLength(1);
    });

    const [sent] = writes();
    expect(sent?.method).toBe('POST');
    expect(sent?.url).toContain('/projects');
    expect(sent?.body).toMatchObject({
      title: 'Наземный комплекс',
      direction_id: 'dir-2',
      curator_person_id: 'per-1',
      due_on: '2026-12-31',
      status_code: 'initiation',
      kind: 'project',
      progress_mode: 'auto',
    });
  });

  it('приоритет по умолчанию обычный, а не первый в справочнике', async () => {
    renderAt('/projects/new');

    // «Срочно» стоит в справочнике первым. Форма, открывающаяся на нём, через месяц даёт
    // портфель, где срочно всё, — то есть светофор, который ничего не значит.
    expect(await screen.findByLabelText(/Приоритет/)).toHaveValue('normal');
  });

  it('срок не подставлен: подставленную дату сохраняют не читая', async () => {
    renderAt('/projects/new');

    expect(await screen.findByLabelText(/Срок/)).toHaveValue('');
    // Дата начала, наоборот, заполнена: это единственное значение, которое почти всегда
    // верно, и требовать его ввода — лишний ввод на каждом проекте.
    expect(screen.getByLabelText(/Начало/)).not.toHaveValue('');
  });

  it('переключатель выдачи наружу стоит в форме и включён по умолчанию', async () => {
    const user = userEvent.setup();
    renderAt('/projects/new');

    // Умолчание в базе — `true`. Форма обязана его показать: невидимое умолчание — это
    // и есть «проект уходит наружу, а помощник об этом не узнаёт» (ADR-0024).
    const toggle = await screen.findByLabelText(/Показывать наружу/);
    expect(toggle).toBeChecked();

    // Подпись говорит, что именно произойдёт, а не «секретно»: грифа в системе нет.
    expect(screen.getByText(/Google-календарь/)).toBeInTheDocument();
    expect(screen.getByText(/подсказки ИИ/)).toBeInTheDocument();

    await user.click(toggle);
    await user.type(screen.getByLabelText(/Название/), 'Закрытая работа');
    await user.type(screen.getByLabelText(/Срок/), '2026-12-31');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => {
      expect(writes()[0]?.body).toMatchObject({ share_externally: false });
    });
  });

  it('после сохранения открывается карточка проекта, а не список', async () => {
    const user = userEvent.setup();
    const router = renderAt('/projects/new');

    await user.type(await screen.findByLabelText(/Название/), 'Наземный комплекс');
    await user.type(screen.getByLabelText(/Срок/), '2026-12-31');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    // Адрес — карточки созданного проекта, а не списка: идентификатор берётся из ответа
    // сервера, потому что до ответа его не существует.
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/projects/p-new');
    });
    expect(await screen.findByText('PRJ-2026-007')).toBeInTheDocument();
  });

  it('причина спрашивается там, где её требует справочник, и не пускает без неё', async () => {
    const user = userEvent.setup();
    renderAt('/projects/new');

    await user.type(await screen.findByLabelText(/Название/), 'Проект на паузе');
    await user.type(screen.getByLabelText(/Срок/), '2026-12-31');

    // Поля причины нет, пока статус её не требует: постоянный вопрос, на который в
    // девяти случаях из десяти нечего ответить, заполняют мусором.
    expect(screen.queryByLabelText(/Причина/)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Статус/), 'on_hold');
    expect(screen.getByLabelText(/Причина/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    // Запрос не уходит вовсе: сервер его отклонит (ТЗ 7), и показать отказ после
    // отправки — значит показать, что система передумала.
    expect(writes()).toHaveLength(0);
    expect(await screen.findByText(/без причины не сохранить/)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Причина/), 'Ждём решения по площадке');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => {
      expect(writes()[0]?.body).toMatchObject({
        status_code: 'on_hold',
        status_reason: 'Ждём решения по площадке',
      });
    });
  });

  it('отказ сервера по полю показывается у этого поля, а не только сверху', async () => {
    saveResponse = {
      status: 422,
      body: {
        title: 'Данные не прошли проверку',
        detail: 'Проверьте значения полей',
        errors: [{ field: 'due_on', message: 'Срок не может быть раньше начала', type: 'value' }],
      },
    };

    const user = userEvent.setup();
    renderAt('/projects/new');

    await user.type(await screen.findByLabelText(/Название/), 'Наземный комплекс');
    await user.type(screen.getByLabelText(/Срок/), '2020-01-01');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    // Сообщение стоит у поля и связано с ним: общая строка сверху заставляет искать
    // поле глазами, а на форме из четырнадцати полей это ищут долго.
    const message = await screen.findByText('Срок не может быть раньше начала');
    const field = screen.getByLabelText(/Срок/);
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field.getAttribute('aria-describedby')).toContain(message.id);
  });

  it('процента выполнения в режиме «по задачам» нет вовсе и он не отправляется', async () => {
    const user = userEvent.setup();
    renderAt('/projects/new');

    await user.type(await screen.findByLabelText(/Название/), 'Наземный комплекс');
    await user.type(screen.getByLabelText(/Срок/), '2026-12-31');
    await user.click(screen.getByRole('button', { name: /Показать остальные поля/ }));

    // Заблокированное поле рядом с числом, которое считает сервер, выглядит сломанным —
    // и первое, что делают, это пробуют его починить.
    expect(screen.queryByLabelText(/Выполнено/)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Как считать выполнение/), 'manual');
    await user.clear(screen.getByLabelText(/Выполнено/));
    await user.type(screen.getByLabelText(/Выполнено/), '30');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => {
      expect(writes()[0]?.body).toMatchObject({ progress_mode: 'manual', progress_pct: 30 });
    });
  });

  it('руководителя на форму не пускает: запись — дело помощника', async () => {
    const router = renderAt('/projects/new', 'leader');

    // Ссылок сюда ему не показывают, но адрес можно набрать руками, и отказ сервера на
    // сохранении — худший способ об этом узнать: к тому моменту форма уже заполнена.
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/403');
    });
  });
});

describe('правка проекта', () => {
  it('форма открывается заполненной значениями проекта', async () => {
    renderAt('/projects/p-1/edit');

    expect(await screen.findByLabelText(/Название/)).toHaveValue('Приёмная станция ДЗЗ');
    expect(screen.getByLabelText(/Направление/)).toHaveValue('dir-2');
    expect(screen.getByLabelText(/Куратор/)).toHaveValue('per-1');
    expect(screen.getByLabelText(/Статус/)).toHaveValue('on_hold');
    expect(screen.getByLabelText(/Причина/)).toHaveValue('Ждём поставку антенны');
    expect(screen.getByLabelText(/Начало/)).toHaveValue('2026-01-15');
    expect(screen.getByLabelText(/Срок/)).toHaveValue('2026-08-28');
    // Проект, которому выдача наружу выключена, обязан открыться с выключенным флажком:
    // иначе правка названия молча включает выдачу.
    expect(screen.getByLabelText(/Показывать наружу/)).not.toBeChecked();
  });

  it('правка одного поля не теряет остальные', async () => {
    const user = userEvent.setup();
    renderAt('/projects/p-1/edit');

    const title = await screen.findByLabelText(/Название/);
    await user.clear(title);
    await user.type(title, 'Приёмная станция ДЗЗ, вторая очередь');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => {
      expect(writes()).toHaveLength(1);
    });

    const [sent] = writes();
    expect(sent?.method).toBe('PATCH');
    expect(sent?.url).toContain('/projects/p-1');
    expect(sent?.body).toMatchObject({
      title: 'Приёмная станция ДЗЗ, вторая очередь',
      direction_id: 'dir-2',
      curator_person_id: 'per-1',
      status_code: 'on_hold',
      status_reason: 'Ждём поставку антенны',
      started_on: '2026-01-15',
      due_on: '2026-08-28',
      share_externally: false,
      budget_note: '12 млрд сум',
      progress_mode: 'manual',
      progress_pct: 40,
    });
  });

  it('при правке справочники запрашиваются вместе с недействующими значениями', async () => {
    renderAt('/projects/p-1/edit');
    await screen.findByLabelText(/Название/);

    // Иначе направление, выведенное из обращения, исчезнет из списка, и правка названия
    // молча заменит его первым доступным.
    const asked = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(asked.some((url) => url.includes('/dictionaries?active_only=false'))).toBe(true);
    expect(asked.some((url) => url.includes('/people?active_only=false'))).toBe(true);
  });

  it('форма создания недействующие значения не предлагает', async () => {
    renderAt('/projects/new');
    await screen.findByLabelText(/Название/);

    const asked = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(asked.some((url) => url.includes('/dictionaries?active_only=true'))).toBe(true);
  });
});

describe('карточка проекта', () => {
  it('показывает то, что вносится формой, включая выдачу наружу', async () => {
    renderAt('/projects/p-1');

    expect(await screen.findByText('Приёмная станция ДЗЗ')).toBeInTheDocument();
    expect(screen.getByText('PRJ-2026-001')).toBeInTheDocument();
    expect(screen.getByText('Приостановлен')).toBeInTheDocument();
    expect(screen.getByText('Каримов А.')).toBeInTheDocument();
    expect(screen.getByText('Ждём поставку антенны')).toBeInTheDocument();
    // Состояние выдачи наружу видно в обоих значениях, а не только когда она включена:
    // поле, заметное лишь в одном состоянии, читается как отсутствующее.
    expect(screen.getByText(/не уходит ни в одну выдачу наружу/)).toBeInTheDocument();
  });

  it('ведёт на правку помощника и не показывает её руководителю', async () => {
    renderAt('/projects/p-1');
    expect(await screen.findByRole('link', { name: 'Правка' })).toHaveAttribute(
      'href',
      '/projects/p-1/edit',
    );
  });

  it('руководителю ссылки на правку нет: карточка ему только для чтения', async () => {
    renderAt('/projects/p-1', 'leader');

    await screen.findByText('Приёмная станция ДЗЗ');
    expect(screen.queryByRole('link', { name: 'Правка' })).not.toBeInTheDocument();
  });
});

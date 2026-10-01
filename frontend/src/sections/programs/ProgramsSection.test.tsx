/**
 * Экран «Программы» против ответа API: горизонт лет с подпроектами, отсчёт, «до конца
 * года», «успеваем?» с действиями, карточка программы, телефон без шкалы, монитор с
 * раскрытыми подпроектами.
 *
 * Числа и порядок считает сервер и проверяет `backend/tests/test_programs.py`. Здесь — что
 * экран делает с ответом и куда ведут действия: «перенести дату» и «урезать объём»
 * открывают настоящую карточку проекта. Сеть подменена на уровне `fetch`.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { card as projectCard, detail as projectDetail } from '@/sections/projects/test-data';
import type { CurrentUser } from '@/shared/api/orbita';
import { setViewport } from '@/test-setup';

import type { ProgramMilestone, YearEndRow } from './model';
import { ProgramsSection } from './ProgramsSection';
import { view } from './test-data';
import { YearEndCard } from './YearEndCard';

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

/** Справочники для названий статусов; `null` — их нет, и названия идут по ключам перевода. */
let dictionaries: unknown = null;

function serve(role: 'leader' | 'assistant' = 'leader') {
  const paths: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    paths.push(path);
    if (path === '/api/me') return Promise.resolve(reply(200, user(role)));
    if (path === '/api/v1/programs') return Promise.resolve(reply(200, view()));
    if (path === '/api/v1/dictionaries' && dictionaries) {
      return Promise.resolve(reply(200, dictionaries));
    }
    const project = /^\/api\/v1\/projects\/([^/?]+)$/.exec(path);
    if (project) {
      const id = project[1]!;
      return Promise.resolve(
        reply(200, projectDetail(projectCard({ id, title: `Карточка ${id}`, is_multiyear: true }))),
      );
    }
    return Promise.resolve(reply(404, { detail: `нет подмены ${path}` }));
  });
  return paths;
}

function renderPrograms() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProgramsSection />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  dictionaries = null;
});

describe('Программы', () => {
  it('ноутбук: горизонт лет, «до конца года» и «успеваем?» рядом', async () => {
    serve();
    renderPrograms();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    const horizon = screen.getByRole('region', { name: 'Горизонт 2026–2030' });
    for (const year of ['2026', '2027', '2028', '2029', '2030']) {
      expect(within(horizon).getByText(year)).toBeInTheDocument();
    }
    expect(within(horizon).getByText('осталось 590 дн')).toBeInTheDocument();
    // Стратегия‑2035 не растягивает шкалу: полоса обрезана с подписью года.
    expect(within(horizon).getByText('до 2035 →')).toBeInTheDocument();
    // «Не успеваем» — в строке программы, а не только в карточке рядом.
    expect(within(horizon).getByText('не успеваем, не хватает 45 дн')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: 'До конца 2026 года' })).toBeInTheDocument();
    expect(
      screen.getByRole('region', { name: 'Просрочено — должно случиться в этом году' }),
    ).toBeInTheDocument();
    // Знаменатель — программы с прогнозом; без прогноза — отдельно (ТЗ 5).
    expect(
      screen.getByText('Не успевают: 1 из 2 с прогнозом · без прогноза: 2'),
    ).toBeInTheDocument();
  });

  it('подпроекты раскрываются под программой', async () => {
    serve();
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    expect(within(horizon).queryByText('Геопортал агентства')).not.toBeInTheDocument();

    const toggle = within(horizon).getByRole('button', { name: /Подпроекты: 1/ });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(within(horizon).getByText('Геопортал агентства')).toBeInTheDocument();
  });

  it('карточка программы: отсчёт, «успеваем?», вехи по годам с исходными сроками', async () => {
    serve();
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    fireEvent.click(within(horizon).getAllByRole('button', { name: /^Спутниковая миссия/ })[0]!);

    const panel = screen.getByRole('dialog');
    expect(within(panel).getByText('осталось 590 дн')).toBeInTheDocument();
    expect(
      within(panel).getByText(
        'Мало данных: за 90 дн закрыто задач 4, а для прогноза нужно не меньше 10.',
      ),
    ).toBeInTheDocument();
    expect(within(panel).getByRole('region', { name: '2027' })).toBeInTheDocument();
    // Перенесённая веха — «исходный → текущий» (ТЗ 11).
    expect(within(panel).getByText(/15\.12\.2026 → 25\.01\.2027/)).toBeInTheDocument();
    // Вехи подпроектов — рядом со своими, с подписью, чьи они; ступень — словом.
    expect(within(panel).getByText(/подпроект «Пилот: калибровка снимков»/)).toBeInTheDocument();
    expect(within(panel).getAllByText('Ждёт решения').length).toBeGreaterThan(0);
    expect(within(panel).getByText(/готово 28 % с подпроектами/)).toBeInTheDocument();
  });

  it('«перенести дату» открывает карточку проекта на «что если»', async () => {
    const paths = serve('leader');
    renderPrograms();
    await screen.findByText('Не успевают: 1 из 2 с прогнозом · без прогноза: 2');

    fireEvent.click(screen.getAllByRole('button', { name: 'Перенести дату' })[0]!);
    const sheet = screen.getByRole('dialog', { name: 'Проекты' });
    expect(await within(sheet).findByText('Карточка pr-catalogue')).toBeInTheDocument();
    expect(within(sheet).getByRole('heading', { name: 'Что если' })).toBeInTheDocument();
    expect(paths).toContain('/api/v1/projects/pr-catalogue');
  });

  it('«открыть карточку проекта» из карточки программы сменяет лист', async () => {
    serve();
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    fireEvent.click(within(horizon).getAllByRole('button', { name: /^Наземная/ })[0]!);
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Открыть карточку проекта' }),
    );

    expect(await screen.findByText('Карточка pr-infrastructure')).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  it('«до конца года» ведёт в программу вехи', async () => {
    serve();
    renderPrograms();
    const overdue = await screen.findByRole('region', {
      name: 'Просрочено — должно случиться в этом году',
    });
    fireEvent.click(within(overdue).getByRole('button', { name: /Площадка станции приёма/ }));
    expect(
      within(screen.getByRole('dialog')).getByRole('heading', {
        name: 'Наземная инфраструктура ДЗЗ 2026–2030',
      }),
    ).toBeInTheDocument();
  });

  it('завершённые свёрнуты', async () => {
    serve();
    renderPrograms();
    const toggle = await screen.findByRole('button', { name: 'Завершённые и отменённые: 1' });
    expect(screen.queryByText('Цифровизация агентства 2023–2025')).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText('Цифровизация агентства 2023–2025')).toBeInTheDocument();
  });

  it('статус завершённой — название из справочника (V25)', async () => {
    const name = { ru: 'Закрыт', uz_cyrl: 'Закрыт', uz_latn: 'Закрыт' };
    dictionaries = {
      project_types: [],
      task_types: [],
      directions: [],
      regions: [],
      project_statuses: [{ id: 'done', code: 'done', name, sort_order: 30, is_active: true }],
      task_statuses: [],
    };
    serve();
    renderPrograms();
    fireEvent.click(await screen.findByRole('button', { name: 'Завершённые и отменённые: 1' }));

    const closed = screen.getByRole('button', { name: /Цифровизация агентства 2023–2025/ });
    await waitFor(() => expect(closed).toHaveTextContent(/Закрыт · /));
    expect(closed).not.toHaveTextContent('Завершён');
  });

  it('телефон: плитки с отсчётом и вехами по годам, без шкалы', async () => {
    setViewport({ width: 390 });
    serve();
    renderPrograms();

    // Первое упоминание — плитка; ниже та же программа в «Успеваем к дате?».
    const [tile] = await screen.findAllByText('Спутниковая миссия «Навоий-2»');
    expect(screen.queryByRole('region', { name: 'Горизонт 2026–2030' })).not.toBeInTheDocument();
    expect(screen.getAllByText('Вехи по годам').length).toBe(4);
    expect(screen.getByText('не успеваем, не хватает 45 дн')).toBeInTheDocument();

    fireEvent.click(tile!);
    expect(within(screen.getByRole('dialog')).getByText('Вехи по годам')).toBeInTheDocument();
  });

  it('монитор: подпроекты раскрыты сразу', async () => {
    setViewport({ width: 2560 });
    serve();
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    expect(within(horizon).getByText('Пилот: калибровка снимков')).toBeInTheDocument();
    expect(within(horizon).getByText('Геопортал агентства')).toBeInTheDocument();
  });
});

describe('До конца года', () => {
  function row(id: string, patch: Partial<ProgramMilestone>): YearEndRow {
    return {
      milestone: {
        id,
        title: `Веха ${id}`,
        due_on: '2026-09-20',
        original_due_on: '2026-09-20',
        is_passed: false,
        passed_on: null,
        days_left: -7,
        step: 'overdue',
        deviation: 7,
        ...patch,
      },
      program: { id: 'pr-1', code: 'PRJ-2026-001', title: 'Программа' },
      subproject: null,
      responsible: null,
    };
  }

  it('«просрочено N» и группа «Просрочено» — одно правило: срок прошёл', () => {
    // Просроченная веха с вопросом руководителю стоит на ступени «ждёт решения», но в
    // просроченных она всё равно числится — и в числе, и в группе.
    render(
      <YearEndCard
        rows={[row('a', {}), row('b', { step: 'awaiting_decision', deviation: 2, days_left: -3 })]}
        year={2026}
        asOf="2026-09-27T07:00:00Z"
        onOpen={() => undefined}
      />,
    );
    expect(screen.getByText(/просрочено 2/)).toBeInTheDocument();
    const group = screen.getByRole('region', { name: 'Просрочено — должно случиться в этом году' });
    expect(within(group).getAllByRole('button')).toHaveLength(2);
    expect(within(group).getByText('Ждёт решения')).toBeInTheDocument();
  });
});

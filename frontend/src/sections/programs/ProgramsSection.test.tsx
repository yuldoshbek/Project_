/**
 * Экран «Программы»: горизонт лет с подпроектами, отсчёт, «до конца года», «успеваем?» с
 * действиями, карточка программы, телефон без шкалы, монитор с раскрытыми подпроектами.
 *
 * Данные — вымышленный сервер `demo.ts`; день закреплён, чтобы отсчёт и «до конца года»
 * не зависели от дня запуска.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setViewport } from '@/test-setup';

import type { ProgramMilestone, YearEndRow } from './model';
import { ProgramsSection } from './ProgramsSection';
import { YearEndCard } from './YearEndCard';

const NOW = new Date('2026-09-27T07:00:00Z');

function renderPrograms() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProgramsSection />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe('Программы', () => {
  it('ноутбук: горизонт лет, «до конца года» и «успеваем?» рядом', async () => {
    renderPrograms();

    expect(await screen.findByText('Вымышленные данные')).toBeInTheDocument();
    const horizon = screen.getByRole('region', { name: 'Горизонт 2026–2030' });
    for (const year of ['2026', '2027', '2028', '2029', '2030']) {
      expect(within(horizon).getByText(year)).toBeInTheDocument();
    }
    // Отсчёт до даты — у каждой программы на шкале.
    expect(within(horizon).getByText('осталось 591 дн')).toBeInTheDocument();
    // Стратегия‑2035 не растягивает шкалу: полоса обрезана с подписью года.
    expect(within(horizon).getByText('до 2035 →')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: 'До конца 2026 года' })).toBeInTheDocument();
    expect(
      screen.getByRole('region', { name: 'Просрочено — должно случиться в этом году' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Не успевают: 1 из 4 с прогнозом · без прогноза: 1'),
    ).toBeInTheDocument();
  });

  it('подпроекты раскрываются под программой', async () => {
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    expect(within(horizon).queryByText('Геопортал агентства')).not.toBeInTheDocument();

    // Первой стоит молчащая программа — порядок лестницы, а не алфавит.
    const toggles = within(horizon).getAllByRole('button', { name: /Подпроекты: 2/ });
    fireEvent.click(toggles[0]!);
    expect(toggles[0]).toHaveAttribute('aria-expanded', 'true');
    expect(within(horizon).getByText('Геопортал агентства')).toBeInTheDocument();
  });

  it('карточка программы: отсчёт, «успеваем?», вехи по годам с исходными сроками', async () => {
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    fireEvent.click(within(horizon).getAllByRole('button', { name: /^Спутниковая миссия/ })[0]!);

    const panel = screen.getByRole('dialog');
    expect(within(panel).getByText('осталось 591 дн')).toBeInTheDocument();
    expect(within(panel).getByText(/^Не успеваем: за 90 дн закрыто 11/)).toBeInTheDocument();
    expect(within(panel).getByRole('region', { name: '2027' })).toBeInTheDocument();
    // Перенесённая веха — «исходный → текущий» (ТЗ 11).
    expect(within(panel).getByText(/15\.12\.2026 → 25\.01\.2027/)).toBeInTheDocument();
    // Вехи подпроектов — рядом со своими, с подписью, чьи они.
    expect(
      within(panel).getAllByText(/подпроект «Пилот: калибровка снимков»/).length,
    ).toBeGreaterThan(0);
  });

  it('«не успеваем» предлагает перенести дату или урезать объём', async () => {
    renderPrograms();
    await screen.findByText('Не успевают: 1 из 4 с прогнозом · без прогноза: 1');
    fireEvent.click(screen.getAllByRole('button', { name: 'Перенести дату' })[0]!);
    expect(screen.getByRole('status')).toHaveTextContent('«что если»');
    fireEvent.click(screen.getAllByRole('button', { name: 'Урезать объём' })[0]!);
    expect(screen.getByRole('status')).toHaveTextContent('вехах и подпроектах');
  });

  it('«до конца года» ведёт в программу вехи', async () => {
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
    renderPrograms();
    const toggle = await screen.findByRole('button', { name: 'Завершённые и отменённые: 1' });
    expect(screen.queryByText('Цифровизация агентства 2023–2025')).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText('Цифровизация агентства 2023–2025')).toBeInTheDocument();
  });

  it('телефон: плитки с отсчётом и вехами по годам, без шкалы', async () => {
    setViewport({ width: 390 });
    renderPrograms();

    // Первое упоминание — плитка; ниже та же программа в «Успеваем к дате?».
    const [tile] = await screen.findAllByText('Спутниковая миссия «Навоий-2»');
    expect(screen.queryByRole('region', { name: 'Горизонт 2026–2030' })).not.toBeInTheDocument();
    expect(screen.getAllByText('Вехи по годам').length).toBe(5);

    fireEvent.click(tile!);
    expect(within(screen.getByRole('dialog')).getByText('Вехи по годам')).toBeInTheDocument();
  });

  it('монитор: подпроекты раскрыты сразу', async () => {
    setViewport({ width: 2560 });
    renderPrograms();
    const horizon = await screen.findByRole('region', { name: 'Горизонт 2026–2030' });
    expect(within(horizon).getByText('Пилот: калибровка снимков')).toBeInTheDocument();
    expect(within(horizon).getByText('IAC-2028: площадка и логистика')).toBeInTheDocument();
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

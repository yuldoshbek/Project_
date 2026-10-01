/**
 * Ответ API раздела для тестов экрана — одна фабрика на все тесты раздела.
 *
 * Числа здесь не считаются: отсчёт, ступени, готовность и «успеваем?» считает сервер и
 * проверяет `backend/tests/test_programs.py`; тест экрана проверяет, что экран делает с
 * ответом. Даты — от `AS_OF`, 27.09.2026: «сегодня» экран берёт из ответа (`as_of`), а не с
 * часов, поэтому часы тестам закреплять не нужно.
 */

import type {
  Pace,
  ProgramCard,
  ProgramMilestone,
  ProgramsView,
  Subproject,
  YearEndRow,
} from './model';

export const AS_OF = '2026-09-27T07:00:00Z';

export function mark(
  overrides: Partial<ProgramMilestone> & Pick<ProgramMilestone, 'id' | 'title' | 'due_on'>,
): ProgramMilestone {
  return {
    original_due_on: overrides.due_on,
    is_passed: false,
    passed_on: null,
    days_left: 0,
    step: null,
    deviation: 0,
    ...overrides,
  };
}

function sub(overrides: Partial<Subproject> & Pick<Subproject, 'id' | 'title'>): Subproject {
  return {
    code: `PRJ-2026-${overrides.id.slice(-3)}`,
    status: 'in_progress',
    responsible: { id: 'p-karimov', name: 'Каримов А.' },
    started_on: '2026-09-07',
    due_on: '2027-02-04',
    original_due_on: '2027-02-04',
    readiness: 20,
    step: null,
    deviation: 0,
    milestones: [],
    ...overrides,
  };
}

function program(overrides: Partial<ProgramCard> & Pick<ProgramCard, 'id' | 'title'>): ProgramCard {
  return {
    code: `PRJ-2026-${overrides.id.slice(-3)}`,
    type: { code: 'platform', name: 'Платформа или ИТ' },
    status: 'in_progress',
    responsible: { id: 'p-tursunov', name: 'Турсунов Б.' },
    started_on: '2026-01-12',
    due_on: '2030-12-15',
    original_due_on: '2030-12-15',
    days_left: 1540,
    readiness: 30,
    lag_days: -100,
    step: null,
    deviation: 0,
    milestones: [],
    subprojects: [],
    pace: null,
    ...overrides,
  };
}

const PACE: Pace = {
  verdict: 'on_track',
  window_days: 90,
  closed: 12,
  closed_tasks: 11,
  min_closed_tasks: 10,
  remaining: 20,
  forecast_on: '2027-02-14',
  gap_days: -1400,
};

const SITE = mark({
  id: 'ms-site',
  title: 'Площадка станции приёма в Самарканде',
  due_on: '2026-08-31',
  days_left: -27,
  step: 'overdue',
  deviation: 27,
});

const AGREEMENT = mark({
  id: 'ms-agreement',
  title: 'Согласование ТЗ на спутниковую группировку',
  due_on: '2026-09-30',
  days_left: 3,
  step: 'awaiting_decision',
  deviation: 6,
});

const CONTRACT = mark({
  id: 'ms-contract',
  title: 'Договор с изготовителем',
  due_on: '2027-01-25',
  original_due_on: '2026-12-15',
  days_left: 120,
});

const FIELD = mark({
  id: 'ms-field',
  title: 'Полевые измерения на полигоне',
  due_on: '2026-10-20',
  days_left: 23,
});

export const ITEMS: ProgramCard[] = [
  program({
    id: 'pr-infrastructure',
    title: 'Наземная инфраструктура ДЗЗ 2026–2030',
    step: 'silent',
    deviation: 16,
    milestones: [
      mark({
        id: 'ms-feasibility',
        title: 'Технико-экономическое обоснование',
        due_on: '2026-04-30',
        is_passed: true,
        passed_on: '2026-05-12',
        days_left: -150,
      }),
      SITE,
      mark({ id: 'ms-station', title: 'Приёмка программы', due_on: '2030-12-15', days_left: 1540 }),
    ],
    subprojects: [sub({ id: 'pr-portal', title: 'Геопортал агентства', due_on: '2026-11-26' })],
    pace: PACE,
  }),
  program({
    id: 'pr-catalogue',
    title: 'Национальный каталог космических снимков 2025–2026',
    started_on: '2025-02-04',
    due_on: '2026-11-11',
    original_due_on: '2026-11-11',
    days_left: 45,
    readiness: 55,
    lag_days: 245,
    pace: {
      ...PACE,
      verdict: 'behind',
      closed: 10,
      closed_tasks: 10,
      remaining: 10,
      forecast_on: '2026-12-26',
      gap_days: 45,
    },
  }),
  program({
    id: 'pr-mission',
    title: 'Спутниковая миссия «Навоий-2»',
    type: { code: 'satellite_mission', name: 'Спутниковая миссия' },
    started_on: '2026-02-19',
    due_on: '2028-05-09',
    original_due_on: '2028-05-09',
    days_left: 590,
    readiness: 28,
    lag_days: -7,
    milestones: [AGREEMENT, CONTRACT],
    subprojects: [
      sub({ id: 'pr-calibration', title: 'Пилот: калибровка снимков', milestones: [FIELD] }),
      sub({
        id: 'pr-insurance',
        title: 'Страхование запуска и работы на орбите',
        step: 'silent',
        deviation: 20,
      }),
    ],
    pace: {
      ...PACE,
      verdict: 'little_data',
      closed: 5,
      closed_tasks: 4,
      remaining: 13,
      forecast_on: null,
      gap_days: null,
    },
  }),
  program({
    id: 'pr-strategy',
    title: 'Стратегия развития космической деятельности до 2035 года',
    started_on: '2025-01-15',
    due_on: '2035-12-31',
    original_due_on: '2035-12-31',
    days_left: 3382,
    pace: {
      ...PACE,
      verdict: 'little_data',
      closed: 3,
      closed_tasks: 3,
      remaining: 8,
      forecast_on: null,
      gap_days: null,
    },
  }),
  program({
    id: 'pr-digital',
    title: 'Цифровизация агентства 2023–2025',
    status: 'done',
    started_on: '2023-12-31',
    due_on: '2025-12-19',
    original_due_on: '2025-12-19',
    days_left: -282,
    readiness: 100,
    lag_days: 0,
  }),
];

function yearEnd(items: ProgramCard[]): YearEndRow[] {
  const [infrastructure, , mission] = ITEMS;
  const rows: YearEndRow[] = [
    {
      milestone: SITE,
      program: { id: infrastructure!.id, code: infrastructure!.code, title: infrastructure!.title },
      subproject: null,
      responsible: infrastructure!.responsible,
    },
    {
      milestone: AGREEMENT,
      program: { id: mission!.id, code: mission!.code, title: mission!.title },
      subproject: null,
      responsible: mission!.responsible,
    },
    {
      milestone: FIELD,
      program: { id: mission!.id, code: mission!.code, title: mission!.title },
      subproject: { id: 'pr-calibration', title: 'Пилот: калибровка снимков' },
      responsible: { id: 'p-karimov', name: 'Каримов А.' },
    },
  ];
  // Как у сервера: строки только тех программ, что есть в ответе.
  const shown = new Set(items.map((item) => item.id));
  return rows.filter((row) => shown.has(row.program.id));
}

export function view(items: ProgramCard[] = ITEMS): ProgramsView {
  return {
    as_of: AS_OF,
    horizon: { from: 2026, to: 2030 },
    items,
    year_end: yearEnd(items),
    is_demo: true,
  };
}

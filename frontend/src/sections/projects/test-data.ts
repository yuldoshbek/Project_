/**
 * Ответы API раздела для тестов экрана — одна фабрика на все тесты раздела.
 *
 * Две копии фабрики расходятся при первом новом поле договора, и падает только одна из
 * них — та, которую не поправили. Числа здесь не считаются: их считает сервер, а экран
 * только показывает (инвариант 2); тест проверяет, что экран делает с ответом.
 */

import type { ProjectCard, ProjectDetail, ProjectsView } from './model';

export function card(overrides: Partial<ProjectCard> & Pick<ProjectCard, 'id'>): ProjectCard {
  return {
    code: `PRJ-2026-${overrides.id.slice(-3).padStart(3, '0')}`,
    title: `Проект ${overrides.id}`,
    type: { code: 'regulation', name: 'Нормативный акт' },
    status: 'in_progress',
    status_reason: null,
    parent: null,
    is_multiyear: false,
    subprojects: 0,
    started_on: '2026-07-01',
    due_on: '2026-11-04',
    original_due_on: '2026-11-04',
    moves: 0,
    responsible: { id: 'p-yusupova', name: 'Юсупова Д.' },
    readiness: 50,
    lag_days: 0,
    step: null,
    deviation: 0,
    impediment: null,
    lead_outside: false,
    center_role: null,
    next_milestone: null,
    milestones: { passed: 1, total: 2 },
    tasks: { done: 1, total: 2 },
    marks: [],
    version: 1,
    ...overrides,
  };
}

export function detail(base: ProjectCard, overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    ...base,
    description: null,
    direction: null,
    region: null,
    organizations: [],
    milestone_list: [
      {
        id: `${base.id}-m1`,
        title: 'Согласование с министерствами',
        due_on: '2026-10-05',
        original_due_on: '2026-10-05',
        is_passed: false,
        passed_on: null,
        step: null,
        deviation: 0,
        version: 3,
      },
    ],
    subproject_list: [],
    task_list: [],
    question: null,
    last_decision: null,
    ...overrides,
  };
}

export const ITEMS: ProjectCard[] = [
  card({
    id: 'pr-geodata',
    title: 'Постановление о порядке обмена геоданными',
    step: 'awaiting_decision',
    deviation: 2,
    version: 4,
    impediment: {
      text: 'Ждём заключение Минюста',
      updated_on: '2026-09-22',
      stale: false,
    },
  }),
  card({ id: 'pr-drought', title: 'Цикл мониторинга: засуха-2026', center_role: 'executor' }),
  card({
    id: 'pr-snow',
    title: 'Цикл мониторинга: снежный покров',
    status: 'on_hold',
    status_reason: 'Сезон съёмки начинается в ноябре',
  }),
  card({ id: 'pr-glossary', title: 'Терминологический стандарт ДЗЗ', status: 'done' }),
  card({
    id: 'pr-mission',
    title: 'Спутниковая миссия «Навоий-2»',
    is_multiyear: true,
    due_on: '2028-05-01',
    original_due_on: '2028-05-01',
  }),
];

export function view(items: ProjectCard[] = ITEMS): ProjectsView {
  return {
    as_of: '2026-09-25T07:00:00Z',
    items,
    types: [
      {
        code: 'regulation',
        name: 'Нормативный акт',
        template: [
          { title: 'Разработка проекта акта', offset_days: 30 },
          { title: 'Внесение в Кабинет Министров', offset_days: 90 },
        ],
      },
      { code: 'standard', name: 'Стандарт', template: [] },
    ],
    people: [
      { id: 'p-karimov', name: 'Каримов А.' },
      { id: 'p-yusupova', name: 'Юсупова Д.' },
    ],
    is_demo: true,
  };
}

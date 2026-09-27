/**
 * Ответы API раздела для тестов экрана — одна фабрика на все тесты раздела.
 *
 * Числа здесь не считаются: группы, ступени и «кто перегружен» считает сервер
 * (`backend/tests/test_tasks.py`), тест экрана проверяет, что экран делает с ответом.
 */

import type { ChecklistItem, TaskCard, TaskDetail, TaskStatus, TasksView } from './model';

/** Граф статусов — для подмены сервера; настоящий живёт в `backend/app/domain/tasks.py`. */
export const TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  new: ['in_progress', 'cancelled'],
  in_progress: ['new', 'in_review', 'done', 'cancelled'],
  in_review: ['in_progress', 'done', 'cancelled'],
  done: ['in_progress'],
  cancelled: ['new', 'in_progress'],
};

export const PEOPLE = [
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
];

const person = (id: string) => PEOPLE.find((each) => each.id === id)!;

export function task(overrides: Partial<TaskCard> & Pick<TaskCard, 'id' | 'title'>): TaskCard {
  return {
    code: `TSK-2026-${overrides.id.replace(/\D/g, '').padStart(4, '0')}`,
    type: null,
    status: 'in_progress',
    assignee: null,
    due_on: null,
    original_due_on: null,
    moves: 0,
    horizon: 'none',
    step: null,
    deviation: 0,
    project: null,
    ijro: null,
    checklist: { done: 0, total: 0 },
    completed_on: null,
    version: 1,
    ...overrides,
  };
}

export const ITEMS: TaskCard[] = [
  task({
    id: 't-1',
    title: 'Аналитическая справка по засухе для Кабинета министров',
    type: { code: 'analytical_note', name: 'Аналитическая информация' },
    assignee: person('p-rakhimov'),
    due_on: '2026-09-24',
    original_due_on: '2026-09-24',
    horizon: 'overdue',
    step: 'overdue',
    deviation: 3,
    project: { id: 'pr-drought', code: 'PRJ-2026-003', title: 'Цикл мониторинга: засуха-2026' },
  }),
  task({
    id: 't-2',
    title: 'Позвонить в Минфин по смете миссии на следующий год',
    status: 'new',
    assignee: person('p-karimov'),
    due_on: '2026-09-27',
    original_due_on: '2026-09-27',
    horizon: 'today',
    step: 'burning',
  }),
  task({
    id: 't-3',
    title: 'Выезд на полигон в Джизаке',
    type: { code: 'site_visit', name: 'Выезд на место' },
    assignee: person('p-karimov'),
    due_on: '2026-10-01',
    original_due_on: '2026-10-01',
    horizon: 'week',
    step: 'burning',
    deviation: 4,
    project: { id: 'pr-calibration', code: 'PRJ-2026-012', title: 'Пилот: калибровка снимков' },
    checklist: { done: 1, total: 3 },
    version: 5,
  }),
  task({
    id: 't-4',
    title: 'Договор с исполнителем аэрофотосъёмки',
    assignee: person('p-tursunov'),
    due_on: '2026-10-15',
    original_due_on: '2026-10-15',
    horizon: 'later',
  }),
  task({ id: 't-5', title: 'Тезисы к совещанию по космическому мониторингу', status: 'new' }),
  task({
    id: 't-6',
    title: 'Разработка ТЗ спутниковой группировки',
    status: 'done',
    assignee: person('p-karimov'),
    horizon: 'closed',
    completed_on: '2026-09-26',
  }),
];

export const CHECKLISTS: Record<string, ChecklistItem[]> = {
  't-3': [
    { id: 'c-1', text: 'Транспорт', is_done: true, version: 2 },
    { id: 'c-2', text: 'Приборы калибровки', is_done: false, version: 1 },
    { id: 'c-3', text: 'Письмо в хокимият', is_done: false, version: 1 },
  ],
};

export function detailOf(card: TaskCard, items: ChecklistItem[] = []): TaskDetail {
  return {
    ...card,
    checklist: { done: items.filter((item) => item.is_done).length, total: items.length },
    description: null,
    checklist_items: items,
    created_on: '2026-09-12',
    question: null,
    transitions: TRANSITIONS[card.status],
  };
}

export function view(items: TaskCard[] = ITEMS): TasksView {
  return {
    as_of: '2026-09-27T07:00:00Z',
    items,
    types: [
      { code: 'analytical_note', name: 'Аналитическая информация' },
      { code: 'site_visit', name: 'Выезд на место' },
      { code: 'other', name: 'Прочее' },
    ],
    people: PEOPLE,
    projects: [
      { id: 'pr-drought', code: 'PRJ-2026-003', title: 'Цикл мониторинга: засуха-2026' },
      { id: 'pr-calibration', code: 'PRJ-2026-012', title: 'Пилот: калибровка снимков' },
    ],
    load: [
      { person: person('p-rakhimov'), overdue: 1, burning: 0, open: 1 },
      { person: person('p-karimov'), overdue: 0, burning: 2, open: 2 },
      { person: person('p-tursunov'), overdue: 0, burning: 0, open: 1 },
    ],
    is_demo: true,
  };
}

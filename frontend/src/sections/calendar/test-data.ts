/**
 * Ответы API раздела «Календарь» для тестов экрана — на 28.09.2026, понедельник.
 *
 * Числа, горячие дни и ступени считает сервер и проверяет `backend/tests/test_calendar.py`.
 * Здесь — готовые ответы той же формы: даты того дня, что утверждали на экране, и
 * «сервер» циклов, который помнит запись и отмену. Даты циклов разворачивает маленькая
 * копия правила `domain/cycles` — только чтобы форма видела даты до записи.
 */

import type {
  CalendarItem,
  CalendarView,
  CycleDetail,
  CyclePreview,
  CycleRuleFields,
  CycleSummary,
  HotDay,
  NewCycle,
  Ref,
} from './model';

export const TODAY = '2026-09-28';
const HORIZON = '2027-09-28';

export const PEOPLE: Ref[] = [
  { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
];

const PROJECTS = {
  portal: { id: 'pr-portal', title: 'Геопортал агентства' },
  floods: { id: 'pr-floods', title: 'Цикл мониторинга: паводки' },
  crops: { id: 'pr-crops', title: 'Пилот: мониторинг посевов' },
  interns: { id: 'pr-interns', title: 'Кадры: стажировки в Центре мониторинга' },
  catalogue: { id: 'pr-catalogue', title: 'Национальный каталог космических снимков 2025–2026' },
  drought: { id: 'pr-drought', title: 'Цикл мониторинга: засуха-2026' },
  station: { id: 'pr-station', title: 'Приём наземной станции по соглашению о сотрудничестве' },
};

function person(id: string): Ref {
  return PEOPLE.find((each) => each.id === id)!;
}

type Kind = 'milestone' | 'task' | 'decision';

function item(
  id: string,
  kind: Kind,
  date: string,
  title: string,
  owner: keyof typeof PROJECTS | null,
  extra: Partial<CalendarItem> = {},
): CalendarItem {
  const project = owner ? PROJECTS[owner] : null;
  return {
    id,
    kind,
    date,
    title,
    decision_kind: kind === 'decision' ? 'hurry' : null,
    owner: project,
    // Как у API: веха открывает свой проект, решение — задачу, по которой оно принято.
    target:
      kind === 'milestone'
        ? { kind: 'project', id: project!.id }
        : kind === 'task'
          ? { kind: 'task', id }
          : { kind: 'task', id: 't-jizzakh' },
    responsible: person('p-rakhimov'),
    step: null,
    deviation: 0,
    is_done: false,
    ends_project: false,
    cycle: null,
    ...extra,
  };
}

const burning = (deviation: number) => ({ step: 'burning' as const, deviation });
const overdue = (deviation: number) => ({ step: 'overdue' as const, deviation });

/** Срок прошёл, не закрыто — пять записей, как на Пульте вымышленной базы. */
const LATE: CalendarItem[] = [
  item(
    'm-accept',
    'milestone',
    '2026-09-19',
    'Приёмка опытного образца платформы',
    'portal',
    overdue(9),
  ),
  item(
    'm-site',
    'milestone',
    '2026-09-20',
    'Площадка станции приёма в Самарканде',
    'station',
    overdue(8),
  ),
  item(
    't-note',
    'task',
    '2026-09-25',
    'Аналитическая справка по засухе для Кабинета министров',
    'drought',
    overdue(3),
  ),
  item(
    'd-hurry',
    'decision',
    '2026-09-27',
    'Поторопить: выезд на полигон в Джизаке',
    null,
    overdue(1),
  ),
  item('t-pf155', 'task', '2026-09-27', 'Сведения по поручению ПФ-155 §5.1', null, overdue(1)),
];

const ITEMS: CalendarItem[] = [
  ...LATE,
  item('m-tz', 'milestone', '2026-09-23', 'Разработка ТЗ', 'portal', { is_done: true }),
  item('m-images', 'milestone', TODAY, 'Получение космических снимков', 'floods', burning(0)),
  item('t-crops', 'task', TODAY, 'Отбор участников пилота с Минсельхозом', 'crops', burning(0)),
  item(
    't-minfin',
    'task',
    TODAY,
    'Позвонить в Минфин по смете миссии на следующий год',
    null,
    burning(0),
  ),
  item('t-tz', 'task', TODAY, 'Разработка ТЗ спутниковой группировки', null, { is_done: true }),
  item(
    't-reservoirs',
    'task',
    '2026-09-29',
    'Сведения для Администрации Президента по мониторингу водохранилищ',
    null,
    burning(1),
  ),
  item('m-results', 'milestone', '2026-10-04', 'Итоги и отчёт', 'interns', {
    ...burning(6),
    ends_project: true,
  }),
  item(
    't-cabinet',
    'task',
    '2026-10-04',
    'Внесение проекта постановления в Кабинет министров',
    null,
    {
      step: 'awaiting_decision',
      deviation: 2,
    },
  ),
  item('m-archive', 'milestone', '2026-10-08', 'Архив снимков перенесён', 'catalogue'),
  item('m-cabinet', 'milestone', '2026-10-08', 'Внесение в Кабинет Министров', 'drought'),
  item('m-talks', 'milestone', '2026-10-08', 'Переговоры и проект документа', 'station'),
  item('m-industry', 'milestone', '2026-10-08', 'Соглашение с отраслью', 'crops'),
  item('m-search', 'milestone', '2026-10-13', 'Поиск и предпросмотр снимков', 'catalogue'),
  item('m-geoportal', 'milestone', '2026-10-18', 'Интеграция с геопорталом', 'catalogue'),
  item('m-analysis', 'milestone', '2026-10-18', 'Обработка и анализ данных', 'floods'),
  item('m-pilot', 'milestone', '2026-10-18', 'Опытная эксплуатация', 'portal'),
  item('m-report', 'milestone', '2026-10-18', 'Отчёт по результатам мониторинга', 'drought', {
    ends_project: true,
  }),
  item('t-spec', 'task', '2026-10-18', 'ТЗ на модуль каталога снимков', 'portal'),
  item('m-launch', 'milestone', '2026-11-12', 'Ввод каталога в эксплуатацию', 'catalogue', {
    ends_project: true,
  }),
];

/** Горячие дни окна — то, что утвердили: сегодня, через 10 и через 20 дней. */
const HOT_AHEAD: HotDay[] = [
  { date: TODAY, count: 3, kinds: { milestone: 1, task: 2 } },
  { date: '2026-10-08', count: 4, kinds: { milestone: 4 } },
  { date: '2026-10-18', count: 5, kinds: { milestone: 4, task: 1 } },
];

const HOT: HotDay[] = [
  ...HOT_AHEAD,
  { date: '2026-11-12', count: 3, kinds: { milestone: 2, task: 1 } },
];

// --------------------------------------------------------------------------------------
// Годовые циклы: копия правила `domain/cycles` — только чтобы форма видела даты до записи
// --------------------------------------------------------------------------------------

function plusMonths(day: string, months: number): string {
  const [year, month, date] = day.split('-').map(Number) as [number, number, number];
  const total = month - 1 + months;
  const nextYear = year + Math.floor(total / 12);
  const nextMonth = (total % 12) + 1;
  const last = new Date(Date.UTC(nextYear, nextMonth, 0)).getUTCDate();
  return `${nextYear}-${String(nextMonth).padStart(2, '0')}-${String(Math.min(date, last)).padStart(2, '0')}`;
}

function datesBetween(rule: CycleRuleFields, since: string, until: string): string[] {
  const months = rule.rule === 'quarterly' ? [1, 4, 7, 10] : [rule.month];
  const found: string[] = [];
  for (let year = Number(since.slice(0, 4)); year <= Number(until.slice(0, 4)); year += 1) {
    const counts =
      rule.rule !== 'every_n_years' ||
      (year >= rule.anchor_year && (year - rule.anchor_year) % rule.every_years === 0);
    if (!counts) continue;
    for (const month of months) {
      if (rule.day > new Date(Date.UTC(year, month, 0)).getUTCDate()) continue;
      const day = `${year}-${String(month).padStart(2, '0')}-${String(rule.day).padStart(2, '0')}`;
      if (day >= since && day <= until) found.push(day);
    }
  }
  return found.sort();
}

function nextDate(rule: CycleRuleFields): string | null {
  const year = Number(TODAY.slice(0, 4));
  const start = rule.rule === 'every_n_years' ? Math.max(year, rule.anchor_year) : year;
  return datesBetween(rule, TODAY, `${start + 4 * rule.every_years + 1}-12-31`)[0] ?? null;
}

export function preview(rule: CycleRuleFields): CyclePreview {
  return { dates: datesBetween(rule, TODAY, plusMonths(TODAY, 12)), next_date: nextDate(rule) };
}

interface StoredCycle extends CycleSummary {
  version: number;
  active: boolean;
}

function cycle(
  id: string,
  title: string,
  rule: CycleRuleFields,
  who: string,
  owner: keyof typeof PROJECTS | null = null,
): StoredCycle {
  return {
    id,
    title,
    ...rule,
    owner: owner ? PROJECTS[owner] : null,
    responsible: person(who),
    next_date: nextDate(rule),
    version: 1,
    active: true,
  };
}

function quarterly(day: number): CycleRuleFields {
  return { rule: 'quarterly', month: 1, day, every_years: 1, anchor_year: 2026 };
}

export function initialCycles(): StoredCycle[] {
  return [
    cycle(
      'cy-cabinet',
      'Сведения в Кабмин по программе космического мониторинга',
      quarterly(5),
      'p-rakhimov',
    ),
    cycle('cy-images', 'Сводка о снимках, выданных ведомствам', quarterly(12), 'p-tursunov'),
    cycle(
      'cy-decree',
      'Годовой отчёт об исполнении Указа ПФ-155',
      { rule: 'annual', month: 1, day: 20, every_years: 1, anchor_year: 2026 },
      'p-yusupova',
    ),
    cycle(
      'cy-operators',
      'Переаттестация операторов станции приёма',
      { rule: 'every_n_years', month: 11, day: 15, every_years: 2, anchor_year: 2025 },
      'p-rakhimov',
      'station',
    ),
  ];
}

function rule(each: CycleRuleFields): CycleRuleFields {
  return {
    rule: each.rule,
    month: each.month,
    day: each.day,
    every_years: each.every_years,
    anchor_year: each.anchor_year,
  };
}

export function summary(each: StoredCycle): CycleSummary {
  return {
    id: each.id,
    title: each.title,
    ...rule(each),
    owner: each.owner,
    responsible: each.responsible,
    next_date: each.next_date,
  };
}

export function detail(each: StoredCycle): CycleDetail {
  return {
    ...summary(each),
    dates: datesBetween(rule(each), TODAY, plusMonths(TODAY, 12)),
    version: each.version,
  };
}

export function created(input: NewCycle, id: string): StoredCycle {
  const project = Object.values(PROJECTS).find((each) => each.id === input.project_id) ?? null;
  return {
    id,
    title: input.title,
    ...rule(input),
    owner: project,
    responsible: input.responsible_id ? person(input.responsible_id) : null,
    next_date: nextDate(input),
    version: 1,
    active: true,
  };
}

/** Ответ `GET /api/v1/calendar` на окно дней — из готовых дат и действующих циклов. */
export function view(
  range: { from: string; to: string },
  cycles: StoredCycle[],
  asOf = '2026-09-28T07:00:00Z',
): CalendarView {
  const until = range.to < HORIZON ? range.to : HORIZON;
  const cycleItems: CalendarItem[] = cycles
    .filter((each) => each.active)
    .flatMap((each) =>
      datesBetween(rule(each), range.from, until).map((date) => ({
        id: `${each.id}:${date}`,
        kind: 'cycle' as const,
        date,
        title: each.title,
        decision_kind: null,
        owner: each.owner,
        target: { kind: 'cycle' as const, id: each.id },
        responsible: each.responsible,
        step: null,
        deviation: 0,
        is_done: false,
        ends_project: false,
        cycle: rule(each),
      })),
    );
  const items = [...ITEMS, ...cycleItems]
    .filter((each) => each.date >= range.from && each.date <= range.to)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const first = range.from > TODAY ? range.from : TODAY;
  return {
    as_of: asOf,
    range,
    items,
    overdue: LATE,
    hot_days: HOT.filter((day) => day.date >= first && day.date <= range.to),
    hot_ahead: HOT_AHEAD,
    hot_window_days: 28,
    hot_threshold: 3,
    horizon_to: HORIZON,
    people: PEOPLE,
    projects: Object.values(PROJECTS),
    is_demo: true,
  };
}

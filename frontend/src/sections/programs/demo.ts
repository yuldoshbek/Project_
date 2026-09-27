/**
 * Вымышленный сервер раздела «Программы» — пока экран не утверждён и API нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит, потом API под
 * утверждённый экран (CLAUDE.md, цикл блока). Люди, типы и часть проектов — те же, что в
 * «Проектах» и «Задачах» (`backend/app/demo.py`), программы и их вехи выдуманы.
 *
 * Правила счёта повторяют домен сервера, чтобы экран утверждали на правильных числах:
 * ступени — `domain/attention`, готовность и отставание — `domain/projects.readiness` и
 * `schedule_lag`. «Успеваем?» — правило из `model.ts` (`Pace`), порог — справочник
 * `min_closed_for_pace`. После утверждения файл удаляется, считать начинает сервер.
 */

import { LADDER, type Step } from '@/sections/pult/model';
import type { ProjectStatus } from '@/sections/projects/model';
import { AGENCY_TIMEZONE } from '@/shared/time';

import {
  TERMINAL,
  type Pace,
  type ProgramCard,
  type ProgramMilestone,
  type ProgramsView,
  type Ref,
  type Subproject,
  type YearEndRow,
} from './model';

const DAY_MS = 86_400_000;
const BURN_DAYS = 7;
const QUIET_DAYS = 14;
const HORIZON_YEARS = 5;
const PACE_WINDOW_DAYS = 90;
const MIN_CLOSED_TASKS = 10;

function todayInTashkent(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(now);
}

function shift(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

const PEOPLE: Record<string, Ref> = {
  abdullaeva: { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
  karimov: { id: 'p-karimov', name: 'Каримов А.' },
  rakhimov: { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  tursunov: { id: 'p-tursunov', name: 'Турсунов Б.' },
  yusupova: { id: 'p-yusupova', name: 'Юсупова Д.' },
};

const TYPES = {
  satellite_mission: 'Спутниковая миссия',
  international: 'Международное сотрудничество',
  higher_authority_order: 'Заказ вышестоящего органа',
  platform: 'Платформа или ИТ',
  staff_education: 'Кадры и образование',
  industry_pilot: 'Пилот с отраслью',
  service_order: 'Заказ услуги',
} as const;

interface MarkSpec {
  title: string;
  due: string;
  original?: string;
  passed?: string;
  /** Открытый вопрос руководителю по вехе — сколько дней ждёт. */
  question?: number;
}

interface WorkSpec {
  key: string;
  code: string;
  title: string;
  type: keyof typeof TYPES;
  who: keyof typeof PEOPLE | null;
  status?: ProjectStatus;
  start: string;
  due: string;
  original?: string;
  /** Дней без движения — признак жизни (ТЗ 4). */
  life: number;
  marks: MarkSpec[];
  /** Закрыто и всего задач. */
  tasks: [number, number];
}

interface ProgramSpec extends WorkSpec {
  subprojects: WorkSpec[];
  /**
   * Сколько задач программы и подпроектов закрыто за окно `PACE_WINDOW_DAYS`. Вехи за окно
   * и остаток считаются по тому же набору, что готовность (`scopeOf`).
   */
  paceTasks?: number;
}

/**
 * Даты — от сегодняшнего дня: ближние сроки днями (`day`), дальние — числом в году
 * (`on`, год от текущего). Так «горит через три дня» остаётся правдой в любой день показа,
 * а вехи по годам не съезжают в соседний год.
 */
function specs(today: string): ProgramSpec[] {
  const year = Number(today.slice(0, 4));
  const day = (days: number) => shift(today, days);
  const on = (years: number, month: number, date: number) =>
    `${year + years}-${String(month).padStart(2, '0')}-${String(date).padStart(2, '0')}`;

  return [
    {
      key: 'mission',
      code: 'PRJ-2026-001',
      title: 'Спутниковая миссия «Навоий-2»',
      type: 'satellite_mission',
      who: 'karimov',
      start: day(-220),
      due: on(2, 5, 10),
      life: 1,
      tasks: [12, 80],
      marks: [
        { title: 'Разработка ТЗ', due: day(-5), passed: day(-5) },
        { title: 'Согласование ТЗ на спутниковую группировку', due: day(3) },
        { title: `Финансирование миссии на ${year + 1} год в бюджете`, due: on(0, 12, 1) },
        { title: 'Договор с изготовителем', due: on(1, 1, 25), original: on(0, 12, 15) },
        { title: 'Эскизный проект спутника', due: on(1, 6, 30) },
        { title: 'Наземный комплекс управления', due: on(1, 11, 30) },
        { title: 'Запуск', due: on(2, 2, 9) },
        { title: 'Ввод в эксплуатацию', due: on(2, 5, 10) },
      ],
      subprojects: [
        {
          key: 'calibration',
          code: 'PRJ-2026-012',
          title: 'Пилот: калибровка снимков',
          type: 'industry_pilot',
          who: 'karimov',
          start: day(-20),
          due: day(130),
          life: 5,
          tasks: [0, 2],
          marks: [
            { title: 'Полевые измерения на полигоне', due: day(23) },
            { title: 'Отчёт о калибровке', due: day(125) },
          ],
        },
        {
          key: 'insurance',
          code: 'PRJ-2026-023',
          title: 'Страхование запуска и работы на орбите',
          type: 'service_order',
          who: 'tursunov',
          start: day(-40),
          due: on(2, 1, 20),
          life: 20,
          tasks: [1, 3],
          marks: [
            { title: 'Запрос предложений страховщиков', due: on(1, 3, 1) },
            { title: 'Договор страхования', due: on(2, 1, 20) },
          ],
        },
      ],
      // Не успевает: темп 11 за 90 дней при 83 оставшихся — прогноз на три месяца позже.
      paceTasks: 10,
    },
    {
      key: 'iac',
      code: 'PRJ-2026-022',
      title: 'IAC-2028: Международный астронавтический конгресс в Ташкенте',
      type: 'international',
      who: 'yusupova',
      start: on(-1, 11, 3),
      due: on(2, 10, 6),
      life: 2,
      tasks: [9, 16],
      marks: [
        { title: 'Концепция конгресса утверждена', due: on(0, 3, 16), passed: on(0, 3, 16) },
        {
          title: 'Оргкомитет сформирован',
          due: on(0, 6, 1),
          original: on(0, 5, 4),
          passed: on(0, 6, 1),
        },
        { title: `Презентация Ташкента на IAC-${year}`, due: day(8) },
        {
          title: `Смета конгресса на ${year + 1} год внесена в Кабмин`,
          due: on(0, 11, 16),
          original: on(0, 11, 2),
          question: 4,
        },
        { title: 'Договор с площадкой', due: on(1, 3, 1) },
        { title: 'Приём докладов открыт', due: on(1, 9, 1) },
        { title: `Передача флага на IAC-${year + 1}`, due: on(1, 10, 1) },
        { title: 'Программа конгресса утверждена', due: on(2, 5, 3) },
        { title: 'Конгресс', due: on(2, 10, 2) },
      ],
      subprojects: [
        {
          key: 'venue',
          code: 'PRJ-2026-024',
          title: 'IAC-2028: площадка и логистика',
          type: 'service_order',
          who: 'tursunov',
          start: on(0, 7, 1),
          due: on(2, 9, 15),
          life: 3,
          tasks: [2, 5],
          marks: [
            { title: 'Три варианта площадки', due: day(33) },
            { title: 'Транспортная схема', due: on(1, 12, 15) },
          ],
        },
        {
          key: 'science',
          code: 'PRJ-2026-025',
          title: 'IAC-2028: научная программа',
          type: 'international',
          who: 'rakhimov',
          start: on(0, 8, 3),
          due: on(2, 8, 1),
          life: 6,
          tasks: [1, 4],
          marks: [
            { title: 'Технические комитеты сформированы', due: on(1, 2, 1) },
            { title: 'Отбор докладов', due: on(2, 4, 28) },
          ],
        },
        {
          key: 'volunteers',
          code: 'PRJ-2026-026',
          title: 'IAC-2028: волонтёры и кадры',
          type: 'staff_education',
          who: 'abdullaeva',
          start: on(0, 9, 1),
          due: on(2, 9, 29),
          life: 9,
          tasks: [0, 2],
          marks: [{ title: 'Набор волонтёров объявлен', due: on(1, 9, 1) }],
        },
      ],
      paceTasks: 12,
    },
    {
      key: 'infrastructure',
      code: 'PRJ-2026-027',
      title: 'Наземная инфраструктура ДЗЗ 2026–2030',
      type: 'platform',
      who: 'tursunov',
      start: on(0, 1, 12),
      due: on(4, 12, 15),
      original: on(4, 6, 30),
      life: 16,
      tasks: [6, 22],
      marks: [
        {
          title: 'Технико-экономическое обоснование',
          due: on(0, 4, 30),
          passed: on(0, 5, 12),
        },
        { title: 'Площадка станции приёма в Самарканде', due: on(0, 8, 31) },
        { title: 'Проект центра обработки данных', due: on(0, 12, 10) },
        { title: 'Монтаж станции приёма', due: on(1, 6, 30), original: on(1, 3, 31) },
        { title: 'Каталог снимков в геопортале', due: on(1, 10, 29) },
        { title: 'Центр обработки данных: первая очередь', due: on(2, 9, 29) },
        { title: 'Станция приёма в Нукусе', due: on(3, 8, 31) },
        { title: 'Приёмка программы', due: on(4, 12, 15) },
      ],
      subprojects: [
        {
          key: 'portal',
          code: 'PRJ-2026-004',
          title: 'Геопортал агентства',
          type: 'platform',
          who: 'tursunov',
          start: on(0, 3, 2),
          due: on(1, 3, 31),
          life: 4,
          tasks: [4, 9],
          marks: [
            { title: 'Публичная версия геопортала', due: on(0, 12, 25) },
            { title: 'Раздел открытых данных', due: on(1, 3, 31) },
          ],
        },
        {
          key: 'station',
          code: 'PRJ-2026-008',
          title: 'Приём наземной станции по соглашению о сотрудничестве',
          type: 'international',
          who: 'karimov',
          start: on(0, 5, 15),
          due: on(1, 4, 30),
          life: 7,
          tasks: [2, 4],
          marks: [
            {
              title: 'Таможенное оформление оборудования',
              due: on(0, 8, 20),
              passed: on(0, 8, 25),
            },
            { title: 'Акт приёма станции', due: on(1, 4, 30) },
          ],
        },
      ],
      paceTasks: 11,
    },
    {
      key: 'staff',
      code: 'PRJ-2026-028',
      title: 'Подготовка кадров космической отрасли 2026–2030',
      type: 'staff_education',
      who: 'abdullaeva',
      start: on(0, 2, 2),
      due: on(4, 6, 28),
      life: 3,
      tasks: [7, 12],
      marks: [
        {
          title: 'Первая группа магистрантов зачислена',
          due: on(0, 9, 1),
          passed: on(0, 9, 1),
        },
        { title: 'Выпуск первого потока стажёров', due: on(1, 6, 30) },
        { title: 'Первый выпуск магистратуры', due: on(2, 6, 30) },
        { title: 'Обмен с зарубежным вузом', due: on(3, 9, 3) },
        { title: 'Итоговый отчёт программы', due: on(4, 6, 28) },
      ],
      subprojects: [
        {
          key: 'interns',
          code: 'PRJ-2026-007',
          title: 'Кадры: стажировки в Центре мониторинга',
          type: 'staff_education',
          who: 'abdullaeva',
          start: on(0, 4, 1),
          due: on(1, 6, 30),
          life: 2,
          tasks: [3, 6],
          marks: [
            { title: 'Первый поток стажёров', due: on(0, 11, 30) },
            { title: 'Отчёт о стажировках', due: on(1, 6, 30) },
          ],
        },
        {
          key: 'lab',
          code: 'PRJ-2026-018',
          title: 'Учебная лаборатория ДЗЗ в вузе',
          type: 'staff_education',
          who: 'rakhimov',
          start: on(0, 6, 1),
          due: on(1, 9, 1),
          life: 4,
          tasks: [1, 3],
          marks: [{ title: 'Оборудование лаборатории поставлено', due: day(5) }],
        },
      ],
      paceTasks: 10,
    },
    {
      key: 'strategy',
      code: 'PRJ-2025-004',
      title: 'Стратегия развития космической деятельности до 2035 года',
      type: 'higher_authority_order',
      who: 'rakhimov',
      start: on(-1, 1, 15),
      due: on(9, 12, 31),
      life: 10,
      tasks: [3, 8],
      marks: [
        {
          title: `Отчёт об исполнении за ${year - 1} год`,
          due: on(0, 2, 16),
          passed: on(0, 2, 20),
        },
        { title: `Дорожная карта на ${year + 1}–${year + 2} годы внесена`, due: on(0, 12, 21) },
        { title: `Отчёт об исполнении за ${year} год`, due: on(1, 2, 15) },
        { title: `Отчёт об исполнении за ${year + 1} год`, due: on(2, 2, 15) },
        { title: `Отчёт об исполнении за ${year + 2} год`, due: on(3, 2, 15) },
        { title: `Отчёт об исполнении за ${year + 3} год`, due: on(4, 2, 15) },
        { title: 'Промежуточная оценка стратегии', due: on(4, 6, 30), original: on(4, 3, 31) },
        { title: 'Итоговый отчёт по стратегии', due: on(9, 12, 1) },
      ],
      subprojects: [],
      // Мало данных: закрытых задач за 90 дней меньше порога.
      paceTasks: 3,
    },
    {
      key: 'digital',
      code: 'PRJ-2023-002',
      title: 'Цифровизация агентства 2023–2025',
      type: 'platform',
      who: 'yusupova',
      status: 'done',
      start: on(-3, 3, 1),
      due: on(-1, 12, 19),
      life: 280,
      tasks: [10, 10],
      marks: [
        {
          title: 'Электронный документооборот',
          due: on(-2, 6, 30),
          passed: on(-2, 6, 30),
        },
        { title: 'Итоговый отчёт', due: on(-1, 12, 19), passed: on(-1, 12, 19) },
      ],
      subprojects: [],
    },
  ];
}

function milestoneOf(key: string, index: number, spec: MarkSpec, today: string): ProgramMilestone {
  const daysLeft = daysBetween(today, spec.due);
  let step: Step | null = null;
  let deviation = 0;
  if (!spec.passed) {
    // Порядок — порядок лестницы: вопрос руководителю важнее сорванного срока.
    if (spec.question !== undefined) {
      step = 'awaiting_decision';
      deviation = spec.question;
    } else if (daysLeft < 0) {
      step = 'overdue';
      deviation = -daysLeft;
    } else if (daysLeft <= BURN_DAYS) {
      step = 'burning';
      deviation = daysLeft;
    }
  }
  return {
    id: `ms-${key}-${index}`,
    title: spec.title,
    due_on: spec.due,
    original_due_on: spec.original ?? spec.due,
    is_passed: spec.passed !== undefined,
    passed_on: spec.passed ?? null,
    days_left: daysLeft,
    step,
    deviation,
  };
}

/** Ступень работы целиком — те же правила, что у строки проекта на Пульте. */
function workStep(spec: WorkSpec, today: string): { step: Step | null; deviation: number } {
  if (TERMINAL.has(spec.status ?? 'in_progress')) return { step: null, deviation: 0 };
  const daysLeft = daysBetween(today, spec.due);
  if (daysLeft < 0) return { step: 'overdue', deviation: -daysLeft };
  if (daysLeft <= BURN_DAYS) return { step: 'burning', deviation: daysLeft };
  if (spec.life > QUIET_DAYS) return { step: 'silent', deviation: spec.life };
  return { step: null, deviation: 0 };
}

/**
 * Вехи и задачи, по которым считаются готовность, отставание и «успеваем?». У программы —
 * она сама вместе с подпроектами (допущение V13): раздел отвечает, где мы по программе
 * целиком, и три числа одной карточки обязаны считаться по одному набору — иначе «готово
 * 44 %» и «осталось 27» спорят друг с другом.
 */
function scopeOf(works: WorkSpec[]): { closed: number; total: number } {
  return works.reduce(
    (sum, work) => ({
      closed: sum.closed + work.marks.filter((mark) => mark.passed).length + work.tasks[0],
      total: sum.total + work.marks.length + work.tasks[1],
    }),
    { closed: 0, total: 0 },
  );
}

function readinessOf(status: ProjectStatus | undefined, works: WorkSpec[]): number {
  if (status === 'done') return 100;
  const { closed, total } = scopeOf(works);
  return total === 0 ? 0 : Math.round((closed * 100) / total);
}

function lagOf(spec: WorkSpec, readiness: number, today: string): number {
  if (TERMINAL.has(spec.status ?? 'in_progress')) return 0;
  const span = daysBetween(spec.start, spec.due);
  if (span <= 0) return 0;
  const elapsed = Math.max(0, daysBetween(spec.start, today) / span);
  return Math.round((elapsed - readiness / 100) * span);
}

function paceOf(spec: ProgramSpec, today: string): Pace | null {
  const tasks = spec.paceTasks;
  if (tasks === undefined || TERMINAL.has(spec.status ?? 'in_progress')) return null;
  const works = [spec, ...spec.subprojects];
  const since = shift(today, -PACE_WINDOW_DAYS);
  const recent = works
    .flatMap((work) => work.marks)
    .filter((mark) => mark.passed !== undefined && mark.passed > since && mark.passed <= today);
  const closed = tasks + recent.length;
  const scope = scopeOf(works);
  const remaining = scope.total - scope.closed;
  const base = {
    window_days: PACE_WINDOW_DAYS,
    closed,
    closed_tasks: tasks,
    min_closed_tasks: MIN_CLOSED_TASKS,
    remaining,
  };
  if (tasks < MIN_CLOSED_TASKS) {
    return { ...base, verdict: 'little_data', forecast_on: null, gap_days: null };
  }
  const forecast = shift(today, Math.ceil((remaining * PACE_WINDOW_DAYS) / closed));
  const gap = daysBetween(spec.due, forecast);
  return {
    ...base,
    verdict: gap > 0 ? 'behind' : 'on_track',
    forecast_on: forecast,
    gap_days: gap,
  };
}

/** Вехи — по сроку, как обещает договор: «далее» на плитке — первая непройденная. */
function milestonesOf(spec: WorkSpec, today: string): ProgramMilestone[] {
  return spec.marks
    .map((mark, index) => milestoneOf(spec.key, index, mark, today))
    .sort((left, right) => left.due_on.localeCompare(right.due_on));
}

function subprojectOf(spec: WorkSpec, today: string): Subproject {
  const readiness = readinessOf(spec.status, [spec]);
  return {
    id: `pr-${spec.key}`,
    code: spec.code,
    title: spec.title,
    status: spec.status ?? 'in_progress',
    responsible: spec.who ? PEOPLE[spec.who]! : null,
    started_on: spec.start,
    due_on: spec.due,
    original_due_on: spec.original ?? spec.due,
    readiness,
    ...workStep(spec, today),
    milestones: milestonesOf(spec, today),
  };
}

function programOf(spec: ProgramSpec, today: string): ProgramCard {
  const readiness = readinessOf(spec.status, [spec, ...spec.subprojects]);
  return {
    id: `pr-${spec.key}`,
    code: spec.code,
    title: spec.title,
    type: { code: spec.type, name: TYPES[spec.type] },
    status: spec.status ?? 'in_progress',
    responsible: spec.who ? PEOPLE[spec.who]! : null,
    started_on: spec.start,
    due_on: spec.due,
    original_due_on: spec.original ?? spec.due,
    days_left: daysBetween(today, spec.due),
    readiness,
    lag_days: lagOf(spec, readiness, today),
    ...workStep(spec, today),
    milestones: milestonesOf(spec, today),
    subprojects: spec.subprojects.map((sub) => subprojectOf(sub, today)),
    pace: paceOf(spec, today),
  };
}

/** Порядок раздела: лестница внимания, затем по дате программы; закрытые в конце. */
function rank(card: ProgramCard): number {
  if (TERMINAL.has(card.status)) return LADDER.length + 1;
  return card.step ? LADDER.indexOf(card.step) : LADDER.length;
}

function yearEnd(items: ProgramCard[], today: string): YearEndRow[] {
  const last = `${today.slice(0, 4)}-12-31`;
  const rows: YearEndRow[] = [];
  for (const program of items) {
    if (TERMINAL.has(program.status)) continue;
    const ref = { id: program.id, code: program.code, title: program.title };
    const add = (
      milestones: ProgramMilestone[],
      subproject: YearEndRow['subproject'],
      responsible: Ref | null,
    ) => {
      for (const milestone of milestones) {
        if (!milestone.is_passed && milestone.due_on <= last) {
          rows.push({ milestone, program: ref, subproject, responsible });
        }
      }
    };
    add(program.milestones, null, program.responsible);
    for (const sub of program.subprojects) {
      if (!TERMINAL.has(sub.status)) {
        add(sub.milestones, { id: sub.id, title: sub.title }, sub.responsible);
      }
    }
  }
  return rows.sort((left, right) => left.milestone.due_on.localeCompare(right.milestone.due_on));
}

export class DemoPrograms {
  constructor(private readonly now: () => Date = () => new Date()) {}

  view(): ProgramsView {
    const moment = this.now();
    const today = todayInTashkent(moment);
    const year = Number(today.slice(0, 4));
    const items = specs(today)
      .map((spec) => programOf(spec, today))
      .sort((left, right) => rank(left) - rank(right) || left.due_on.localeCompare(right.due_on));
    return {
      as_of: moment.toISOString(),
      horizon: { from: year, to: year + HORIZON_YEARS - 1 },
      items,
      year_end: yearEnd(items, today),
      is_demo: true,
    };
  }
}

export const demoPrograms = new DemoPrograms();

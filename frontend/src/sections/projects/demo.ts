/**
 * Вымышленный сервер раздела «Проекты» — пока экран не утверждён и API нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит, потом API под
 * утверждённый экран (CLAUDE.md, цикл блока). Здесь те же люди и проекты, что на
 * вымышленном Пульте, а вехи — из шаблонов типов (`backend/app/seed.py`): так проект на
 * экране выглядит ровно так, как будет выглядеть заведённый настоящий.
 *
 * Правила счёта повторяют домен сервера, чтобы экран утверждали на правильных числах:
 * готовность — `domain/projects.readiness`, отставание — `schedule_lag`, ступени —
 * `domain/attention`. После утверждения этот файл удаляется, считать начинает сервер.
 */

import { AGENCY_TIMEZONE } from '@/shared/time';

import type { Step } from '@/sections/pult/model';

import type {
  MilestoneRow,
  NewProject,
  OrganizationRole,
  ProjectCard,
  ProjectDetail,
  ProjectStatus,
  ProjectType,
  ProjectsView,
  Ref,
  WhatIfChange,
  WhatIfResult,
  WhatIfState,
} from './model';

const DAY_MS = 86_400_000;
const BURN_DAYS = 7;
const QUIET_DAYS = 14;
const IMPEDIMENT_STALE_DAYS = 14;

function todayInTashkent(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(now);
}

function shift(day: string, days: number): string {
  return new Date(new Date(`${day}T00:00:00Z`).getTime() + days * DAY_MS)
    .toISOString()
    .slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  return Math.round(
    (new Date(`${to}T00:00:00Z`).getTime() - new Date(`${from}T00:00:00Z`).getTime()) / DAY_MS,
  );
}

export const TYPES: ProjectType[] = [
  {
    code: 'monitoring_cycle',
    name: 'Цикл мониторинга',
    template: [
      { title: 'Получение космических снимков', offset_days: 30 },
      { title: 'Обработка и анализ данных', offset_days: 60 },
      { title: 'Отчёт по результатам мониторинга', offset_days: 90 },
    ],
  },
  {
    code: 'regulation',
    name: 'Нормативный акт',
    template: [
      { title: 'Разработка проекта акта', offset_days: 30 },
      { title: 'Согласование с министерствами и ведомствами', offset_days: 60 },
      { title: 'Внесение в Кабинет Министров', offset_days: 90 },
      { title: 'Принятие', offset_days: 120 },
    ],
  },
  {
    code: 'standard',
    name: 'Стандарт',
    template: [
      { title: 'Разработка проекта стандарта', offset_days: 60 },
      { title: 'Обсуждение и согласование', offset_days: 120 },
      { title: 'Утверждение и регистрация', offset_days: 180 },
    ],
  },
  {
    code: 'platform',
    name: 'Платформа или ИТ',
    template: [
      { title: 'Техническое задание', offset_days: 30 },
      { title: 'Разработка', offset_days: 120 },
      { title: 'Опытная эксплуатация', offset_days: 150 },
      { title: 'Ввод в эксплуатацию', offset_days: 180 },
    ],
  },
  {
    code: 'satellite_mission',
    name: 'Спутниковая миссия',
    template: [
      { title: 'Концепция и техническое задание', offset_days: 90 },
      { title: 'Договор с изготовителем', offset_days: 180 },
      { title: 'Запуск', offset_days: 720 },
      { title: 'Ввод в эксплуатацию', offset_days: 810 },
    ],
  },
  {
    code: 'industry_pilot',
    name: 'Пилот с отраслью',
    template: [
      { title: 'Соглашение с отраслью', offset_days: 30 },
      { title: 'Проведение пилота', offset_days: 120 },
      { title: 'Отчёт и предложения по масштабированию', offset_days: 150 },
    ],
  },
  {
    code: 'service_order',
    name: 'Заказ услуги',
    template: [
      { title: 'Заявка и техническое задание', offset_days: 14 },
      { title: 'Договор', offset_days: 30 },
      { title: 'Оказание услуги', offset_days: 75 },
      { title: 'Акт приёмки', offset_days: 90 },
    ],
  },
  {
    code: 'international',
    name: 'Международное сотрудничество',
    template: [
      { title: 'Переговоры и проект документа', offset_days: 60 },
      { title: 'Внутригосударственное согласование', offset_days: 120 },
      { title: 'Подписание', offset_days: 150 },
    ],
  },
  {
    code: 'staff_education',
    name: 'Кадры и образование',
    template: [
      { title: 'Программа и отбор участников', offset_days: 30 },
      { title: 'Обучение', offset_days: 120 },
      { title: 'Итоги и отчёт', offset_days: 150 },
    ],
  },
  {
    code: 'higher_authority_order',
    name: 'Заказ вышестоящего органа',
    template: [
      { title: 'План исполнения', offset_days: 7 },
      { title: 'Исполнение', offset_days: 45 },
      { title: 'Доклад об исполнении', offset_days: 60 },
    ],
  },
];

const PEOPLE: Ref[] = [
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
];

const PARTNER = { id: 'o-ecology', name: 'Министерство экологии' };
const CENTER = { id: 'o-center', name: 'Центр космического мониторинга' };

interface Milestone {
  id: string;
  title: string;
  due: number;
  original: number;
  passedAgo: number | null;
}

interface Project {
  id: string;
  code: string;
  title: string;
  type: string;
  status: ProjectStatus;
  reason: string | null;
  parent: string | null;
  multiyear: boolean;
  start: number;
  due: number;
  original: number;
  moves: number;
  who: string | null;
  impediment: { text: string; ago: number } | null;
  lifeAgo: number;
  lead: 'outside' | null;
  center: OrganizationRole | null;
  question: { text: string; ago: number } | null;
  milestones: Milestone[];
  tasks: { done: number; total: number; titles: string[] };
  direction: string | null;
  region: string | null;
}

interface Spec {
  key: string;
  type: string;
  title: string;
  who: string;
  start: number;
  due: number;
  original?: number;
  moves?: number;
  status?: ProjectStatus;
  reason?: string;
  parent?: string;
  multiyear?: boolean;
  impediment?: { text: string; ago: number };
  lifeAgo?: number;
  lead?: 'outside';
  center?: OrganizationRole;
  question?: { text: string; ago: number };
  milestones?: { title: string; due: number; original?: number; passedAgo?: number | null }[];
  tasks?: { done: number; total: number; titles?: string[] };
  direction?: string;
  region?: string;
}

const SPECS: Spec[] = [
  {
    key: 'mission',
    type: 'satellite_mission',
    title: 'Спутниковая миссия «Навоий-2»',
    who: 'p-karimov',
    start: -220,
    due: 590,
    multiyear: true,
    lifeAgo: 1,
    center: 'co_executor',
    direction: 'Космический мониторинг',
    milestones: [
      { title: 'Разработка ТЗ', due: -5, passedAgo: 0 },
      { title: 'Согласование ТЗ на спутниковую группировку', due: 3 },
      { title: 'Договор с изготовителем', due: 120 },
      { title: 'Запуск', due: 500 },
    ],
    tasks: { done: 3, total: 6, titles: ['План работ по группировке на квартал'] },
  },
  {
    key: 'geodata',
    type: 'regulation',
    title: 'Постановление о порядке обмена геоданными',
    who: 'p-yusupova',
    start: -80,
    due: 40,
    lifeAgo: 5,
    question: {
      text: 'Вносить проект постановления в Кабинет министров в текущей редакции?',
      ago: 2,
    },
    impediment: { text: 'Ждём заключение Минюста по разделу о персональных данных', ago: 3 },
    direction: 'Нормативная база',
    tasks: { done: 2, total: 4, titles: ['Согласование проекта постановления с Минэкологии'] },
  },
  {
    key: 'drought',
    type: 'monitoring_cycle',
    title: 'Цикл мониторинга: засуха-2026',
    who: 'p-rakhimov',
    start: -70,
    due: 20,
    lifeAgo: 10,
    center: 'executor',
    region: 'Джизакская область',
    tasks: {
      done: 1,
      total: 3,
      titles: ['Аналитическая справка по засухе для Кабинета министров'],
    },
  },
  {
    key: 'portal',
    type: 'platform',
    title: 'Геопортал агентства',
    who: 'p-tursunov',
    start: -150,
    due: 60,
    original: 30,
    moves: 1,
    lifeAgo: 8,
    impediment: { text: 'Поставщик не передал исходный код модуля карт', ago: 21 },
    milestones: [
      { title: 'Техническое задание', due: -120, passedAgo: 118 },
      { title: 'Приёмка опытного образца платформы', due: -9, original: -23 },
      { title: 'Опытная эксплуатация', due: 20 },
      { title: 'Ввод в эксплуатацию', due: 60 },
    ],
    tasks: { done: 4, total: 7, titles: ['Выгрузка данных в субплатформу'] },
  },
  {
    key: 'crops',
    type: 'industry_pilot',
    title: 'Пилот: мониторинг посевов',
    who: 'p-abdullaeva',
    start: -40,
    due: 110,
    lifeAgo: 7,
    center: 'co_executor',
    tasks: { done: 1, total: 3, titles: ['Отбор участников пилота с Минсельхозом'] },
  },
  {
    key: 'standard',
    type: 'standard',
    title: 'Стандарт на снимки ДЗЗ',
    who: 'p-yusupova',
    start: -118,
    due: 62,
    lifeAgo: 4,
    milestones: [
      { title: 'Разработка проекта стандарта', due: -58, passedAgo: 55 },
      { title: 'Внесение стандарта в агентство «Узстандарт»', due: 2 },
      { title: 'Утверждение и регистрация', due: 62 },
    ],
    tasks: { done: 2, total: 3 },
  },
  {
    key: 'interns',
    type: 'staff_education',
    title: 'Кадры: стажировки в Центре мониторинга',
    who: 'p-abdullaeva',
    start: -144,
    due: 6,
    lifeAgo: 6,
    center: 'executor',
    tasks: { done: 5, total: 6 },
  },
  {
    key: 'station',
    type: 'international',
    title: 'Приём наземной станции по соглашению о сотрудничестве',
    who: 'p-rakhimov',
    start: -75,
    due: 75,
    original: 61,
    moves: 1,
    lifeAgo: 0,
    lead: 'outside',
    tasks: { done: 0, total: 2 },
  },
  {
    key: 'air',
    type: 'international',
    title: 'Совместная программа наблюдения за качеством воздуха',
    who: 'p-yusupova',
    start: -50,
    due: 100,
    lifeAgo: 25,
    lead: 'outside',
    impediment: { text: 'Министерство экологии не прислало свой проект соглашения', ago: 25 },
    tasks: { done: 0, total: 1 },
  },
  {
    key: 'aerial',
    type: 'service_order',
    title: 'Заказ услуги: аэрофотосъёмка Ферганской долины',
    who: 'p-tursunov',
    start: -21,
    due: 69,
    lifeAgo: 21,
    region: 'Ферганская область',
    tasks: { done: 0, total: 2 },
  },
  {
    key: 'floods',
    type: 'monitoring_cycle',
    title: 'Цикл мониторинга: паводки',
    who: 'p-rakhimov',
    start: -30,
    due: 60,
    lifeAgo: 2,
    center: 'executor',
    tasks: { done: 1, total: 3, titles: ['Запрос сведений у хокимиятов о паводках'] },
  },
  {
    key: 'calibration',
    type: 'industry_pilot',
    title: 'Пилот: калибровка снимков',
    who: 'p-karimov',
    start: -20,
    due: 130,
    parent: 'mission',
    lifeAgo: 5,
    tasks: { done: 0, total: 2, titles: ['Выезд на полигон в Джизаке'] },
  },
  {
    key: 'forest',
    type: 'monitoring_cycle',
    title: 'Цикл мониторинга: лесные пожары',
    who: 'p-tursunov',
    start: -4,
    due: 86,
    lifeAgo: 4,
    center: 'co_executor',
    tasks: { done: 0, total: 2 },
  },
  {
    key: 'atlas',
    type: 'platform',
    title: 'Цифровой атлас земель',
    who: 'p-tursunov',
    start: -40,
    due: 140,
    lifeAgo: 3,
    center: 'executor',
    tasks: { done: 2, total: 5 },
  },
  {
    key: 'uav',
    type: 'service_order',
    title: 'Заказ услуги: съёмка с БПЛА Каракалпакстана',
    who: 'p-karimov',
    start: -6,
    due: 84,
    lifeAgo: 6,
    center: 'executor',
    region: 'Республика Каракалпакстан',
    tasks: { done: 0, total: 1 },
  },
  {
    key: 'cadastre',
    type: 'industry_pilot',
    title: 'Пилот с кадастром: границы участков',
    who: 'p-abdullaeva',
    start: -9,
    due: 141,
    lifeAgo: 9,
    tasks: { done: 0, total: 2 },
  },
  {
    key: 'snow',
    type: 'monitoring_cycle',
    title: 'Цикл мониторинга: снежный покров',
    who: 'p-rakhimov',
    start: -40,
    due: 50,
    status: 'on_hold',
    reason: 'Сезон съёмки начинается в ноябре — возобновить 1 ноября',
    lifeAgo: 12,
  },
  {
    key: 'lab',
    type: 'staff_education',
    title: 'Учебная лаборатория ДЗЗ в вузе',
    who: 'p-abdullaeva',
    start: -60,
    due: 90,
    status: 'on_hold',
    reason: 'Ждём решения вуза о помещении',
    lifeAgo: 30,
  },
  {
    key: 'glossary',
    type: 'standard',
    title: 'Терминологический стандарт ДЗЗ',
    who: 'p-yusupova',
    start: -200,
    due: -10,
    status: 'done',
    lifeAgo: 10,
  },
  {
    key: 'hydro',
    type: 'higher_authority_order',
    title: 'Поручение по мониторингу водохранилищ',
    who: 'p-karimov',
    start: -70,
    due: -8,
    status: 'done',
    lifeAgo: 8,
  },
  {
    key: 'legacy',
    type: 'platform',
    title: 'Прежний портал спутниковых данных',
    who: 'p-tursunov',
    start: -300,
    due: -40,
    status: 'cancelled',
    reason: 'Заменён геопорталом агентства',
    lifeAgo: 40,
  },
];

function milestonesFor(spec: Spec, type: ProjectType, id: string): Milestone[] {
  if (spec.milestones) {
    return spec.milestones.map((mark, index) => ({
      id: `${id}-m${index + 1}`,
      title: mark.title,
      due: mark.due,
      original: mark.original ?? mark.due,
      passedAgo: mark.passedAgo ?? null,
    }));
  }
  const done = spec.status === 'done';
  return type.template.map((step, index) => {
    const due = spec.start + step.offset_days;
    return {
      id: `${id}-m${index + 1}`,
      title: step.title,
      due,
      original: due,
      // Пройдено то, чей срок давно позади; у завершённого проекта — всё.
      passedAgo: done || due < -3 ? Math.max(-due - 2, 0) : null,
    };
  });
}

function buildProject(spec: Spec, number: number, year: number): Project {
  const type = TYPES.find((each) => each.code === spec.type)!;
  const id = `pr-${spec.key}`;
  const done = spec.status === 'done';
  return {
    id,
    code: `PRJ-${year}-${String(number).padStart(3, '0')}`,
    title: spec.title,
    type: spec.type,
    status: spec.status ?? 'in_progress',
    reason: spec.reason ?? null,
    parent: spec.parent ? `pr-${spec.parent}` : null,
    multiyear: spec.multiyear ?? false,
    start: spec.start,
    due: spec.due,
    original: spec.original ?? spec.due,
    moves: spec.moves ?? 0,
    who: spec.who,
    impediment: spec.impediment ?? null,
    lifeAgo: spec.lifeAgo ?? 3,
    lead: spec.lead ?? null,
    center: spec.center ?? null,
    question: spec.question ?? null,
    milestones: milestonesFor(spec, type, id),
    tasks: {
      done: done ? (spec.tasks?.total ?? 2) : (spec.tasks?.done ?? 0),
      total: spec.tasks?.total ?? 2,
      titles: spec.tasks?.titles ?? [],
    },
    direction: spec.direction ?? null,
    region: spec.region ?? null,
  };
}

/** Ступень и отклонение — правило `domain/attention.attention_of`. */
function stepOf(project: Pick<Project, 'status' | 'question' | 'due' | 'lifeAgo' | 'lead'>): {
  step: Step | null;
  deviation: number;
} {
  if (project.status === 'done' || project.status === 'cancelled')
    return { step: null, deviation: 0 };
  if (project.question) return { step: 'awaiting_decision', deviation: project.question.ago };
  if (project.due < 0) return { step: 'overdue', deviation: -project.due };
  if (project.due <= BURN_DAYS) return { step: 'burning', deviation: project.due };
  if (project.lifeAgo > QUIET_DAYS) {
    return { step: project.lead ? 'blocked_by_others' : 'silent', deviation: project.lifeAgo };
  }
  return { step: null, deviation: 0 };
}

function milestoneStep(mark: Milestone): { step: Step | null; deviation: number } {
  if (mark.passedAgo !== null) return { step: null, deviation: 0 };
  if (mark.due < 0) return { step: 'overdue', deviation: -mark.due };
  if (mark.due <= BURN_DAYS) return { step: 'burning', deviation: mark.due };
  return { step: null, deviation: 0 };
}

/** Готовность — `domain/projects.readiness`: вехи и задачи в общий счёт. */
function readinessOf(project: Project): number {
  const passed = project.milestones.filter((mark) => mark.passedAgo !== null).length;
  const total = project.milestones.length + project.tasks.total;
  if (total === 0) return 0;
  return Math.round(((passed + project.tasks.done) * 100) / total);
}

/** Отставание от плана — `domain/projects.schedule_lag`. */
function lagOf(project: Project): number {
  const span = project.due - project.start;
  if (span <= 0) return 0;
  const elapsed = Math.max(0, -project.start / span);
  return Math.round((elapsed - readinessOf(project) / 100) * span);
}

function emptyCounts(): Record<Step, number> {
  return { awaiting_decision: 0, overdue: 0, burning: 0, blocked_by_others: 0, silent: 0 };
}

export class DemoProjects {
  private projects: Project[] = [];
  private nextNumber = 0;

  constructor(private readonly clock: () => Date = () => new Date()) {
    this.reset();
  }

  reset(): void {
    const year = Number(todayInTashkent(this.clock()).slice(0, 4));
    this.projects = SPECS.map((spec, index) => buildProject(spec, index + 1, year));
    this.nextNumber = SPECS.length;
  }

  private today(): string {
    return todayInTashkent(this.clock());
  }

  private card(project: Project): ProjectCard {
    const today = this.today();
    const type = TYPES.find((each) => each.code === project.type)!;
    const state = stepOf(project);
    const open = project.milestones
      .filter((mark) => mark.passedAgo === null)
      .sort((left, right) => left.due - right.due);
    const who = PEOPLE.find((person) => person.id === project.who) ?? null;
    const parent = project.parent ? this.projects.find((each) => each.id === project.parent) : null;
    const terminal = project.status === 'done' || project.status === 'cancelled';
    return {
      id: project.id,
      code: project.code,
      title: project.title,
      type: { code: type.code, name: type.name },
      status: project.status,
      status_reason: project.reason,
      parent: parent ? { id: parent.id, title: parent.title } : null,
      is_multiyear: project.multiyear,
      subprojects: this.projects.filter((each) => each.parent === project.id).length,
      started_on: shift(today, project.start),
      due_on: shift(today, project.due),
      original_due_on: shift(today, project.original),
      moves: project.moves,
      responsible: who,
      readiness: terminal && project.status === 'done' ? 100 : readinessOf(project),
      lag_days: terminal ? 0 : lagOf(project),
      step: state.step,
      deviation: state.deviation,
      impediment: project.impediment
        ? {
            text: project.impediment.text,
            updated_on: shift(today, -project.impediment.ago),
            stale: project.impediment.ago > IMPEDIMENT_STALE_DAYS,
          }
        : null,
      lead_outside: project.lead === 'outside',
      center_role: project.center,
      next_milestone: open[0] ? { title: open[0].title, due_on: shift(today, open[0].due) } : null,
      milestones: {
        passed: project.milestones.filter((mark) => mark.passedAgo !== null).length,
        total: project.milestones.length,
      },
      marks: project.milestones.map((mark) => ({
        title: mark.title,
        due_on: shift(today, mark.due),
        is_passed: mark.passedAgo !== null,
      })),
      tasks: { done: project.tasks.done, total: project.tasks.total },
    };
  }

  view(): ProjectsView {
    return {
      as_of: this.clock().toISOString(),
      items: this.ordered().map((project) => this.card(project)),
      types: TYPES,
      people: PEOPLE,
      is_demo: true,
    };
  }

  /**
   * Порядок: сначала то, что требует внимания, в порядке лестницы, затем идущее по плану,
   * в конце завершённое и отменённое; внутри группы — по сроку.
   */
  private ordered(): Project[] {
    const rank = (project: Project): number => {
      const { step } = stepOf(project);
      const ladder: (Step | null)[] = [
        'awaiting_decision',
        'overdue',
        'burning',
        'blocked_by_others',
        'silent',
      ];
      if (project.status === 'done' || project.status === 'cancelled') return ladder.length + 1;
      return step ? ladder.indexOf(step) : ladder.length;
    };
    return [...this.projects].sort(
      (left, right) => rank(left) - rank(right) || left.due - right.due,
    );
  }

  detail(id: string): ProjectDetail {
    const project = this.find(id);
    const today = this.today();
    const card = this.card(project);
    const organizations: ProjectDetail['organizations'] = [];
    if (project.center) organizations.push({ ...CENTER, role: project.center, is_center: true });
    if (project.lead) organizations.push({ ...PARTNER, role: 'lead_agency', is_center: false });
    return {
      ...card,
      description: null,
      direction: project.direction,
      region: project.region,
      organizations,
      milestone_list: project.milestones.map((mark): MilestoneRow => ({
        id: mark.id,
        title: mark.title,
        due_on: shift(today, mark.due),
        original_due_on: shift(today, mark.original),
        is_passed: mark.passedAgo !== null,
        passed_on: mark.passedAgo !== null ? shift(today, -mark.passedAgo) : null,
        ...milestoneStep(mark),
      })),
      subproject_list: this.projects
        .filter((each) => each.parent === project.id)
        .map((each) => this.card(each)),
      task_list: project.tasks.titles.map((title, index) => ({
        id: `${project.id}-t${index + 1}`,
        title,
        status: 'in_progress' as const,
        due_on: null,
        assignee: card.responsible,
        step: null,
      })),
      question: project.question
        ? { text: project.question.text, asked_on: shift(today, -project.question.ago) }
        : null,
      last_decision: null,
    };
  }

  create(input: NewProject): ProjectDetail {
    const type = TYPES.find((each) => each.code === input.type_code);
    if (!type) throw new Error('неизвестный тип проекта');
    const today = this.today();
    const start = daysBetween(today, input.started_on);
    const last = Math.max(...type.template.map((step) => step.offset_days));
    const due = input.due_on ? daysBetween(today, input.due_on) : start + last;
    this.nextNumber += 1;
    const year = Number(today.slice(0, 4));
    const id = `pr-new-${this.nextNumber}`;
    const project: Project = {
      id,
      code: `PRJ-${year}-${String(this.nextNumber).padStart(3, '0')}`,
      title: input.title.trim(),
      type: type.code,
      status: 'in_progress',
      reason: null,
      parent: input.parent_id,
      multiyear: input.is_multiyear,
      start,
      due,
      original: due,
      moves: 0,
      who: input.responsible_id,
      impediment: null,
      lifeAgo: 0,
      lead: null,
      center: null,
      question: null,
      milestones: type.template.map((step, index) => ({
        id: `${id}-m${index + 1}`,
        title: step.title,
        due: start + step.offset_days,
        original: start + step.offset_days,
        passedAgo: null,
      })),
      tasks: { done: 0, total: 0, titles: [] },
      direction: null,
      region: null,
    };
    this.projects.push(project);
    return this.detail(id);
  }

  setStatus(id: string, status: ProjectStatus, reason: string | null): void {
    const project = this.find(id);
    project.status = status;
    project.reason = status === 'on_hold' || status === 'cancelled' ? reason : null;
    project.lifeAgo = 0;
  }

  setImpediment(id: string, text: string): void {
    const project = this.find(id);
    project.impediment = text.trim() ? { text: text.trim(), ago: 0 } : null;
    project.lifeAgo = 0;
  }

  whatIf(id: string, changes: WhatIfChange[]): WhatIfResult {
    const before = this.find(id);
    const after = this.applied(before, changes);
    const today = this.today();
    const state = (project: Project): WhatIfState => ({
      ...stepOf(project),
      lag_days: lagOf(project),
      due_on: shift(today, project.due),
    });
    return {
      project: { before: state(before), after: state(after) },
      milestones: before.milestones.map((mark, index) => ({
        id: mark.id,
        title: mark.title,
        before: milestoneStep(mark).step,
        after: milestoneStep(after.milestones[index]!).step,
      })),
      pult: {
        before: this.counts(this.projects),
        after: this.counts(this.projects.map((each) => (each.id === id ? after : each))),
      },
    };
  }

  /** «Применить»: сроки записываются, перенос позже считается переносом. */
  apply(id: string, changes: WhatIfChange[]): void {
    const project = this.find(id);
    const next = this.applied(project, changes);
    if (next.due > project.due) next.moves += 1;
    next.lifeAgo = 0;
    this.projects = this.projects.map((each) => (each.id === id ? next : each));
  }

  private applied(project: Project, changes: WhatIfChange[]): Project {
    const today = this.today();
    const copy: Project = {
      ...project,
      milestones: project.milestones.map((mark) => ({ ...mark })),
    };
    for (const change of changes) {
      const offset = daysBetween(today, change.due_on);
      if (change.kind === 'project') copy.due = offset;
      const mark = copy.milestones.find((each) => each.id === change.id);
      if (change.kind === 'milestone' && mark) mark.due = offset;
    }
    return copy;
  }

  /** Счётчики Пульта по проектам и вехам — как `services/metrics.what_if` по снимку. */
  private counts(projects: Project[]): Record<Step, number> {
    const counts = emptyCounts();
    for (const project of projects) {
      if (project.status === 'done' || project.status === 'cancelled') continue;
      const { step } = stepOf(project);
      if (step) counts[step] += 1;
      for (const mark of project.milestones) {
        const own = milestoneStep(mark).step;
        if (own) counts[own] += 1;
      }
    }
    return counts;
  }

  private find(id: string): Project {
    const project = this.projects.find((each) => each.id === id);
    if (!project) throw new Error(`нет проекта ${id}`);
    return project;
  }
}

export const demoProjects = new DemoProjects();

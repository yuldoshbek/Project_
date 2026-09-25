/**
 * Вымышленный Пульт — сервер, которого ещё нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит его на iPhone, потом
 * API под утверждённый экран (CLAUDE.md, «Цикл блока»). Этот модуль и есть такой сервер: он
 * держит набор записей в памяти, сам считает порядок, счётчики и «кто держит», принимает
 * решения и вопросы — ровно то, что потом будет делать `GET /api/v1/pult` и соседние.
 *
 * Люди, проекты и поручения выдуманы. Экран пишет об этом прямо (`is_demo`), иначе
 * вымышленную строку однажды примут за настоящую.
 *
 * Сроки заданы смещением от сегодняшнего дня по Ташкенту: набор не «стареет», и через
 * неделю показ выглядит так же, как в день, когда его утвердили.
 */

import { AGENCY_TIMEZONE } from '@/shared/time';

import {
  LADDER,
  rowKey,
  type Change,
  type DecisionKind,
  type Holder,
  type Person,
  type PultRow,
  type PultView,
  type RowSection,
  type Step,
} from './model';

const DAY_MS = 86_400_000;

/** Сегодня по Ташкенту как `ГГГГ-ММ-ДД` — сроки наступают по календарным дням агентства. */
function todayInTashkent(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(now);
}

function shiftDate(day: string, offset: number): string {
  const moment = new Date(`${day}T00:00:00Z`).getTime() + offset * DAY_MS;
  return new Date(moment).toISOString().slice(0, 10);
}

function hoursAgo(now: Date, hours: number): string {
  return new Date(now.getTime() - hours * 3_600_000).toISOString();
}

const people = {
  karimov: { id: 'p-karimov', name: 'Каримов А.' },
  yusupova: { id: 'p-yusupova', name: 'Юсупова Д.' },
  rakhimov: { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  tursunov: { id: 'p-tursunov', name: 'Турсунов Б.' },
  abdullaeva: { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
} satisfies Record<string, Person>;

/** Запись набора: состояние, из которого сервер выводит строку. */
interface Item {
  section: RowSection;
  id: string;
  title: string;
  context: string | null;
  responsible: Person | null;
  /** Ступень без вопроса к руководителю и отклонение на ней; `null` — по плану. */
  step: Exclude<Step, 'awaiting_decision'> | null;
  deviation: number;
  /** Смещение срока от сегодня, дни. */
  due: number | null;
  /** Смещение исходного срока, если срок переносили. */
  originalDue?: number;
  question?: { text: string; askedDaysAgo: number };
  lastDecision?: { kind: DecisionKind; daysAgo: number };
}

function seedItems(): Item[] {
  return [
    {
      section: 'milestones',
      id: 'm-tz-constellation',
      title: 'Согласование ТЗ на спутниковую группировку',
      context: 'Спутниковая миссия «Навоий-2»',
      responsible: people.karimov,
      step: 'burning',
      deviation: 3,
      due: 3,
      question: {
        text: 'Утвердить перенос вехи на две недели: поставщик задерживает документацию?',
        askedDaysAgo: 6,
      },
    },
    {
      section: 'projects',
      id: 'pr-geodata-act',
      title: 'Постановление о порядке обмена геоданными',
      context: null,
      responsible: people.yusupova,
      step: null,
      deviation: 0,
      due: 40,
      question: {
        text: 'Вносить проект постановления в Кабинет министров в текущей редакции?',
        askedDaysAgo: 2,
      },
    },
    {
      section: 'tasks',
      id: 't-drought-note',
      title: 'Аналитическая справка по засухе для Кабинета министров',
      context: 'Цикл мониторинга: засуха-2026',
      responsible: people.rakhimov,
      step: 'overdue',
      deviation: 3,
      due: -3,
    },
    {
      section: 'milestones',
      id: 'm-platform-acceptance',
      title: 'Приёмка опытного образца платформы',
      context: 'Геопортал агентства',
      responsible: people.tursunov,
      step: 'overdue',
      deviation: 9,
      due: -9,
      originalDue: -23,
      lastDecision: { kind: 'hurry', daysAgo: 4 },
    },
    {
      section: 'decisions',
      id: 'd-jizzakh-visit',
      title: 'Поторопить: выезд на полигон в Джизаке',
      context: 'Пилот: калибровка снимков',
      responsible: people.karimov,
      step: 'overdue',
      deviation: 1,
      due: -1,
    },
    {
      section: 'tasks',
      id: 't-pilot-selection',
      title: 'Отбор участников пилота с Минсельхозом',
      context: 'Пилот: мониторинг посевов',
      responsible: people.abdullaeva,
      step: 'burning',
      deviation: 0,
      due: 0,
    },
    {
      section: 'milestones',
      id: 'm-standard-submit',
      title: 'Внесение стандарта в агентство «Узстандарт»',
      context: 'Стандарт на снимки ДЗЗ',
      responsible: people.yusupova,
      step: 'burning',
      deviation: 2,
      due: 2,
    },
    {
      section: 'tasks',
      id: 't-subplatform-upload',
      title: 'Выгрузка данных в субплатформу',
      context: 'Геопортал агентства',
      responsible: people.tursunov,
      step: 'burning',
      deviation: 5,
      due: 5,
      originalDue: -4,
    },
    {
      section: 'projects',
      id: 'pr-internships',
      title: 'Кадры: стажировки в Центре мониторинга',
      context: null,
      responsible: people.abdullaeva,
      step: 'burning',
      deviation: 6,
      due: 6,
    },
    {
      section: 'projects',
      id: 'pr-ground-station',
      title: 'Приём наземной станции по соглашению о сотрудничестве',
      context: null,
      responsible: people.rakhimov,
      step: 'blocked_by_others',
      deviation: 23,
      due: 75,
      originalDue: 61,
    },
    {
      section: 'tasks',
      id: 't-ecology-approval',
      title: 'Согласование проекта постановления с Минэкологии',
      context: 'Постановление о порядке обмена геоданными',
      responsible: people.yusupova,
      step: 'blocked_by_others',
      deviation: 17,
      due: 20,
    },
    {
      section: 'projects',
      id: 'pr-aerial-fergana',
      title: 'Заказ услуги: аэрофотосъёмка Ферганской долины',
      context: null,
      responsible: people.tursunov,
      step: 'silent',
      deviation: 21,
      due: 90,
    },
    {
      section: 'tasks',
      id: 't-khokimiyat-request',
      title: 'Запрос сведений у хокимиятов о паводках',
      context: 'Цикл мониторинга: паводки',
      responsible: people.rakhimov,
      step: 'silent',
      deviation: 15,
      due: 30,
    },
  ];
}

/** Записей по плану сверх тех, что в наборе: «и ещё N по плану». */
const QUIET_ON_TRACK = 23;

/** Ступень строки: вопрос к руководителю старше любого срока (ТЗ 4). */
function stepOf(item: Item): { step: Step; deviation: number } | null {
  if (item.question) return { step: 'awaiting_decision', deviation: item.question.askedDaysAgo };
  return item.step ? { step: item.step, deviation: item.deviation } : null;
}

/** Порядок лестницы: ступень, затем «что горит сильнее» — как `domain/attention.py`. */
function order(row: PultRow): [number, number] {
  const urgency = row.step === 'burning' ? row.deviation : -row.deviation;
  return [LADDER.indexOf(row.step), urgency];
}

function emptyCounts(): Record<Step, number> {
  return {
    awaiting_decision: 0,
    overdue: 0,
    burning: 0,
    blocked_by_others: 0,
    silent: 0,
  };
}

export class DemoPult {
  private items: Item[] = seedItems();
  private readonly history = new Map<string, Item>();

  constructor(private readonly clock: () => Date = () => new Date()) {}

  /** Вернуть набор к исходному: нужен тестам, чтобы решения одного не видел другой. */
  reset(): void {
    this.items = seedItems();
    this.history.clear();
  }

  view(): PultView {
    const now = this.clock();
    const today = todayInTashkent(now);
    const rows: PultRow[] = [];
    let onTrack = QUIET_ON_TRACK;

    for (const item of this.items) {
      const state = stepOf(item);
      if (!state) {
        onTrack += 1;
        continue;
      }
      rows.push({
        section: item.section,
        entity_id: item.id,
        title: item.title,
        context: item.context,
        step: state.step,
        deviation: state.deviation,
        due_on: item.due === null ? null : shiftDate(today, item.due),
        original_due_on: item.originalDue === undefined ? null : shiftDate(today, item.originalDue),
        responsible: item.responsible,
        question: item.question
          ? {
              id: `q-${item.id}`,
              text: item.question.text,
              asked_on: shiftDate(today, -item.question.askedDaysAgo),
            }
          : null,
        last_decision: item.lastDecision
          ? {
              kind: item.lastDecision.kind,
              decided_on: shiftDate(today, -item.lastDecision.daysAgo),
            }
          : null,
      });
    }

    rows.sort((left, right) => {
      const [a1, a2] = order(left);
      const [b1, b2] = order(right);
      return a1 - b1 || a2 - b2;
    });

    const counts = emptyCounts();
    for (const row of rows) counts[row.step] += 1;

    return {
      as_of: now.toISOString(),
      last_visit_at: hoursAgo(now, 17),
      rows,
      counts,
      on_track: onTrack,
      holders: holdersOf(rows),
      changes: changesSince(now, today),
      deadline_moves: {
        period_days: 30,
        moves: 4,
        total_shift_days: 37,
        items: [
          {
            section: 'milestones',
            entity_id: 'm-platform-acceptance',
            title: 'Приёмка опытного образца платформы',
            original_due_on: shiftDate(today, -23),
            due_on: shiftDate(today, -9),
            moves: 2,
          },
          {
            section: 'projects',
            entity_id: 'pr-ground-station',
            title: 'Приём наземной станции по соглашению о сотрудничестве',
            original_due_on: shiftDate(today, 61),
            due_on: shiftDate(today, 75),
            moves: 1,
          },
          {
            section: 'tasks',
            entity_id: 't-subplatform-upload',
            title: 'Выгрузка данных в субплатформу',
            original_due_on: shiftDate(today, -4),
            due_on: shiftDate(today, 5),
            moves: 1,
          },
        ],
      },
      is_demo: true,
    };
  }

  /** Решение руководителя. Вопрос по объекту закрывается любым решением (V12). */
  decide(key: string, kind: DecisionKind): void {
    const item = this.find(key);
    this.history.set(key, { ...item });
    const answered: Item = { ...item, lastDecision: { kind, daysAgo: 0 } };
    delete answered.question;
    this.replace(key, answered);
  }

  /** Вопрос помощника руководителю — ставит запись на верхнюю ступень. */
  ask(key: string, text: string): void {
    const item = this.find(key);
    this.history.set(key, { ...item });
    this.replace(key, { ...item, question: { text, askedDaysAgo: 0 } });
  }

  /** Отмена последнего действия по записи — то, что даёт кнопка «Отменить». */
  undo(key: string): void {
    const previous = this.history.get(key);
    if (!previous) return;
    this.history.delete(key);
    this.replace(key, previous);
  }

  private find(key: string): Item {
    const item = this.items.find(
      (each) => rowKey({ section: each.section, entity_id: each.id }) === key,
    );
    if (!item) throw new Error(`нет записи ${key}`);
    return item;
  }

  private replace(key: string, next: Item): void {
    this.items = this.items.map((each) =>
      rowKey({ section: each.section, entity_id: each.id }) === key ? next : each,
    );
  }
}

function holdersOf(rows: PultRow[]): Holder[] {
  const byPerson = new Map<string, Holder>();
  for (const row of rows) {
    if (!row.responsible) continue;
    const holder = byPerson.get(row.responsible.id) ?? {
      person: row.responsible,
      counts: emptyCounts(),
      total: 0,
      worst: row.step,
    };
    holder.counts[row.step] += 1;
    holder.total += 1;
    if (LADDER.indexOf(row.step) < LADDER.indexOf(holder.worst)) holder.worst = row.step;
    byPerson.set(row.responsible.id, holder);
  }
  // Сначала тот, у кого хуже всего, затем у кого больше строк: вопрос «кто держит» — это
  // «кому звонить первым».
  return [...byPerson.values()].sort(
    (left, right) =>
      LADDER.indexOf(left.worst) - LADDER.indexOf(right.worst) ||
      right.counts.overdue - left.counts.overdue ||
      right.total - left.total,
  );
}

function changesSince(now: Date, today: string): Change[] {
  return [
    {
      kind: 'decision_done',
      section: 'decisions',
      title: 'Эскалировать: письмо в Минэкологии',
      at: hoursAgo(now, 2),
    },
    {
      kind: 'created',
      section: 'projects',
      title: 'Пилот с Минздравом: мониторинг вспышек',
      at: hoursAgo(now, 4),
    },
    {
      kind: 'milestone_passed',
      section: 'milestones',
      title: 'Разработка ТЗ — Спутниковая миссия «Навоий-2»',
      at: hoursAgo(now, 6),
    },
    {
      kind: 'deadline_moved',
      section: 'milestones',
      title: 'Приёмка опытного образца платформы',
      at: hoursAgo(now, 9),
      moved: { from: shiftDate(today, -16), to: shiftDate(today, -9) },
    },
    {
      kind: 'closed',
      section: 'tasks',
      title: 'Сведения по поручению ПФ-155 для Администрации Президента',
      at: hoursAgo(now, 15),
    },
  ];
}

/** Один сервер на приложение: решения переживают переход между разделами. */
export const demoPult = new DemoPult();

/**
 * Пульт — договор данных экрана.
 *
 * Это форма будущего ответа API (`GET /api/v1/pult`). Экран строится раньше API по
 * правилу блока «экран → API» (CLAUDE.md), и чтобы замена вымышленных данных настоящими
 * была заменой одной функции, экран с первого дня говорит на языке ответа сервера.
 *
 * **Числа считает сервер** (инвариант 2): порядок строк, отклонения, счётчики ступеней,
 * «кто держит», переносы сроков. Экран их только показывает — второй расчёт на клиенте дал
 * бы два разных числа на двух экранах. Отвечает `GET /api/v1/pult`
 * (`backend/app/api/routes/pult.py`) — экран утверждён заказчиком 25.09.2026.
 */

/** Ступень лестницы внимания (ТЗ 4). Порядок объявления — порядок показа. */
export const LADDER = [
  'awaiting_decision',
  'overdue',
  'burning',
  'blocked_by_others',
  'silent',
] as const;

export type Step = (typeof LADDER)[number];

/** Откуда строка. Ижро приходит в блоке 2. */
export type RowSection =
  'projects' | 'milestones' | 'tasks' | 'decisions' | 'ijro' | 'letters' | 'agreements';

/** Вид решения руководителя (ТЗ 3.7). */
export type DecisionKind =
  'approve' | 'return' | 'assign' | 'hurry' | 'escalate' | 'ask_extension' | 'reject';

/** Цвет ступени: четыре сигнала токенов и ни одного больше (tokens.css). */
export const STEP_SIGNAL = {
  awaiting_decision: 'call',
  overdue: 'burn',
  burning: 'burn',
  blocked_by_others: 'wait',
  silent: 'wait',
} as const satisfies Record<Step, 'call' | 'burn' | 'wait'>;

/**
 * Решения, которые предлагает строка: первое — основное, остальные — по «Ещё».
 *
 * Основное — то, что руководитель выбирает чаще всего на этой ступени: по вопросу —
 * утвердить, по сорванному сроку — поторопить, по чужому ведомству — эскалировать. Одно
 * касание должно попадать в самое частое действие, а не открывать выбор.
 */
export const STEP_DECISIONS = {
  awaiting_decision: ['approve', 'return', 'assign', 'ask_extension', 'reject'],
  overdue: ['hurry', 'ask_extension', 'escalate', 'assign'],
  burning: ['hurry', 'assign', 'ask_extension'],
  blocked_by_others: ['escalate', 'hurry', 'ask_extension'],
  silent: ['hurry', 'assign', 'escalate'],
} as const satisfies Record<Step, readonly DecisionKind[]>;

export interface Person {
  id: string;
  name: string;
}

/** По какому объекту принимается решение (ТЗ 3.7). */
export type TargetType =
  'project' | 'milestone' | 'task' | 'ijro_assignment' | 'letter' | 'agreement';

export interface PultRow {
  section: RowSection;
  entity_id: string;
  /** У решения без текста названия нет: подпись — вид решения, её переводит экран. */
  title: string | null;
  /** Вид решения — у строк раздела `decisions`. */
  decision_kind: DecisionKind | null;
  /**
   * Объект, по которому решают из этой строки. У проекта, вехи и задачи — они сами; у
   * строки-решения — объект того решения: «поторопить» относится к работе, а не к
   * решению.
   */
  target_type: TargetType;
  target_id: string;
  /** Чему принадлежит: проект у вехи и задачи. */
  context: string | null;
  step: Step;
  /** Дни рядом со ступенью: ждёт, просрочено, осталось, тишина. Считает сервер. */
  deviation: number;
  due_on: string | null;
  /** Первое значение срока: перенос виден как «исходный → текущий». */
  original_due_on: string | null;
  responsible: Person | null;
  /** Открытый вопрос к руководителю — только у строк «ждёт решения». */
  question: { id: string; text: string; asked_on: string } | null;
  /** Последнее решение руководителя по объекту: чтобы не поторопить дважды, не зная. */
  last_decision: { kind: DecisionKind; decided_on: string } | null;
}

/** «Кто держит»: строки лестницы по ответственным. */
export interface Holder {
  person: Person;
  counts: Record<Step, number>;
  total: number;
  /** Самая тяжёлая ступень у этого человека — ею окрашена строка. */
  worst: Step;
}

/** Изменение с прошлого визита руководителя (ТЗ 4, ТЗ 5). */
export interface Change {
  kind: 'created' | 'closed' | 'deadline_moved' | 'milestone_passed' | 'decision_done';
  section: RowSection;
  entity_id: string;
  /** Удалённая после правки запись названия не имеет: её видно в журнале, но не в базе. */
  title: string | null;
  at: string;
  /** Для переноса срока: было → стало. */
  moved: { from: string; to: string } | null;
}

/** «Держим ли мы свои сроки?» — переносы за период (ТЗ 5). */
export interface DeadlineMoves {
  period_days: number;
  moves: number;
  total_shift_days: number;
  items: {
    section: RowSection;
    entity_id: string;
    title: string | null;
    original_due_on: string;
    due_on: string | null;
    moves: number;
  }[];
}

export interface PultView {
  /** Момент расчёта: свежесть показывается всегда (инвариант 7). */
  as_of: string;
  /** Прошлый визит руководителя — от него считается «с прошлого визита». */
  last_visit_at: string | null;
  rows: PultRow[];
  counts: Record<Step, number>;
  on_track: number;
  holders: Holder[];
  changes: Change[];
  deadline_moves: DeadlineMoves;
  /** Вымышленные данные: экран обязан это сказать, иначе их примут за настоящие. */
  is_demo: boolean;
}

export function rowKey(row: Pick<PultRow, 'section' | 'entity_id'>): string {
  return `${row.section}:${row.entity_id}`;
}

const SECTION_TARGET = {
  projects: 'project',
  milestones: 'milestone',
  tasks: 'task',
} as const satisfies Partial<Record<RowSection, TargetType>>;

/** Объект решения для записи из «Держим ли сроки?»: там только проекты, вехи и задачи. */
export function targetOf(item: {
  section: RowSection;
  entity_id: string;
}): { target_type: TargetType; target_id: string } | null {
  const type = SECTION_TARGET[item.section as keyof typeof SECTION_TARGET];
  return type ? { target_type: type, target_id: item.entity_id } : null;
}

/** Отчёт недели или месяца — вкладка Пульта (`GET /api/v1/pult/report`). */
export type ReportPeriod = 'week' | 'month';

export interface ReportTotals {
  created_projects: number;
  created_tasks: number;
  closed_tasks: number;
  closed_projects: number;
  passed_milestones: number;
  decisions_made: number;
  decisions_done: number;
  moves: number;
  shift_days: number;
}

export interface ReportView {
  period: ReportPeriod;
  start: string;
  end: string;
  /** Момент формирования: лестница и «кто держит» показаны на него, а не на конец периода. */
  generated_at: string;
  totals: ReportTotals;
  counts: Record<Step, number>;
  on_track: number;
  rows: PultRow[];
  /** Сколько строк лестницы не попало в отчёт: лист A4, а не выгрузка. */
  more_rows: number;
  holders: Holder[];
  decisions: {
    kind: DecisionKind;
    title: string | null;
    decided_on: string;
    state: 'open' | 'done';
    done_on: string | null;
  }[];
  deadline_moves: DeadlineMoves;
  is_demo: boolean;
}

/**
 * Строка в тексте уведомления: только то, из чего складываются слова, — название, а у решения
 * без текста вид решения и объект, и дни ожидания.
 */
export interface PushRow {
  title: string | null;
  section: RowSection;
  decision_kind: DecisionKind | null;
  context: string | null;
  deviation: number;
}

/**
 * Что покажет экран блокировки (V29): два числа и два названия. Те же данные сервер кладёт в
 * пуш утренней сводки (ADR-0036).
 */
export interface LockScreen {
  /** Ждут решения: сколько и что ждёт дольше всех; `null` — ничего не ждёт. */
  awaiting: { count: number; oldest: PushRow } | null;
  /** Срок сегодня: сколько и первое по лестнице; `null` — сроков сегодня нет. */
  due: { count: number; first: PushRow } | null;
}

/**
 * Данные пуша: утренняя сводка и вопрос помощника. Текста в них нет — слова складывает service
 * worker (`push.ts`, ADR-0036). `tag` — метка уведомления на устройстве: повторная доставка с
 * той же меткой заменяет прежнее, а не добавляет второе.
 */
export type PushPayload =
  | { kind: 'summary'; tag: string; url: string; lock_screen: LockScreen }
  | {
      kind: 'question';
      tag: string;
      url: string;
      /** Название объекта вопроса; `null` — объекта уже нет, и уведомление — сам вопрос. */
      title: string | null;
      question: string;
    };

/**
 * Утренняя сводка — вкладка Пульта (`GET /api/v1/pult/summary`).
 *
 * В сводке ровно два пункта (ТЗ 8): что ждёт решения и что горит сегодня. Строки — те же
 * строки лестницы, что на Пульте (инвариант 2): решение из сводки принимается тем же
 * касанием. Экран блокировки сервер собирает из этих же списков: одно число не живёт в двух
 * расчётах.
 */
export interface SummaryView {
  /**
   * Момент расчёта (инвариант 7). От него же считаются «сегодня» и «ещё не время»: сервер
   * решил, ушла ли сводка, на этот момент, а не на часы браузера.
   */
  as_of: string;
  /** Во сколько приходит по Ташкенту — порог «Утренняя сводка» (V24), «ЧЧ:ММ». */
  send_at: string;
  /**
   * Последний запуск расписания за утро по Ташкенту, «ЧЧ:ММ»: до него не ушедшая сводка ещё
   * может уйти, после — уже завтра. Сервер берёт его из того же места, что и расписание.
   */
  last_run: string;
  /** Когда сегодняшняя дошла до устройства руководителя; `null` — ещё не ушла. */
  sent_at: string | null;
  /** Ждёт решения руководителя — ступень лестницы, самое давнее первым. */
  awaiting: PultRow[];
  /** Срок сегодня (V26): срок сегодня на любой ступени — и у работы, что ждёт решения. */
  due_today: PultRow[];
  /** Что покажет экран блокировки — то, что уйдёт в пуш. */
  lock_screen: LockScreen;
  /** Устройство руководителя, на котором включены уведомления; `null` — нигде. */
  leader_device: { name: string; since: string } | null;
  /**
   * Открытый ключ сервера для подписки (VAPID, base64url); `null` — уведомления на сервере не
   * настроены: ключ вводит заказчик.
   */
  push_key: string | null;
  /**
   * Вымышленные данные — значит, не рабочий контур. Расписание утренней сводки вызывает только
   * рабочий контур, так что здесь по расписанию она не уходит: приходит лишь пуш о вопросе (V30).
   */
  is_demo: boolean;
}

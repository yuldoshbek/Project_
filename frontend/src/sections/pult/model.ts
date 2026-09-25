/**
 * Пульт — договор данных экрана.
 *
 * Это форма будущего ответа API (`GET /api/v1/pult`). Экран строится раньше API по
 * правилу блока «экран → API» (CLAUDE.md), и чтобы замена вымышленных данных настоящими
 * была заменой одной функции, экран с первого дня говорит на языке ответа сервера.
 *
 * **Числа считает сервер** (инвариант 2): порядок строк, отклонения, счётчики ступеней,
 * «кто держит», переносы сроков. Экран их только показывает — второй расчёт на клиенте дал
 * бы два разных числа на двух экранах. Пока API нет, сервером служит `demo.ts`.
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
export type RowSection = 'projects' | 'milestones' | 'tasks' | 'decisions' | 'ijro';

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

export interface PultRow {
  section: RowSection;
  entity_id: string;
  title: string;
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
  title: string;
  at: string;
  /** Для переноса срока: было → стало. */
  moved?: { from: string; to: string };
}

/** «Держим ли мы свои сроки?» — переносы за период (ТЗ 5). */
export interface DeadlineMoves {
  period_days: number;
  moves: number;
  total_shift_days: number;
  items: {
    section: RowSection;
    entity_id: string;
    title: string;
    original_due_on: string;
    due_on: string;
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

/**
 * Задачи — договор данных раздела.
 *
 * Форма ответа API (`/api/v1/tasks…`, `backend/app/api/routes/tasks.py`). Экран утверждён
 * заказчиком 27.09.2026 на вымышленных данных той же формы, и API написан под него
 * (CLAUDE.md, цикл блока «экран → API»).
 *
 * **Числа и группы считает сервер**: ступень лестницы и отклонение, «к какому сроку»
 * (группа по сроку относительно сегодняшнего дня Ташкента), число переносов, «кто
 * перегружен», разрешённые переходы статуса. Экран их только показывает (инвариант 2).
 */

import type { Step } from '@/sections/pult/model';

/** Статусы задачи (ТЗ 3.2). «Просрочена» — не статус, а ступень (инвариант 1). */
export type TaskStatus = 'new' | 'in_progress' | 'in_review' | 'done' | 'cancelled';

export const TASK_STATUSES: readonly TaskStatus[] = [
  'new',
  'in_progress',
  'in_review',
  'done',
  'cancelled',
];

export const TERMINAL: ReadonlySet<TaskStatus> = new Set(['done', 'cancelled']);

/**
 * «К какому сроку» — группа списка. Считает сервер по сроку и сегодняшнему дню Ташкента:
 * граница «сегодня» на телефоне в поездке не должна сдвигаться вместе с поясом телефона.
 */
export type Horizon = 'overdue' | 'today' | 'tomorrow' | 'week' | 'later' | 'none' | 'closed';

export const HORIZONS: readonly Horizon[] = [
  'overdue',
  'today',
  'tomorrow',
  'week',
  'later',
  'none',
  'closed',
];

export interface Ref {
  id: string;
  name: string;
}

export interface TaskType {
  code: string;
  name: string;
}

export interface ProjectRef {
  id: string;
  code: string;
  title: string;
}

export interface TaskCard {
  id: string;
  code: string;
  title: string;
  type: TaskType | null;
  status: TaskStatus;
  assignee: Ref | null;
  /** Срок — день по Ташкенту; время — конец рабочего дня (18:00). */
  due_on: string | null;
  /** Первый срок; перенос виден как «исходный → текущий». */
  original_due_on: string | null;
  /** Сколько раз срок переносили позже. */
  moves: number;
  horizon: Horizon;
  /** Ступень лестницы внимания; `null` — по плану или закрыта. */
  step: Step | null;
  deviation: number;
  /** Привязки необязательны (ТЗ 3.2): задача без привязки — обычное дело. */
  project: ProjectRef | null;
  ijro: { id: string; label: string } | null;
  checklist: { done: number; total: number };
  completed_on: string | null;
  version: number;
  /** Пометка «просьба руководителя»: задачу завёл Захват из его просьбы (V17). */
  is_request: boolean;
}

export interface ChecklistItem {
  id: string;
  text: string;
  is_done: boolean;
  version: number;
}

export interface TaskDetail extends TaskCard {
  description: string | null;
  checklist_items: ChecklistItem[];
  created_on: string;
  /** Открытый вопрос руководителю — из-за него задача «ждёт решения». */
  question: { text: string; asked_on: string } | null;
  /** Куда можно перейти из текущего статуса — граф на сервере (`domain/tasks`). */
  transitions: TaskStatus[];
}

/** «Кто перегружен?» (ТЗ 5): просрочки по ответственным — считает сервер. */
export interface LoadRow {
  person: Ref;
  overdue: number;
  burning: number;
  open: number;
}

export interface TasksView {
  as_of: string;
  items: TaskCard[];
  types: TaskType[];
  people: Ref[];
  projects: ProjectRef[];
  load: LoadRow[];
  is_demo: boolean;
}

/**
 * Разбор строки (ТЗ 7): «к пятнице рассмотрение проекта постановления Минэкологии,
 * Каримов» → тип, срок, ответственный. Правилами на сервере (`backend/app/domain/capture.py`),
 * без внешних моделей. `matched` — какие куски строки что дали.
 */
export interface ParsedLine {
  title: string;
  type_code: string | null;
  due_on: string | null;
  assignee_id: string | null;
  matched: { type: string | null; due: string | null; assignee: string | null };
}

export interface NewTask {
  title: string;
  type_code: string | null;
  due_on: string | null;
  assignee_id: string | null;
  project_id: string | null;
}

/** Правка задачи в карточке: всё, кроме статуса и чек-листа, у которых свои действия. */
export interface TaskEdit {
  title: string;
  type_code: string | null;
  due_on: string | null;
  assignee_id: string | null;
  project_id: string | null;
  description: string | null;
  version: number;
}

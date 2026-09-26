/**
 * Проекты — договор данных раздела.
 *
 * Форма ответа API (`/api/v1/projects…`, `backend/app/api/routes/projects.py`). Экран
 * утверждён заказчиком 25.09.2026 на вымышленных данных той же формы, и API написан под
 * него (CLAUDE.md, цикл блока «экран → API»).
 *
 * **Числа считает сервер**: готовность, отставание от плана, ступень лестницы и отклонение,
 * число переносов. Экран их только показывает — так же, как Пульт (инвариант 2).
 */

import type { DecisionKind, Step } from '@/sections/pult/model';

export type ProjectStatus = 'in_progress' | 'on_hold' | 'done' | 'cancelled';

/** Колонки доски — статусы проекта (ТЗ 3.1) в порядке жизни проекта. */
export const BOARD_COLUMNS: readonly ProjectStatus[] = [
  'in_progress',
  'on_hold',
  'done',
  'cancelled',
];

/** Пауза и отмена требуют причины: она же потом снимает паузу (ТЗ 3.1). */
export const NEEDS_REASON: ReadonlySet<ProjectStatus> = new Set(['on_hold', 'cancelled']);

export const TERMINAL: ReadonlySet<ProjectStatus> = new Set(['done', 'cancelled']);

/** Роль организации в проекте (ТЗ 3.1). */
export type OrganizationRole = 'customer' | 'executor' | 'co_executor' | 'lead_agency';

export interface Ref {
  id: string;
  name: string;
}

export interface ProjectType {
  code: string;
  name: string;
  /** Шаблон вех: подставляется в новый проект (ТЗ 3.1), дни — от начала проекта. */
  template: { title: string; offset_days: number }[];
}

export interface ProjectCard {
  id: string;
  code: string;
  title: string;
  type: { code: string; name: string };
  status: ProjectStatus;
  status_reason: string | null;
  parent: { id: string; title: string } | null;
  /** Программа: многолетний проект с подпроектами (ТЗ 3.1). */
  is_multiyear: boolean;
  subprojects: number;
  started_on: string;
  due_on: string;
  /** Первое значение срока; перенос виден как «исходный → текущий». */
  original_due_on: string;
  /** Сколько раз срок переносили позже. */
  moves: number;
  responsible: Ref | null;
  /** Готовность, % — по закрытым вехам и задачам (ТЗ 3.1). Считается, а не вводится. */
  readiness: number;
  /** Отставание от плана, дни (ТЗ 4): плюс — отстаём, минус — идём с запасом. */
  lag_days: number;
  /** Ступень лестницы внимания; `null` — по плану или работа закончена. */
  step: Step | null;
  deviation: number;
  /** «Что мешает» — одна строка с датой обновления; устаревшая помечена. */
  impediment: { text: string; updated_on: string; stale: boolean } | null;
  /** Головное ведомство — не агентство и не Центр. */
  lead_outside: boolean;
  /** Роль Центра в проекте — основа среза «что держит Центр» (ТЗ 5). */
  center_role: OrganizationRole | null;
  next_milestone: { title: string; due_on: string } | null;
  milestones: { passed: number; total: number };
  /** Вехи на таймлайне: ромб на дате, закрашенный — пройдена. */
  marks: { title: string; due_on: string; is_passed: boolean }[];
  tasks: { done: number; total: number };
  /** Версия записи: правка по устаревшей получает честный отказ (инвариант 15). */
  version: number;
}

export interface MilestoneRow {
  id: string;
  title: string;
  due_on: string;
  original_due_on: string;
  is_passed: boolean;
  passed_on: string | null;
  step: Step | null;
  deviation: number;
  version: number;
}

export interface ProjectDetail extends ProjectCard {
  description: string | null;
  direction: string | null;
  region: string | null;
  organizations: { id: string; name: string; role: OrganizationRole; is_center: boolean }[];
  milestone_list: MilestoneRow[];
  subproject_list: ProjectCard[];
  task_list: {
    id: string;
    title: string;
    status: 'new' | 'in_progress' | 'in_review' | 'done' | 'cancelled';
    due_on: string | null;
    assignee: Ref | null;
    step: Step | null;
  }[];
  question: { text: string; asked_on: string } | null;
  last_decision: { kind: DecisionKind; decided_on: string } | null;
}

export interface ProjectsView {
  as_of: string;
  items: ProjectCard[];
  types: ProjectType[];
  people: Ref[];
  is_demo: boolean;
}

/** «Что если»: новые сроки проекта и его вех — ничего не записывается (инвариант 2). */
export interface WhatIfChange {
  kind: 'project' | 'milestone';
  id: string;
  due_on: string;
}

/** «Применить»: те же сроки плюс версия записи, которую видел человек. */
export interface DatesChange extends WhatIfChange {
  version: number;
}

export interface WhatIfState {
  step: Step | null;
  deviation: number;
  lag_days: number;
  due_on: string;
}

export interface WhatIfResult {
  project: { before: WhatIfState; after: WhatIfState };
  milestones: { id: string; title: string; before: Step | null; after: Step | null }[];
  /** Как изменится Пульт: счётчики ступеней до и после. */
  pult: { before: Record<Step, number>; after: Record<Step, number> };
}

export interface NewProject {
  title: string;
  type_code: string;
  started_on: string;
  due_on: string | null;
  responsible_id: string | null;
  parent_id: string | null;
  is_multiyear: boolean;
}

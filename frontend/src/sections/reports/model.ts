/**
 * Доклады и мероприятия — договор данных раздела: «готовы ли мы к дате и кто задерживает?»
 * (ТЗ 2, 3.5). Форма ответов `GET /api/v1/preparations…`.
 *
 * **Числа считает сервер** (инвариант 2): ступень подготовки, дни до показа, сведения —
 * сколько запрошено, получено и просрочено, «кто задерживает» и на сколько, ответы
 * вопросов. Экран только показывает.
 *
 * Допущения (docs/OPEN-QUESTIONS.md): V41 — ступени подготовки: показ прошёл, а этап не
 * «показ» — просрочено; до показа не больше порога «горит» — горит; «начать готовить»
 * наступило, а этап всё ещё «тезисы» — молчит; V42 — запрос сведений просрочен, если срок
 * прошёл и сведения не получены, задерживает тот, от кого они ждутся; V43 — напоминание —
 * готовый текст для копирования, отправляет человек своим каналом.
 */

import type { Step } from '@/sections/pult/model';

export type PreparationKind = 'report' | 'event';

/** Этап подготовки (ТЗ 3.5). Порядок объявления — порядок фишек. */
export type PrepStage = 'theses' | 'data' | 'draft' | 'approval' | 'rehearsal' | 'shown';

export const PREP_STAGES: readonly PrepStage[] = [
  'theses',
  'data',
  'draft',
  'approval',
  'rehearsal',
  'shown',
];

/** Адресат доклада (ТЗ 3.5). */
export type Addressee = 'cabinet' | 'administration' | 'president' | 'prime_minister' | 'other';

export const ADDRESSEES: readonly Addressee[] = [
  'cabinet',
  'administration',
  'president',
  'prime_minister',
  'other',
];

export interface Person {
  id: string;
  name: string;
}

/** От кого ждём сведения: сотрудник агентства или организация. */
export interface Source {
  kind: 'person' | 'organization';
  id: string;
  name: string;
}

export interface ChecklistItem {
  id: string;
  text: string;
  is_done: boolean;
  version: number;
}

export interface InfoRequest {
  id: string;
  what: string;
  source: Source;
  due_on: string | null;
  received_on: string | null;
  /** Считает сервер: запрошено, получено, просрочено (ТЗ 3.5). */
  state: 'requested' | 'received' | 'overdue';
  /** У просроченного — сколько дней задерживает; у остальных 0. */
  late_days: number;
  version: number;
}

/** «Кто задерживает»: источник, сколько сведений не дал и на сколько дольше всего. */
export interface Delay {
  source: Source;
  count: number;
  days: number;
  /** Запросы, о которых напомнить. */
  requests: string[];
}

export interface PreparationRow {
  id: string;
  kind: PreparationKind;
  title: string;
  addressee: Addressee | null;
  show_on: string;
  start_on: string | null;
  responsible: Person | null;
  stage: PrepStage;
  link: { type: 'project'; id: string; title: string } | null;
  checklist: { done: number; total: number };
  requests: { total: number; received: number; overdue: number };
  delays: Delay[];
  /** Дней до показа; отрицательное — показ прошёл. */
  days_left: number;
  step: Step | null;
  deviation: number;
  version: number;
}

/** Статус версии презентации (ТЗ 3.5). */
export type VersionState = 'review' | 'rework' | 'accepted';

export const VERSION_STATES: readonly VersionState[] = ['review', 'rework', 'accepted'];

export interface SlideComment {
  id: string;
  slide: number;
  text: string;
  author: 'assistant' | 'leader' | null;
  created_at: string;
  /** Номер версии, в которой исправлено; `null` — ещё не исправлено. */
  fixed_in: number | null;
  version: number;
}

export interface PresentationVersion {
  id: string;
  number: number;
  state: VersionState;
  file: { id: string; name: string; size: number; content_type: string };
  uploaded_at: string;
  uploaded_by: 'assistant' | 'leader' | null;
  comments: SlideComment[];
  version: number;
}

export interface PreparationCard extends PreparationRow {
  items: ChecklistItem[];
  info_requests: InfoRequest[];
  /** Загруженные версии презентации — новые первыми. */
  versions: PresentationVersion[];
}

export const QUESTIONS = ['readiness', 'start_now'] as const;

export type QuestionKey = (typeof QUESTIONS)[number];

export type QuestionAnswer =
  | {
      /** «Готовы ли к дате и кто задерживает?» (ТЗ 5) — по ближайшей подготовке. */
      key: 'readiness';
      nearest: {
        id: string;
        title: string;
        days_left: number;
        missing: number;
        delay: Delay | null;
      } | null;
      /** Подготовок, где сведений не хватает. */
      count: number;
      rows: string[];
    }
  | {
      /** «Что пора начинать готовить?» — «начать готовить» наступило, а этап — тезисы. */
      key: 'start_now';
      count: number;
      rows: string[];
    };

export interface ReportsView {
  as_of: string;
  questions: QuestionAnswer[];
  /** В порядке лестницы, затем по дате показа. */
  items: PreparationRow[];
  people: Person[];
  organizations: { id: string; name: string; short_name: string | null }[];
  projects: { id: string; code: string; title: string }[];
  is_demo: boolean;
}

/** Новая подготовка: обязательны вид, название и дата показа (ТЗ 7 — минимум полей). */
export interface NewPreparation {
  kind: PreparationKind;
  title: string;
  show_on: string;
  start_on: string | null;
  addressee: Addressee | null;
  responsible_id: string | null;
  project_id: string | null;
}

export interface NewRequest {
  what: string;
  source_kind: 'person' | 'organization';
  source_id: string;
  due_on: string | null;
}

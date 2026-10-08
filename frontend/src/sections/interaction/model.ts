/**
 * Взаимодействие — договор данных раздела: «кто кого ждёт: организации, письма,
 * соглашения?» (ТЗ 2, 3.4). Форма ответов `GET /api/v1/interaction…`.
 *
 * Экран утверждён заказчиком 01.10.2026 на вымышленных данных этой формы, и API написан под
 * него (`backend/app/api/routes/interaction.py`). Сервер в памяти для тестов экрана —
 * `test-server.ts`.
 *
 * **Числа считает сервер** (инвариант 2): состояние письма, ступень и отклонение, дни
 * ожидания и ответа, медиана скорости ответа, «спит» у соглашения, четыре ответа и их
 * списки. Экран только показывает.
 *
 * **Скорость ответа по организации — только при пяти письмах и больше** (ТЗ 4, 11); меньше —
 * честное «мало писем», а не среднее по двум (ТЗ 5: «средние по выборке меньше пяти»
 * запрещены). Это критерий 4 блока 2.
 *
 * Допущения (docs/OPEN-QUESTIONS.md): V38 — оценивается ответ на наше исходящее письмо;
 * V39 — у исходящего «ждём ответа» без срока становится «зависит от чужих» после порога
 * молчания; V40 — «движение» соглашения — правка следующего шага или его даты.
 */

import type { Step } from '@/sections/pult/model';

/** Вид организации (ТЗ 3.4) — как в справочнике `OrganizationKind` сервера. */
export type OrganizationKind = 'ministry' | 'agency' | 'khokimiyat' | 'international' | 'company';

export type Direction = 'incoming' | 'outgoing';

/** Оценка ответа руководителем в одно касание (ТЗ 3.4, 11). Порядок — порядок кнопок. */
export type Rating = 'substance' | 'formal' | 'off_topic';

export const RATINGS: readonly Rating[] = ['substance', 'formal', 'off_topic'];

export type AgreementKind = 'memorandum' | 'contract';

/** Роль организации в проекте (ТЗ 3.1) — как `OrganizationRole` сервера. */
export type OrganizationRole = 'customer' | 'executor' | 'co_executor' | 'lead_agency';

/** С чем связано письмо (ТЗ 3.4): проект, поручение Ижро, подготовка доклада. */
export type LinkType = 'project' | 'ijro' | 'preparation';

/**
 * Состояние письма — считает сервер:
 * - `waiting_reply` — наше исходящее, ответа нет: «кто нам не отвечает»;
 * - `to_answer` — входящее, мы ещё не ответили: «на что мы должны ответить»;
 * - `answered` — ответ есть (у исходящего — получен, у входящего — отправлен).
 */
export type LetterState = 'waiting_reply' | 'to_answer' | 'answered';

export const LETTER_STATES: readonly LetterState[] = ['to_answer', 'waiting_reply', 'answered'];

export interface Person {
  id: string;
  name: string;
}

export interface OrganizationRef {
  id: string;
  name: string;
  short_name: string | null;
}

export interface LetterRow {
  id: string;
  direction: Direction;
  organization: OrganizationRef;
  subject: string;
  /** Номер как на бланке: «02-14/1532». */
  number: string | null;
  sent_on: string;
  /** Срок ответа: у входящего — наш, у исходящего — тот, что мы попросили. */
  due_on: string | null;
  author: Person | null;
  link: { type: LinkType; id: string; title: string } | null;
  answered_on: string | null;
  /** Ответное письмо, если внесено: номер и дата. */
  reply: { number: string | null; sent_on: string } | null;
  rating: Rating | null;
  state: LetterState;
  /** Ступень лестницы; `null` — по плану или отвечено. */
  step: Step | null;
  deviation: number;
  /** Дней от письма: у неотвеченного — сколько ждёт, у отвеченного — за сколько ответили. */
  days: number;
  version: number;
}

/** Скорость ответа организации: медиана — только при `letters ≥ min_letters`. */
export interface Speed {
  letters: number;
  median_days: number | null;
}

export interface OrganizationRow {
  id: string;
  name: string;
  short_name: string | null;
  kind: OrganizationKind;
  /** Учреждена агентством — Центр (ТЗ 3.4). */
  is_founded_by_agency: boolean;
  phone: string | null;
  email: string | null;
  /** Наших исходящих без ответа. */
  waiting: number;
  /** Их входящих, на которые мы не ответили. */
  to_answer: number;
  agreement_count: number;
  sleeping: number;
  /** Соглашений, у которых следующий шаг просрочен. */
  overdue_steps: number;
  /** Поручений Ижро, где организация — головной исполнитель. */
  ijro_lead: number;
  project_count: number;
  speed: Speed;
  /** Оценки ответов руководителем — сколько каких. */
  ratings: Record<Rating, number>;
}

export interface Agreement {
  id: string;
  organization: OrganizationRef;
  kind: AgreementKind;
  title: string;
  signed_on: string;
  valid_until: string | null;
  next_step: string | null;
  next_step_on: string | null;
  responsible: Person | null;
  /** Последнее движение: правка следующего шага или его даты (V40). */
  moved_on: string;
  /** Нет движения дольше порога — «спит» (ТЗ 5). */
  sleeping: boolean;
  quiet_days: number;
  step: Step | null;
  deviation: number;
  version: number;
}

/** Карточка организации собирает письма, поручения, проекты, соглашения (ТЗ 11). */
export interface OrganizationCard extends OrganizationRow {
  letters: LetterRow[];
  agreements: Agreement[];
  ijro: { id: string; place: string; content: string; step: Step | null }[];
  projects: { id: string; code: string; title: string; role: OrganizationRole }[];
}

export const QUESTIONS = ['not_answering', 'to_answer', 'speed', 'sleeping'] as const;

export type QuestionKey = (typeof QUESTIONS)[number];

/** Ответ на вопрос: число или фраза и **те же строки**, что считались (ТЗ 5). */
export type QuestionAnswer =
  | {
      key: 'not_answering';
      count: number;
      /** По организациям, больше первым: кому напомнить. */
      organizations: {
        organization: OrganizationRef;
        count: number;
        oldest_days: number;
        rows: string[];
      }[];
      rows: string[];
    }
  | {
      key: 'to_answer';
      count: number;
      overdue: number;
      /** Ближайший срок среди непросроченных. */
      nearest: { id: string; due_on: string; days: number } | null;
      rows: string[];
    }
  | {
      key: 'speed';
      /** Организации с медианой — медленные первыми. */
      measured: { organization: OrganizationRef; median_days: number; letters: number }[];
      /** Писем меньше порога: медианы нет, это говорится словами. */
      little_data: number;
      min_letters: number;
      /** Строки списка — организации. */
      rows: string[];
    }
  | {
      key: 'sleeping';
      count: number;
      oldest: { id: string; days: number } | null;
      /** Строки списка — соглашения. */
      rows: string[];
    };

export interface Thresholds {
  burn_days: number;
  quiet_days: number;
  /** «Спит» — соглашение без движения дольше стольких дней (ТЗ 5). */
  sleeping_days: number;
  /** Скорость ответа — только при стольких письмах и больше (ТЗ 4). */
  min_letters: number;
}

export interface InteractionView {
  as_of: string;
  thresholds: Thresholds;
  questions: QuestionAnswer[];
  /** Письма в порядке лестницы, затем новые первыми. */
  letters: LetterRow[];
  organizations: OrganizationRow[];
  agreements: Agreement[];
  people: Person[];
  /** Все действующие организации — выбор в форме нового письма. */
  choices: OrganizationRef[];
  is_demo: boolean;
}

/** Новое письмо: обязательны направление, организация и тема (ТЗ 7 — минимум полей). */
export interface NewLetter {
  direction: Direction;
  organization_id: string;
  subject: string;
  number: string | null;
  sent_on: string;
  due_on: string | null;
  author_id: string | null;
}

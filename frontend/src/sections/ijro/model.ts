/**
 * Ижро — договор данных раздела.
 *
 * Это форма будущего ответа API (`GET /api/v1/ijro…`). Экран строится раньше API по
 * правилу блока «экран → API» (CLAUDE.md): вымышленный сервер (`demo.ts`) отдаёт ровно эту
 * форму, и замена его настоящим будет заменой тел функций в хуках, а не экрана.
 *
 * **Числа считает сервер** (инвариант 2): ступень лестницы и отклонение, признак жизни,
 * промежуточный срок, число продлений, двенадцать ответов и их списки, стена документов,
 * классы предпросмотра. Экран их только показывает. У каждого числа из привоза — дата
 * таблицы (инвариант 7).
 *
 * **Содержание, механизм, проблема и предложение — узбекская кириллица как в источнике**
 * (ТЗ 3.3): это данные, а не текст интерфейса, и они не переводятся.
 *
 * Допущения, на которых стоит договор (docs/OPEN-QUESTIONS.md):
 * - V31 — двенадцать вопросов: семь из ТЗ 5 и пять из ТЗ 3.3, 4 и ADR-0033 (`QUESTIONS`).
 * - V32 — пять этапов ТЗ 3.3 (`Stage`); «зависит от чужих» — ступень, а не этап; конечный
 *   этап один — «снято с контроля».
 * - V33 — три точности срока (`DuePrecision`); горит только срок с известным днём.
 * - V34 — «Разложить на задачу»: название — первая фраза содержания, ответственный —
 *   сопоставленный сотрудник, тип «подготовка сведений по Ижро», срок — за три рабочих дня.
 * - V35 — контрольную отметку ставят оба; решения и вопросы — как на Пульте; этап, проблема
 *   и предложение, «запрошено продление», сопоставление ФИО и загрузка — только помощник.
 */

import type { DecisionKind, Step } from '@/sections/pult/model';
import type { TaskStatus } from '@/sections/tasks/model';
import type { Role } from '@/shared/api/orbita';

/** Откуда пришла таблица (ТЗ 3.3): АП, Кабмин, законодательные акты. Как в `domain/ijro.py`. */
export type IjroSource = 'pa' | 'vm' | 'legal';

export const SOURCES: readonly IjroSource[] = ['pa', 'vm', 'legal'];

/** Вид документа (ТЗ 3.3); написание вида входит в номер («ПҚ-135», «ВМҚ-512») — это данные. */
export type DocumentKind = 'farmon' | 'qaror' | 'qonun' | 'bayon' | 'topshiriq' | 'other';

/** Этап поручения (ТЗ 3.3, V32). Порядок объявления — порядок фишек в карточке. */
export type Stage =
  'not_started' | 'in_progress' | 'submitted' | 'returned' | 'removed_from_control';

export const STAGES: readonly Stage[] = [
  'not_started',
  'in_progress',
  'submitted',
  'returned',
  'removed_from_control',
];

/**
 * Этапы, на которых работа — наша: по ним считается лестница. «Сдано» до возврата — не
 * наше: торопить некого, срок после сдачи не «просрочен». Снятое с контроля — конечное.
 */
export const OPEN_STAGES: ReadonlySet<Stage> = new Set(['not_started', 'in_progress', 'returned']);

export const TERMINAL_STAGE: Stage = 'removed_from_control';

/** Точность срока (ТЗ 3.3, V33). Месяц и конец года по дням не горят. */
export type DuePrecision = 'day' | 'month' | 'end_of_year';

/** Вид контрольной отметки (ТЗ 3.3). Порядок — порядок кнопок в одно касание. */
export type MarkKind = 'contacted' | 'doing' | 'no_answer';

export const MARK_KINDS: readonly MarkKind[] = ['contacted', 'doing', 'no_answer'];

/** Откуда признак жизни (ТЗ 4): самое свежее из трёх событий. */
export type LifeSource = 'control_mark' | 'task_movement' | 'interim_report';

/** Вид переноса срока в истории продлений (ТЗ 3.3): продление или уточнение даты. */
export type ExtensionKind = 'extension' | 'correction';

export interface Person {
  id: string;
  name: string;
}

/** Головной исполнитель — организация из справочника (ТЗ 3.4); короткое имя — для строки. */
export interface Organization {
  id: string;
  name: string;
  short_name: string | null;
}

export interface IjroDocument {
  id: string;
  kind: DocumentKind;
  /** Номер как в источнике, с видом: «ПФ-155», «ВМҚ-512». Опознаётся вместе с датой. */
  code: string;
  issued_on: string;
  /** Название как в источнике, узбекская кириллица. */
  title: string;
  source: IjroSource;
}

/** Запись истории продлений: «было → стало, дата, партия привоза, вид переноса» (ТЗ 3.3). */
export interface Extension {
  from: string;
  to: string;
  /** Дата таблицы, из которой пришёл перенос; подтвердил его человек (ТЗ 7). */
  on: string;
  batch_id: string;
  kind: ExtensionKind;
}

export interface ControlMark {
  id: string;
  kind: MarkKind;
  promised_on: string | null;
  comment: string | null;
  made_at: string;
  /** Кто поставил: отметку ставят оба (V35), и подпись роли — часть записи (инвариант 13). */
  author: Role;
}

export interface Comment {
  id: string;
  text: string;
  author: Role;
  created_at: string;
}

/** Связанная задача (ADR-0033): её ступень — сигнал расхождения, а не этап поручения. */
export interface LinkedTask {
  id: string;
  code: string;
  title: string;
  status: TaskStatus;
  step: Step | null;
  due_on: string | null;
  /** Последнее движение задачи — оно засчитывается поручению как признак жизни. */
  moved_on: string;
}

/**
 * Строка списка. Всё, что нужно списку, таблице, фильтрам и стене, — без длинных полей
 * карточки. Порядок строк задаёт сервер: лестница, затем срок (`domain/attention.py`).
 */
export interface AssignmentRow {
  id: string;
  document: Pick<IjroDocument, 'id' | 'code' | 'source'>;
  /** Пункт как в источнике: «5.1-банд», «2-илова 12-банд»; пусто — у строки пункта нет. */
  band: string | null;
  band_order: number;
  /** Содержание как в источнике. Первую строку для телефона режет экран. */
  content: string;
  due_on: string | null;
  due_precision: DuePrecision;
  /** Первый срок; продление видно как «исходный → текущий». */
  original_due_on: string | null;
  /** Середина срока, если срок длиннее трёх месяцев (ТЗ 3.3, V3); считает сервер. */
  interim_on: string | null;
  /** Сколько раз срок продлевали — «продлевали ≥ 2» (ТЗ 5). */
  extensions: number;
  extension_requested: boolean;
  /** Написание из таблицы хранится всегда (инвариант 6); сопоставление — отдельно. */
  responsible_raw: string;
  responsible: Person | null;
  /** `null` — головной исполнитель само агентство. */
  lead_organization: Organization | null;
  /** Головной — не агентство: мы соисполнитель (ТЗ 3.3). */
  is_co_executor: boolean;
  stage: Stage;
  stage_changed_on: string;
  /** Ступень лестницы; `null` — по плану, сдано или снято с контроля. */
  step: Step | null;
  deviation: number;
  /** Самое свежее из трёх событий; `null` — движения не было с привоза. */
  sign_of_life: { on: string; source: LifeSource } | null;
  has_problem: boolean;
  question: { id: string; text: string; asked_on: string } | null;
  last_decision: { id: string; kind: DecisionKind; decided_on: string } | null;
  /** Связанных задач — «без задач» (V31, ADR-0033). */
  tasks: number;
  /** Когда строка появилась в реестре — от неё считается тишина без единого события. */
  first_seen_on: string;
  version: number;
}

export interface AssignmentCard extends AssignmentRow {
  document: IjroDocument;
  /** Механизм исполнения как в источнике; пусто — в таблице графы нет. */
  mechanism: string | null;
  extension_history: Extension[];
  problem: string | null;
  proposal: string | null;
  problem_updated_on: string | null;
  marks: ControlMark[];
  linked_tasks: LinkedTask[];
  comments: Comment[];
  /**
   * Кого предлагает система по написанию из таблицы: «Это Каримов А.?». Только когда
   * сотрудник не сопоставлен; подтверждает человек, псевдоним запоминается (ТЗ 7).
   */
  suggestions: Person[];
  /** «АП · таблица от DD.MM.YYYY · файл.docx» — партия привоза строки (ТЗ 3.3). */
  import: { batch_id: string; table_on: string; file: string };
}

/** Клетка стены: один пункт документа, окрашенный ступенью; снятое с контроля — приглушено. */
export interface WallCell {
  id: string;
  band: string | null;
  stage: Stage;
  step: Step | null;
}

/** «Как исполнен документ целиком?» — карточка стены документов (ТЗ 5). */
export interface WallDocument {
  document: IjroDocument;
  /** Сдано или снято с контроля — «сдано X из Y». */
  done: number;
  total: number;
  cells: WallCell[];
  /** «Кого вызвать с отчётом»: у кого больше всего открытых пунктов документа. */
  call_for_report: { person: Person; open: number } | null;
}

/** Ключи двенадцати вопросов (V31). Порядок — порядок на телефоне: сначала руководителю. */
export const QUESTIONS = [
  'burning',
  'silent',
  'foreign',
  'awaiting',
  'returned',
  'extension_requested',
  'report_up',
  'without_tasks',
  'chronic',
  'year_end',
  'last_batch',
  'documents',
] as const;

export type QuestionKey = (typeof QUESTIONS)[number];

export type PaceVerdict = 'on_track' | 'behind' | 'little_data';

/**
 * Ответ на вопрос: число или фраза и **те же строки**, что считались (ТЗ 5). Список под
 * действием и число в виджете — одно вычисление: `rows` — идентификаторы строк списка.
 */
export type QuestionAnswer =
  | {
      key: 'burning';
      burning: number;
      overdue: number;
      /** Самое давнее просроченное. */
      oldest: { id: string; days: number } | null;
      /** «Кого поторопить»: по ответственным; `null` — не сопоставлен. */
      by_person: {
        person: Person | null;
        responsible_raw: string;
        overdue: number;
        burning: number;
      }[];
      rows: string[];
    }
  | {
      key: 'foreign';
      count: number;
      /** По ведомствам, больше первым: «письмо или звонок». */
      organizations: { organization: Organization; count: number; rows: string[] }[];
      rows: string[];
    }
  | {
      key: 'silent';
      count: number;
      /** «Каримов А. молчит 21 дн» — кто молчит дольше всех при близком сроке. */
      worst: { id: string; person: Person | null; responsible_raw: string; days: number } | null;
      rows: string[];
    }
  | {
      key: 'documents';
      /** Документ с наименьшей долей сданного; `rows` — его открытые пункты. */
      worst: { document: IjroDocument; done: number; total: number } | null;
      rows: string[];
    }
  | {
      key: 'chronic';
      count: number;
      sample: { id: string; original_due_on: string; due_on: string; extensions: number } | null;
      rows: string[];
    }
  | {
      key: 'year_end';
      /** Открытых со сроком до конца года. */
      upcoming: number;
      /** Сдано или снято за окно. */
      closed: number;
      window_days: number;
      min_closed: number;
      verdict: PaceVerdict;
      /** «Начинать заранее»: из наступающих — не начатые. */
      rows: string[];
    }
  | {
      key: 'report_up';
      count: number;
      freshest_on: string | null;
      rows: string[];
    }
  | {
      key: 'awaiting';
      count: number;
      oldest: { id: string; days: number } | null;
      rows: string[];
    }
  | { key: 'extension_requested'; count: number; rows: string[] }
  | {
      key: 'returned';
      count: number;
      oldest: { id: string; days: number } | null;
      rows: string[];
    }
  | {
      key: 'without_tasks';
      count: number;
      /** Открытых с точным сроком — знаменатель полноты (ADR-0033). */
      total: number;
      rows: string[];
    }
  | {
      key: 'last_batch';
      batch: { id: string; table_on: string; file: string; source: IjroSource } | null;
      created: number;
      changed: number;
      vanished: number;
      /** Переносы срока из партии, которые человек ещё не подтвердил (ТЗ 7). */
      pending_extensions: number;
      /** Новые и изменённые — `changed_last_batch` для руководителя. */
      rows: string[];
    };

/** Пороги, по которым посчитаны ответы, — чтобы экран назвал правило рядом с числом. */
export interface Thresholds {
  burn_days: number;
  quiet_days: number;
  /** «Близкий срок» вопроса «работает ли ответственный?»: срок не дальше стольких дней. */
  near_due_days: number;
  /** Окно темпа «хватит ли сил на декабрь?» и сколько закрытого нужно, чтобы судить. */
  pace_window_days: number;
  min_closed_for_pace: number;
}

/** Класс строки предпросмотра (ТЗ 7). Порядок объявления — порядок групп на экране. */
export type ChangeClass =
  | 'new'
  | 'unchanged'
  | 'text_changed'
  | 'responsible_changed'
  | 'due_moved'
  | 'vanished'
  | 'unrecognized';

export const CHANGE_CLASSES: readonly ChangeClass[] = [
  'new',
  'unchanged',
  'text_changed',
  'responsible_changed',
  'due_moved',
  'vanished',
  'unrecognized',
];

export interface PreviewRow {
  id: string;
  class: ChangeClass;
  /** Строка реестра, к которой относится; `null` — новая или не распознана. */
  assignment_id: string | null;
  document_code: string | null;
  band: string | null;
  content: string;
  /** «Было → стало» для изменившегося текста или ответственного. */
  diff: { field: 'content' | 'mechanism' | 'responsible_raw'; from: string; to: string } | null;
  /** Перенос срока: подтверждает человек, вид переноса предлагает сервер (ТЗ 7). */
  due_move: { from: string; to: string; suggested_kind: ExtensionKind } | null;
  /** Написание, которого нет среди псевдонимов, и кого система предлагает. */
  unmatched: { raw: string; suggestions: Person[] } | null;
  /** Строка как в файле — для нераспознанной. */
  raw: string | null;
}

export interface Preview {
  batch_id: string;
  file: string;
  source: IjroSource;
  /** Год таблицы — из заголовка; правится человеком, срок берёт год отсюда (ТЗ 3.3). */
  table_year: number;
  table_on: string;
  counts: Record<ChangeClass, number>;
  rows: PreviewRow[];
  /** Тот же файл уже применяли: «изменений нет» (ТЗ 7, идемпотентность). */
  already_applied_on: string | null;
}

/** Что решил человек в предпросмотре; ключи — `PreviewRow.id`. */
export interface ApplyChoices {
  /** Подтверждённые переносы и их вид; неподтверждённый остаётся на подтверждение. */
  due_moves: Record<string, ExtensionKind>;
  /** Подтверждённые сопоставления написаний: строка → сотрудник. Псевдоним запоминается. */
  aliases: Record<string, string>;
  /** Исчезнувшие строки, которые человек снял с контроля. */
  removed: string[];
}

export type ApplyResult =
  | {
      outcome: 'applied';
      created: number;
      changed: number;
      vanished: number;
      removed: number;
      extensions: number;
      pending_extensions: number;
    }
  | { outcome: 'already_applied'; applied_on: string }
  | { outcome: 'no_changes' };

/** Партия привоза в истории загрузок (ТЗ 3.3, 7). */
export interface Batch {
  id: string;
  file: string;
  source: IjroSource;
  table_on: string;
  uploaded_at: string;
  state: 'applied' | 'discarded';
  counts: Record<ChangeClass, number>;
}

/** Что придёт с файлом: сам файл в этом шаге не разбирается — только его имя и размер. */
export interface UploadInput {
  file: { name: string; size: number };
  /** Источник и год — из заголовка таблицы; человек может поправить до применения. */
  source?: IjroSource;
  table_year?: number;
}

/** «Разложить на задачу» (ADR-0033, V34): что покажет лист подтверждения. */
export interface TaskPrefill {
  title: string;
  type_code: 'ijro_report';
  assignee_id: string | null;
  due_on: string | null;
  ijro_assignment_id: string;
}

/** Строка справки по проблемным поручениям — «что докладывать наверх?» (ТЗ 5, 10). */
export interface SpravkaLine {
  id: string;
  /** «ПҚ-312 · 4-банд». */
  place: string;
  content: string;
  due_on: string | null;
  due_precision: DuePrecision;
  responsible: string;
  problem: string;
  proposal: string | null;
  problem_updated_on: string | null;
}

export interface IjroView {
  /** Момент расчёта (инвариант 7). */
  as_of: string;
  /** Дата последней применённой таблицы — «по таблице от …» на всём разделе. */
  table_on: string | null;
  thresholds: Thresholds;
  /** Двенадцать ответов в порядке `QUESTIONS`. */
  questions: QuestionAnswer[];
  /** Все строки реестра в порядке лестницы; фильтры — на экране, по полям строки. */
  items: AssignmentRow[];
  documents: WallDocument[];
  people: Person[];
  organizations: Organization[];
  /** История загрузок, новые первыми. */
  batches: Batch[];
  /** Вымышленные данные: экран обязан это сказать, иначе их примут за настоящие. */
  is_demo: boolean;
}

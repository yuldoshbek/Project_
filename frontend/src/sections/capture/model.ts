/**
 * Захват — договор данных `GET /api/v1/captures` и `POST /api/v1/captures`.
 *
 * Экран утверждён заказчиком 28.09.2026 на вымышленных данных той же формы; API написан под
 * него (CLAUDE.md, цикл блока «экран → API»). Разбор фразы — `POST /api/v1/tasks/parse`,
 * общий со строкой «Новая задача».
 *
 * Захват — быстрая запись одной кнопкой с выбором типа (ТЗ 7, CONTEXT). Куда уходит запись —
 * допущение V17: задача и просьба руководителя — в «Задачи», идея, письмо и мероприятие — во
 * входящие, пока их разделы не появятся (блоки 2–3).
 */

/** Тип записи. Порядок — порядок кнопок. */
export const CAPTURE_KINDS = ['task', 'request', 'idea', 'letter', 'event'] as const;

export type CaptureKind = (typeof CAPTURE_KINDS)[number];

/** Куда ушла запись: сразу в раздел или во входящие до его появления. */
export type Destination = 'tasks' | 'inbox';

export interface Capture {
  id: string;
  kind: CaptureKind;
  /** Текст как записан — для идеи, письма, мероприятия; у задачи — название после разбора. */
  text: string;
  /** Срок задачи и просьбы, срок ответа на письмо, дата мероприятия — из разбора или руками. */
  due_on: string | null;
  author: 'assistant' | 'leader';
  created_at: string;
  destination: Destination;
}

export interface CaptureView {
  as_of: string;
  /** Последние записи обоих — сначала новые; сколько — решает сервер. */
  recent: Capture[];
  is_demo: boolean;
}

/** Ответ на запись: у задачи и просьбы — номер заведённой задачи. */
export interface SavedCapture extends Capture {
  task_code: string | null;
}

/**
 * Новая запись. Поля — те, что экран показывает под фразой: у задачи все четыре, у просьбы
 * срок и «кому», у письма и мероприятия срок, у идеи ни одного. Лишнее сервер отклоняет.
 */
export interface NewCapture {
  kind: CaptureKind;
  text: string;
  due_on?: string | null;
  assignee_id?: string | null;
  type_code?: string | null;
  project_id?: string | null;
}

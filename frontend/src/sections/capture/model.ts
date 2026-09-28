/**
 * Захват — договор данных.
 *
 * Форма будущих ответов `GET /api/v1/captures` и `POST /api/v1/captures`. Экран строится
 * раньше API по правилу блока «экран → API» (CLAUDE.md): пока его не утвердили, отвечает
 * вымышленный сервер `demo.ts`. Задача уже сейчас заводится настоящим API «Задач»: её экран
 * утверждён, и захват только открывает к нему короткий путь.
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
  /** Последние записи обоих — сначала новые. */
  recent: Capture[];
  is_demo: boolean;
}

/** Новая запись, кроме задачи: у задачи свой путь — `POST /api/v1/tasks`. */
export interface NewCapture {
  kind: Exclude<CaptureKind, 'task'>;
  text: string;
  due_on: string | null;
  /** Кому — только у просьбы руководителя: разбор предлагает, человек решает. */
  assignee_id: string | null;
}

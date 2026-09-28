/**
 * Вымышленный сервер Захвата — пока экран не утверждён и API нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит, потом API под
 * утверждённый экран (CLAUDE.md, цикл блока). Задача про смету Минфина — из вымышленной
 * базы (`backend/app/demo.py`), её видно и в «Задачах»; остальные записи выдуманы здесь.
 * Даты — в днях от сегодня, поэтому в тексте записей дат нет: «ответ до 10 октября» в тексте
 * разошёлся бы со сроком на следующий же день. Заведённое во вкладке живёт до перезагрузки.
 * После утверждения файл удаляется.
 */

import { AGENCY_TIMEZONE } from '@/shared/time';

import type { Capture, CaptureView, NewCapture } from './model';

const DAY_MS = 86_400_000;
const HOUR_MS = 3_600_000;

function dayIn(now: Date, days: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(
    new Date(now.getTime() + days * DAY_MS),
  );
}

interface Spec {
  kind: Capture['kind'];
  text: string;
  /** Срок — дней от сегодня. */
  due?: number;
  author: Capture['author'];
  /** Сколько часов назад записано. */
  ago: number;
}

const SPECS: Spec[] = [
  {
    kind: 'letter',
    text: 'Минэкологии просит данные мониторинга засухи за август',
    due: 12,
    author: 'assistant',
    ago: 2,
  },
  {
    kind: 'task',
    text: 'Позвонить в Минфин по смете миссии на следующий год',
    due: 0,
    author: 'assistant',
    ago: 5,
  },
  {
    kind: 'idea',
    text: 'Спутниковый мониторинг пастбищ — предложить Минсельхозу пилот на весну',
    author: 'leader',
    ago: 26,
  },
  {
    kind: 'request',
    text: 'Справка по паводкам для Кабмина',
    due: 4,
    author: 'leader',
    ago: 49,
  },
  {
    kind: 'event',
    text: 'Международная конференция по ДЗЗ в Самарканде — выступление агентства',
    due: 47,
    author: 'assistant',
    ago: 75,
  },
];

export class DemoCaptures {
  private added: Capture[] = [];
  private counter = 0;

  constructor(private readonly now: () => Date = () => new Date()) {}

  reset(): void {
    this.added = [];
    this.counter = 0;
  }

  view(): CaptureView {
    const now = this.now();
    const fixed: Capture[] = SPECS.map((spec, index) => ({
      id: `cp-${index}`,
      kind: spec.kind,
      text: spec.text,
      due_on: spec.due === undefined ? null : dayIn(now, spec.due),
      author: spec.author,
      created_at: new Date(now.getTime() - spec.ago * HOUR_MS).toISOString(),
      destination: spec.kind === 'task' || spec.kind === 'request' ? 'tasks' : 'inbox',
    }));
    return {
      as_of: now.toISOString(),
      // Сортировка устойчивая: записанное в одну минуту идёт в порядке записи.
      recent: [...this.added, ...fixed].sort((a, b) => b.created_at.localeCompare(a.created_at)),
      is_demo: true,
    };
  }

  /** Просьба — в «Задачи» с пометкой; идея, письмо, мероприятие — во входящие (V17). */
  save(input: NewCapture, author: Capture['author']): Capture {
    const text = input.text.trim();
    if (!text) throw new Error('Нечего записать: текст пустой');
    this.counter += 1;
    const saved: Capture = {
      id: `cp-new-${this.counter}`,
      kind: input.kind,
      text,
      due_on: input.due_on,
      author,
      created_at: this.now().toISOString(),
      destination: input.kind === 'request' ? 'tasks' : 'inbox',
    };
    this.added.unshift(saved);
    return saved;
  }

  /** Задачу заводит настоящий API «Задач»; в недавние она попадает, чтобы было видно, куда ушла. */
  remember(title: string, dueOn: string | null, author: Capture['author']): Capture {
    this.counter += 1;
    const saved: Capture = {
      id: `cp-new-${this.counter}`,
      kind: 'task',
      text: title,
      due_on: dueOn,
      author,
      created_at: this.now().toISOString(),
      destination: 'tasks',
    };
    this.added.unshift(saved);
    return saved;
  }
}

export const demoCaptures = new DemoCaptures();

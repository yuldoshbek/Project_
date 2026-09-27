/**
 * Вымышленный сервер раздела «Задачи» — пока экран не утверждён и API нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит, потом API под
 * утверждённый экран (CLAUDE.md, цикл блока). Люди и проекты — те же, что в «Проектах» и на
 * Пульте (`backend/app/demo.py`), типы задач — одиннадцать из ТЗ 3.9 (`backend/app/seed.py`).
 *
 * Правила счёта повторяют домен сервера, чтобы экран утверждали на правильных числах:
 * ступени — `domain/attention`, переходы статуса — `domain/tasks.ALLOWED_TRANSITIONS`,
 * перенос — сдвиг срока позже. После утверждения файл удаляется, считать начинает сервер.
 */

import type { Step } from '@/sections/pult/model';
import { AGENCY_TIMEZONE } from '@/shared/time';

import type {
  ChecklistItem,
  Horizon,
  LoadRow,
  NewTask,
  ParsedLine,
  ProjectRef,
  Ref,
  TaskCard,
  TaskDetail,
  TaskEdit,
  TaskStatus,
  TaskType,
  TasksView,
} from './model';
import { parseLine } from './parse';

const DAY_MS = 86_400_000;
const BURN_DAYS = 7;
const QUIET_DAYS = 14;

function todayInTashkent(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(now);
}

function shift(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

export const TYPES: TaskType[] = [
  { code: 'technical_spec', name: 'Техническое задание' },
  { code: 'review_and_endorse', name: 'Рассмотрение и визирование' },
  { code: 'approval', name: 'Согласование' },
  { code: 'cabinet_submission', name: 'Внесение в Кабмин' },
  { code: 'analytical_note', name: 'Аналитическая информация' },
  { code: 'site_visit', name: 'Выезд на место' },
  { code: 'request_or_survey', name: 'Запрос или опросник' },
  { code: 'subplatform_upload', name: 'Выгрузка в субплатформу' },
  { code: 'participant_selection', name: 'Отбор участников' },
  { code: 'ijro_report', name: 'Подготовка сведений по Ижро' },
  { code: 'other', name: 'Прочее' },
];

export const PEOPLE: Ref[] = [
  { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
];

const PROJECTS: Record<string, ProjectRef> = Object.fromEntries(
  (
    [
      ['mission', 1, 'Спутниковая миссия «Навоий-2»'],
      ['geodata', 2, 'Постановление о порядке обмена геоданными'],
      ['drought', 3, 'Цикл мониторинга: засуха-2026'],
      ['portal', 4, 'Геопортал агентства'],
      ['crops', 5, 'Пилот: мониторинг посевов'],
      ['standard', 6, 'Стандарт на снимки ДЗЗ'],
      ['interns', 7, 'Кадры: стажировки в Центре мониторинга'],
      ['station', 8, 'Приём наземной станции по соглашению о сотрудничестве'],
      ['aerial', 10, 'Заказ услуги: аэрофотосъёмка Ферганской долины'],
      ['floods', 11, 'Цикл мониторинга: паводки'],
      ['calibration', 12, 'Пилот: калибровка снимков'],
      ['snow', 17, 'Цикл мониторинга: снежный покров'],
      ['lab', 18, 'Учебная лаборатория ДЗЗ в вузе'],
      ['legacy', 21, 'Прежний портал спутниковых данных'],
    ] as const
  ).map(([key, number, title]) => [
    key,
    { id: `pr-${key}`, code: `PRJ-2026-${String(number).padStart(3, '0')}`, title },
  ]),
);

interface Spec {
  title: string;
  type: string;
  who: string | null;
  /** Срок — дней от сегодня; `null` — без срока. */
  due: number | null;
  original?: number;
  moves?: number;
  status?: TaskStatus;
  project?: string;
  ijro?: string;
  checklist?: [string, boolean][];
  /** Дней без движения — признак жизни задачи. */
  life?: number;
  /** Открытый вопрос руководителю — дней ждёт. */
  question?: number;
  questionText?: string;
  /** Закрыта столько дней назад. */
  closed?: number;
  description?: string;
}

const SPECS: Spec[] = [
  {
    title: 'Аналитическая справка по засухе для Кабинета министров',
    type: 'analytical_note',
    who: 'p-rakhimov',
    due: -3,
    project: 'drought',
    life: 2,
    checklist: [
      ['Свести данные по NDVI за август', true],
      ['Карта засушливых районов', true],
      ['Текст справки на согласование', false],
    ],
  },
  {
    title: 'Выгрузка данных в субплатформу',
    type: 'subplatform_upload',
    who: 'p-tursunov',
    due: -2,
    original: -6,
    moves: 1,
    project: 'portal',
    life: 4,
  },
  {
    title: 'Сведения по поручению ПФ-155 §5.1',
    type: 'ijro_report',
    who: 'p-rakhimov',
    due: -1,
    ijro: 'ПФ-155 §5.1',
    life: 6,
    checklist: [
      ['Запросить данные у Центра', false],
      ['Подготовить проект ответа', false],
    ],
  },
  {
    title: 'Отбор участников пилота с Минсельхозом',
    type: 'participant_selection',
    who: 'p-abdullaeva',
    due: 0,
    project: 'crops',
    life: 1,
  },
  {
    title: 'Позвонить в Минфин по смете миссии на следующий год',
    type: 'other',
    who: 'p-karimov',
    due: 0,
    status: 'new',
    life: 1,
  },
  {
    title: 'Сведения для Администрации Президента по мониторингу водохранилищ',
    type: 'ijro_report',
    who: 'p-yusupova',
    due: 1,
    ijro: 'ПП-4231 §2',
    life: 2,
  },
  {
    title: 'Согласование проекта постановления с Минэкологии',
    type: 'approval',
    who: 'p-yusupova',
    due: 3,
    status: 'in_review',
    project: 'geodata',
    life: 1,
    checklist: [
      ['Отправить проект письмом', true],
      ['Получить замечания', true],
      ['Свести замечания в таблицу', true],
      ['Повторное согласование', false],
    ],
  },
  {
    title: 'Выезд на полигон в Джизаке',
    type: 'site_visit',
    who: 'p-karimov',
    due: 4,
    project: 'calibration',
    life: 5,
    checklist: [
      ['Транспорт', true],
      ['Приборы калибровки', false],
      ['Письмо в хокимият', false],
    ],
  },
  {
    title: 'Запрос сведений у хокимиятов о паводках',
    type: 'request_or_survey',
    who: 'p-rakhimov',
    due: 5,
    project: 'floods',
    life: 16,
  },
  {
    title: 'Внесение проекта постановления в Кабинет министров',
    type: 'cabinet_submission',
    who: 'p-yusupova',
    due: 6,
    project: 'geodata',
    question: 2,
    questionText: 'Вносить в текущей редакции или дождаться замечаний Минюста?',
    life: 2,
    description: 'Вносим после согласования с Минэкологии; руководитель решает, в какой редакции.',
  },
  {
    title: 'Сводка по паводкам за сентябрь',
    type: 'analytical_note',
    who: 'p-rakhimov',
    due: 12,
    project: 'floods',
    life: 3,
  },
  {
    title: 'Договор с исполнителем аэрофотосъёмки',
    type: 'approval',
    who: 'p-tursunov',
    due: 18,
    project: 'aerial',
    life: 21,
  },
  {
    title: 'ТЗ на модуль каталога снимков',
    type: 'technical_spec',
    who: 'p-tursunov',
    due: 20,
    project: 'portal',
    life: 3,
    checklist: [
      ['Требования к поиску', true],
      ['Форматы выдачи', false],
      ['Роли пользователей', false],
      ['Нагрузка', false],
      ['Согласование с Центром', false],
    ],
  },
  {
    title: 'Рассмотрение замечаний к стандарту',
    type: 'review_and_endorse',
    who: 'p-yusupova',
    due: 25,
    project: 'standard',
    life: 4,
  },
  {
    title: 'План работ по группировке на квартал',
    type: 'other',
    who: 'p-karimov',
    due: 30,
    status: 'new',
    project: 'mission',
    life: 3,
  },
  {
    title: 'Опросник для хокимиятов по снежному покрову',
    type: 'request_or_survey',
    who: 'p-rakhimov',
    due: 40,
    status: 'new',
    project: 'snow',
    life: 12,
  },
  {
    title: 'Программа занятий для стажёров',
    type: 'other',
    who: 'p-abdullaeva',
    due: 45,
    project: 'interns',
    life: 6,
  },
  {
    title: 'Подобрать помещение для учебной лаборатории',
    type: 'other',
    who: 'p-abdullaeva',
    due: null,
    project: 'lab',
    life: 30,
  },
  {
    title: 'Тезисы к совещанию по космическому мониторингу',
    type: 'other',
    who: 'p-karimov',
    due: null,
    status: 'new',
    life: 3,
  },
  {
    title: 'Перевод технической документации станции',
    type: 'other',
    who: null,
    due: null,
    project: 'station',
    life: 9,
  },
  {
    title: 'Сведения по поручению ПФ-155 для Администрации Президента',
    type: 'ijro_report',
    who: 'p-rakhimov',
    due: -1,
    status: 'done',
    ijro: 'ПФ-155 §3',
    closed: 1,
  },
  {
    title: 'Разработка ТЗ спутниковой группировки',
    type: 'technical_spec',
    who: 'p-karimov',
    due: 0,
    status: 'done',
    project: 'mission',
    closed: 0,
  },
  {
    title: 'Выгрузка в прежний портал',
    type: 'subplatform_upload',
    who: 'p-tursunov',
    due: -20,
    status: 'cancelled',
    project: 'legacy',
    closed: 30,
  },
];

/** Граф переходов статуса — копия `domain/tasks.ALLOWED_TRANSITIONS`. */
const TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  new: ['in_progress', 'cancelled'],
  in_progress: ['new', 'in_review', 'done', 'cancelled'],
  in_review: ['in_progress', 'done', 'cancelled'],
  done: ['in_progress'],
  cancelled: ['new', 'in_progress'],
};

interface Task {
  id: string;
  code: string;
  title: string;
  type: string | null;
  who: string | null;
  due: number | null;
  original: number | null;
  moves: number;
  status: TaskStatus;
  project: string | null;
  ijro: string | null;
  items: ChecklistItem[];
  life: number;
  question: number | null;
  questionText: string | null;
  closed: number | null;
  created: number;
  description: string | null;
  version: number;
}

function build(spec: Spec, number: number): Task {
  const id = `t-${number}`;
  return {
    id,
    code: `TSK-2026-${String(number).padStart(4, '0')}`,
    title: spec.title,
    type: spec.type,
    who: spec.who,
    due: spec.due,
    original: spec.original ?? spec.due,
    moves: spec.moves ?? 0,
    status: spec.status ?? (spec.closed !== undefined ? 'done' : 'in_progress'),
    project: spec.project ?? null,
    ijro: spec.ijro ?? null,
    items: (spec.checklist ?? []).map(([text, done], index) => ({
      id: `${id}-c${index + 1}`,
      text,
      is_done: done,
      version: 1,
    })),
    life: spec.life ?? 3,
    question: spec.question ?? null,
    questionText: spec.questionText ?? null,
    closed: spec.closed ?? null,
    created: Math.max(spec.life ?? 3, 10) + 5,
    description: spec.description ?? null,
    version: 1,
  };
}

/** Ступень — правило `domain/attention.attention_of`; у задачи чужого ведомства нет. */
function stepOf(task: Task): { step: Step | null; deviation: number } {
  if (task.status === 'done' || task.status === 'cancelled') return { step: null, deviation: 0 };
  if (task.question !== null) return { step: 'awaiting_decision', deviation: task.question };
  if (task.due !== null) {
    if (task.due < 0) return { step: 'overdue', deviation: -task.due };
    if (task.due <= BURN_DAYS) return { step: 'burning', deviation: task.due };
  }
  if (task.life > QUIET_DAYS) return { step: 'silent', deviation: task.life };
  return { step: null, deviation: 0 };
}

function horizonOf(task: Task): Horizon {
  if (task.status === 'done' || task.status === 'cancelled') return 'closed';
  if (task.due === null) return 'none';
  if (task.due < 0) return 'overdue';
  if (task.due === 0) return 'today';
  if (task.due === 1) return 'tomorrow';
  if (task.due <= 7) return 'week';
  return 'later';
}

const HORIZON_ORDER: Horizon[] = [
  'overdue',
  'today',
  'tomorrow',
  'week',
  'later',
  'none',
  'closed',
];

export class DemoTasks {
  private tasks: Task[] = [];
  private next = 0;

  constructor(private readonly clock: () => Date = () => new Date()) {
    this.reset();
  }

  reset(): void {
    this.tasks = SPECS.map((spec, index) => build(spec, index + 1));
    this.next = SPECS.length;
  }

  private today(): string {
    return todayInTashkent(this.clock());
  }

  private card(task: Task): TaskCard {
    const today = this.today();
    const type = TYPES.find((each) => each.code === task.type) ?? null;
    const { step, deviation } = stepOf(task);
    return {
      id: task.id,
      code: task.code,
      title: task.title,
      type,
      status: task.status,
      assignee: PEOPLE.find((person) => person.id === task.who) ?? null,
      due_on: task.due === null ? null : shift(today, task.due),
      original_due_on: task.original === null ? null : shift(today, task.original),
      moves: task.moves,
      horizon: horizonOf(task),
      step,
      deviation,
      project: task.project ? (PROJECTS[task.project] ?? null) : null,
      ijro: task.ijro ? { id: `ijro-${task.ijro}`, label: task.ijro } : null,
      checklist: {
        done: task.items.filter((item) => item.is_done).length,
        total: task.items.length,
      },
      completed_on: task.closed === null ? null : shift(today, -task.closed),
      version: task.version,
    };
  }

  /** Порядок — по группе срока, внутри — по сроку; закрытые — свежие первыми. */
  private ordered(): Task[] {
    return [...this.tasks].sort((left, right) => {
      const group =
        HORIZON_ORDER.indexOf(horizonOf(left)) - HORIZON_ORDER.indexOf(horizonOf(right));
      if (group !== 0) return group;
      if (horizonOf(left) === 'closed') return (left.closed ?? 0) - (right.closed ?? 0);
      return (left.due ?? 0) - (right.due ?? 0) || left.title.localeCompare(right.title, 'ru');
    });
  }

  /** «Кто перегружен?» — по ступеням тех же задач, что в списке. */
  private load(): LoadRow[] {
    const rows = new Map<string, LoadRow>();
    for (const task of this.tasks) {
      if (task.status === 'done' || task.status === 'cancelled' || !task.who) continue;
      const person = PEOPLE.find((each) => each.id === task.who)!;
      const row = rows.get(person.id) ?? { person, overdue: 0, burning: 0, open: 0 };
      const { step } = stepOf(task);
      row.open += 1;
      if (step === 'overdue') row.overdue += 1;
      if (step === 'burning') row.burning += 1;
      rows.set(person.id, row);
    }
    return [...rows.values()].sort(
      (left, right) =>
        right.overdue - left.overdue || right.burning - left.burning || right.open - left.open,
    );
  }

  view(): TasksView {
    return {
      as_of: this.clock().toISOString(),
      items: this.ordered().map((task) => this.card(task)),
      types: TYPES,
      people: PEOPLE,
      projects: Object.values(PROJECTS),
      load: this.load(),
      is_demo: true,
    };
  }

  detail(id: string): TaskDetail {
    const task = this.find(id);
    return {
      ...this.card(task),
      description: task.description,
      checklist_items: task.items.map((item) => ({ ...item })),
      created_on: shift(this.today(), -task.created),
      question:
        task.question !== null && task.questionText
          ? { text: task.questionText, asked_on: shift(this.today(), -task.question) }
          : null,
      transitions: TRANSITIONS[task.status],
    };
  }

  parse(text: string): ParsedLine {
    return parseLine(text, { today: this.today(), people: PEOPLE, types: TYPES });
  }

  create(input: NewTask): TaskDetail {
    const title = input.title.trim();
    if (!title) throw new Error('Напишите, что нужно сделать');
    this.next += 1;
    const due = input.due_on ? daysBetween(this.today(), input.due_on) : null;
    const task: Task = {
      id: `t-new-${this.next}`,
      code: `TSK-2026-${String(this.next).padStart(4, '0')}`,
      title,
      type: input.type_code,
      who: input.assignee_id,
      due,
      original: due,
      moves: 0,
      status: 'new',
      project: Object.entries(PROJECTS).find(([, ref]) => ref.id === input.project_id)?.[0] ?? null,
      ijro: null,
      items: [],
      life: 0,
      question: null,
      questionText: null,
      closed: null,
      created: 0,
      description: null,
      version: 1,
    };
    this.tasks.push(task);
    return this.detail(task.id);
  }

  setStatus(id: string, status: TaskStatus, version: number): void {
    const task = this.find(id, version);
    if (status !== task.status && !TRANSITIONS[task.status].includes(status)) {
      throw new Error('Такой переход статуса не разрешён');
    }
    task.status = status;
    task.closed = status === 'done' || status === 'cancelled' ? 0 : null;
    this.touch(task);
  }

  edit(id: string, input: TaskEdit): void {
    const task = this.find(id, input.version);
    const due = input.due_on ? daysBetween(this.today(), input.due_on) : null;
    if (due !== null && task.due !== null && due > task.due) task.moves += 1;
    if (task.original === null) task.original = due;
    task.title = input.title.trim() || task.title;
    task.type = input.type_code;
    task.who = input.assignee_id;
    task.due = due;
    task.project =
      Object.entries(PROJECTS).find(([, ref]) => ref.id === input.project_id)?.[0] ?? null;
    task.description = input.description?.trim() || null;
    this.touch(task);
  }

  addItem(id: string, text: string): void {
    const task = this.find(id);
    task.items.push({
      id: `${id}-c${task.items.length + 1}-${Date.now()}`,
      text: text.trim(),
      is_done: false,
      version: 1,
    });
    this.touch(task);
  }

  toggleItem(id: string, itemId: string, done: boolean): void {
    const task = this.find(id);
    const item = task.items.find((each) => each.id === itemId);
    if (!item) throw new Error('Пункт не найден');
    item.is_done = done;
    item.version += 1;
    this.touch(task);
  }

  removeItem(id: string, itemId: string): void {
    const task = this.find(id);
    task.items = task.items.filter((each) => each.id !== itemId);
    this.touch(task);
  }

  /** Любая правка — движение: отметка пункта и есть признак жизни задачи. */
  private touch(task: Task): void {
    task.life = 0;
    task.version += 1;
  }

  private find(id: string, version?: number): Task {
    const task = this.tasks.find((each) => each.id === id);
    if (!task) throw new Error('Задача не найдена');
    if (version !== undefined && version !== task.version) {
      throw new Error('Запись уже изменили, пока вы её редактировали');
    }
    return task;
  }
}

export const demoTasks = new DemoTasks();

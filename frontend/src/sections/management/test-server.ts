/**
 * Сервер Управления в памяти — для тестов экрана.
 *
 * Отвечает на те же пути, что `/api/v1/management…`, по тем же правилам, что сервер
 * (`backend/app/services/management.py`): очередь обхода подчиняется порогам (строгое
 * сравнение), правки — по версии (отказ 409), поле без значения — 422. Данные — вымышленная
 * база и наполнение справочников. Сам сервер проверяют `backend/tests/test_management.py`;
 * здесь — что экран делает с его ответами.
 */

import { AGENCY_TIMEZONE } from '@/shared/time';

import type {
  DictionaryEntry,
  DictionaryGroup,
  DictionaryKind,
  ManagementView,
  OrganizationKind,
  Person,
  RoundAction,
  RoundItem,
  TemplateStep,
  Threshold,
  ThresholdKey,
} from './model';

const DAY_MS = 86_400_000;

function dayIn(now: Date, days: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(
    new Date(now.getTime() + days * DAY_MS),
  );
}

/** Понедельник и воскресенье недели по Ташкенту. */
function week(now: Date): [string, string] {
  const today = new Date(`${dayIn(now, 0)}T00:00:00Z`);
  const monday = (today.getUTCDay() + 6) % 7;
  return [dayIn(now, -monday), dayIn(now, 6 - monday)];
}

const RECORD: Record<RoundItem['reason'], RoundItem['record']['kind']> = {
  decision_overdue: 'decision',
  task_overdue: 'task',
  milestone_passed: 'milestone',
  task_review: 'task',
  impediment_stale: 'project',
  project_silent: 'project',
  task_unassigned: 'task',
};

const PEOPLE: Person[] = [
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
];

const ROUND: Omit<RoundItem, 'record'>[] = [
  {
    id: 'r-hurry',
    reason: 'decision_overdue',
    target: { kind: 'task', id: 'jizzakh-visit' },
    title: 'Поторопить: выезд на полигон в Джизаке',
    owner: 'Пилот: калибровка снимков',
    responsible: 'Каримов А.',
    days: 1,
    actions: ['decision_done', 'move_week'],
  },
  {
    id: 'r-drought',
    reason: 'task_overdue',
    target: { kind: 'task', id: 'drought-note' },
    title: 'Аналитическая справка по засухе для Кабинета министров',
    owner: 'Цикл мониторинга: засуха-2026',
    responsible: 'Рахимов Ш.',
    days: 3,
    actions: ['task_done', 'move_week', 'task_cancel'],
  },
  {
    id: 'r-pf155',
    reason: 'task_overdue',
    target: { kind: 'task', id: 'ijro-overdue' },
    title: 'Сведения по поручению ПФ-155 §5.1',
    owner: null,
    responsible: 'Рахимов Ш.',
    days: 1,
    actions: ['task_done', 'move_week', 'task_cancel'],
  },
  {
    id: 'r-acceptance',
    reason: 'milestone_passed',
    target: { kind: 'project', id: 'portal' },
    title: 'Приёмка опытного образца платформы',
    owner: 'Геопортал агентства',
    responsible: 'Турсунов Б.',
    days: 9,
    actions: ['milestone_passed', 'move_week'],
  },
  {
    id: 'r-site',
    reason: 'milestone_passed',
    target: { kind: 'project', id: 'station' },
    title: 'Площадка станции приёма в Самарканде',
    owner: 'Приём наземной станции по соглашению о сотрудничестве',
    responsible: 'Рахимов Ш.',
    days: 8,
    actions: ['milestone_passed', 'move_week'],
  },
  {
    id: 'r-review',
    reason: 'task_review',
    target: { kind: 'task', id: 'geodata-approval' },
    title: 'Согласование проекта постановления с Минэкологии',
    owner: 'Постановление о порядке обмена геоданными',
    responsible: 'Юсупова Д.',
    days: 16,
    actions: ['task_done', 'task_back'],
  },
  {
    id: 'r-air',
    reason: 'impediment_stale',
    target: { kind: 'project', id: 'air' },
    title: 'Совместная программа наблюдения за качеством воздуха',
    owner: null,
    responsible: 'Абдуллаева Н.',
    days: 18,
    actions: ['impediment_confirm', 'impediment_clear', 'note'],
  },
  {
    id: 'r-mission',
    reason: 'impediment_stale',
    target: { kind: 'project', id: 'mission' },
    title: 'Спутниковая миссия «Навоий-2»',
    owner: null,
    responsible: 'Каримов А.',
    days: 25,
    actions: ['impediment_confirm', 'impediment_clear', 'note'],
  },
  {
    id: 'r-calibration',
    reason: 'impediment_stale',
    target: { kind: 'project', id: 'calibration' },
    title: 'Пилот: калибровка снимков',
    owner: null,
    responsible: 'Каримов А.',
    days: 40,
    actions: ['impediment_confirm', 'impediment_clear', 'note'],
  },
  // Свежие записи «что мешает»: в обходе их нет, пока порог не опустят ниже их давности.
  {
    id: 'r-portal-note',
    reason: 'impediment_stale',
    target: { kind: 'project', id: 'portal' },
    title: 'Геопортал агентства',
    owner: null,
    responsible: 'Турсунов Б.',
    days: 9,
    actions: ['impediment_confirm', 'impediment_clear', 'note'],
  },
  {
    id: 'r-drought-note',
    reason: 'impediment_stale',
    target: { kind: 'project', id: 'drought' },
    title: 'Цикл мониторинга: засуха-2026',
    owner: null,
    responsible: 'Рахимов Ш.',
    days: 12,
    actions: ['impediment_confirm', 'impediment_clear', 'note'],
  },
  {
    id: 'r-aerial',
    reason: 'project_silent',
    target: { kind: 'project', id: 'aerial' },
    title: 'Заказ услуги: аэрофотосъёмка Ферганской долины',
    owner: null,
    responsible: 'Турсунов Б.',
    days: 21,
    actions: ['note', 'project_done', 'hold'],
  },
  {
    id: 'r-lab',
    reason: 'project_silent',
    target: { kind: 'project', id: 'lab' },
    title: 'Учебная лаборатория ДЗЗ в вузе',
    owner: null,
    responsible: 'Юсупова Д.',
    days: 30,
    actions: ['note', 'project_done', 'hold'],
  },
  {
    id: 'r-letter',
    reason: 'task_unassigned',
    target: { kind: 'task', id: 'crops-letter' },
    title: 'Проект письма в Минсельхоз об итогах пилота',
    owner: 'Пилот: мониторинг посевов',
    responsible: null,
    days: 6,
    actions: ['assign', 'task_cancel'],
  },
];

/**
 * Из чего складывается «сколько строк сделает сигналом» каждый порог — вымышленные
 * расстояния в днях и счёты, подобранные так, чтобы при значениях по умолчанию ответ
 * совпал с Пультом вымышленной базы (горит 11, молчит 9). На сервере это посчитает
 * `services/metrics.py` тем же кодом, что Пульт, и ничего не запишет.
 */
const BURN = [0, 0, 1, 2, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10, 10, 12, 14, 15, 20, 21, 25, 30];
const QUIET = [2, 4, 6, 9, 15, 16, 17, 18, 20, 21, 25, 30, 34];
const CLOSED = [3, 7, 9, 12, 15, 22, 31];
/**
 * Дни впереди: через сколько дней и сколько в этот день незакрытых сроков. Оба порога
 * горячих дней считают по одному списку — у «горячего дня» и у «окна» одно число: горячие
 * дни в окне (`hot_ahead` в `services/calendar.py`).
 */
const AHEAD: [inDays: number, deadlines: number][] = [
  [0, 3],
  [2, 1],
  [5, 2],
  [10, 4],
  [14, 2],
  [20, 3],
  [26, 2],
  [33, 5],
  [45, 3],
  [61, 4],
];

const THRESHOLDS: Omit<Threshold, 'affected' | 'version'>[] = [
  { key: 'burn_days', value: 7, default: 7, origin: 'tz', kind: 'days', min: 1, max: 60 },
  { key: 'quiet_days', value: 14, default: 14, origin: 'tz', kind: 'days', min: 1, max: 180 },
  {
    key: 'impediment_stale_days',
    value: 14,
    default: 14,
    origin: 'assumption',
    kind: 'days',
    min: 1,
    max: 180,
  },
  {
    key: 'min_closed_for_pace',
    value: 10,
    default: 10,
    origin: 'tz',
    kind: 'count',
    min: 1,
    max: 100,
  },
  {
    key: 'hot_day_threshold',
    value: 3,
    default: 3,
    origin: 'assumption',
    kind: 'count',
    min: 2,
    max: 20,
  },
  {
    key: 'hot_window_days',
    value: 28,
    default: 28,
    origin: 'assumption',
    kind: 'days',
    min: 7,
    max: 90,
  },
  {
    key: 'summary_at',
    value: '08:30',
    default: '08:30',
    origin: 'tz',
    kind: 'time',
    min: null,
    max: null,
  },
];

type Named = [code: string, name: string, used: number];

const SEEDED: Record<Exclude<DictionaryKind, 'organizations'>, Named[]> = {
  project_types: [
    ['monitoring_cycle', 'Цикл мониторинга', 4],
    ['regulation', 'Нормативный акт', 3],
    ['standard', 'Стандарт', 2],
    ['platform', 'Платформа или ИТ', 3],
    ['satellite_mission', 'Спутниковая миссия', 2],
    ['industry_pilot', 'Пилот с отраслью', 4],
    ['service_order', 'Заказ услуги', 2],
    ['international', 'Международное сотрудничество', 4],
    ['staff_education', 'Кадры и образование', 3],
    ['higher_authority_order', 'Заказ вышестоящего органа', 4],
  ],
  task_types: [
    ['technical_spec', 'Техническое задание', 6],
    ['review_and_endorse', 'Рассмотрение и визирование', 9],
    ['approval', 'Согласование', 7],
    ['cabinet_submission', 'Внесение в Кабмин', 4],
    ['analytical_note', 'Аналитическая информация', 11],
    ['site_visit', 'Выезд на место', 5],
    ['request_or_survey', 'Запрос или опросник', 3],
    ['subplatform_upload', 'Выгрузка в субплатформу', 4],
    ['participant_selection', 'Отбор участников', 2],
    ['ijro_report', 'Подготовка сведений по Ижро', 8],
    ['other', 'Прочее', 60],
  ],
  directions: [
    ['space_monitoring', 'Космический мониторинг', 9],
    ['remote_sensing', 'Дистанционное зондирование Земли', 7],
    ['international', 'Международное сотрудничество', 5],
    ['infrastructure', 'Инфраструктура и техническое развитие', 4],
    ['regulatory', 'Нормативно-регуляторная работа', 4],
    ['internal', 'Внутренние организационные инициативы', 2],
  ],
  regions: [
    ['karakalpakstan', 'Республика Каракалпакстан', 1],
    ['andijan', 'Андижанская область', 0],
    ['bukhara', 'Бухарская область', 1],
    ['jizzakh', 'Джизакская область', 2],
    ['kashkadarya', 'Кашкадарьинская область', 0],
    ['navoi', 'Навоийская область', 1],
    ['namangan', 'Наманганская область', 0],
    ['samarkand', 'Самаркандская область', 3],
    ['surkhandarya', 'Сурхандарьинская область', 0],
    ['syrdarya', 'Сырдарьинская область', 1],
    ['tashkent_region', 'Ташкентская область', 2],
    ['fergana', 'Ферганская область', 2],
    ['khorezm', 'Хорезмская область', 0],
    ['tashkent_city', 'город Ташкент', 4],
  ],
  project_statuses: [
    ['in_progress', 'В работе', 26],
    ['on_hold', 'На паузе', 1],
    ['done', 'Завершён', 3],
    ['cancelled', 'Отменён', 1],
  ],
  task_statuses: [
    ['new', 'Новая', 9],
    ['in_progress', 'В работе', 62],
    ['in_review', 'На проверке', 4],
    ['done', 'Готова', 41],
    ['cancelled', 'Отменена', 3],
  ],
};

const ORGANIZATIONS: [name: string, kind: OrganizationKind, used: number, center?: boolean][] = [
  ['Центр космического мониторинга', 'company', 9, true],
  ['Министерство экологии', 'ministry', 6],
  ['Министерство сельского хозяйства', 'ministry', 3],
  ['Агентство по гидрометеорологии', 'agency', 2],
  ['Хокимият Самаркандской области', 'khokimiyat', 1],
  ['Международный партнёр по программе воздуха', 'international', 1],
];

const TEMPLATES: Record<string, [name: string, offset: number][]> = {
  monitoring_cycle: [
    ['Получение космических снимков', 30],
    ['Обработка и анализ данных', 60],
    ['Отчёт по результатам мониторинга', 90],
  ],
  regulation: [
    ['Разработка проекта акта', 30],
    ['Согласование с министерствами и ведомствами', 60],
    ['Внесение в Кабинет Министров', 90],
    ['Принятие', 120],
  ],
  standard: [
    ['Разработка проекта стандарта', 60],
    ['Обсуждение и согласование', 120],
    ['Утверждение и регистрация', 180],
  ],
  platform: [
    ['Техническое задание', 30],
    ['Разработка', 120],
    ['Опытная эксплуатация', 150],
    ['Ввод в эксплуатацию', 180],
  ],
  satellite_mission: [
    ['Концепция и техническое задание', 90],
    ['Договор с изготовителем', 180],
    ['Запуск', 720],
    ['Ввод в эксплуатацию', 810],
  ],
  industry_pilot: [
    ['Соглашение с отраслью', 30],
    ['Проведение пилота', 120],
    ['Отчёт и предложения по масштабированию', 150],
  ],
  service_order: [
    ['Заявка и техническое задание', 14],
    ['Договор', 30],
    ['Оказание услуги', 75],
    ['Акт приёмки', 90],
  ],
  international: [
    ['Переговоры и проект документа', 60],
    ['Внутригосударственное согласование', 120],
    ['Подписание', 150],
  ],
  staff_education: [
    ['Программа и отбор участников', 30],
    ['Обучение', 120],
    ['Итоги и отчёт', 150],
  ],
  higher_authority_order: [
    ['План исполнения', 7],
    ['Исполнение', 45],
    ['Доклад об исполнении', 60],
  ],
};

/** Набор статусов задан графом переходов, регионы — ТЗ 3.1; остальное дополняется. */
const CAN_ADD: ReadonlySet<DictionaryKind> = new Set([
  'project_types',
  'task_types',
  'directions',
  'organizations',
]);

function fail(message: string): never {
  throw new Error(message);
}

/** Пункт обхода стоит в очереди при текущих порогах — строгое сравнение, как на сервере. */
function inRound(item: Omit<RoundItem, 'record'>, quiet: number, stale: number): boolean {
  if (item.reason === 'project_silent' || item.reason === 'task_review') return item.days > quiet;
  if (item.reason === 'impediment_stale') return item.days > stale;
  return true;
}

function stale(version: number, expected: number): void {
  if (version !== expected) fail('Значение уже изменили: обновите страницу');
}

export class FakeManagement {
  private items: Omit<RoundItem, 'record'>[] = [];
  private done = 0;
  private thresholds: Threshold[] = [];
  private groups: DictionaryGroup[] = [];
  private templates: Record<string, TemplateStep[]> = {};
  private counter = 0;

  constructor(private readonly now: () => Date = () => new Date()) {
    this.reset();
  }

  reset(): void {
    this.items = ROUND.map((item) => ({ ...item }));
    this.done = 3;
    this.thresholds = THRESHOLDS.map((each) => ({ ...each, affected: null, version: 1 }));
    this.recount();
    const entry = ([code, name, used]: Named): DictionaryEntry => ({
      id: code,
      name,
      is_active: true,
      used,
      version: 1,
    });
    this.groups = [
      ...(Object.keys(SEEDED) as (keyof typeof SEEDED)[]).map((kind) => ({
        kind,
        entries: SEEDED[kind].map(entry),
        can_add: CAN_ADD.has(kind),
        can_disable: kind !== 'project_statuses' && kind !== 'task_statuses',
        can_move: true,
      })),
      {
        kind: 'organizations' as const,
        entries: ORGANIZATIONS.map(([name, kind, used, center], index) => ({
          id: `org-${index}`,
          name,
          is_active: true,
          used,
          version: 1,
          org_kind: kind,
          is_center: center === true,
        })),
        can_add: true,
        can_disable: true,
        can_move: false,
      },
    ];
    this.templates = Object.fromEntries(
      Object.entries(TEMPLATES).map(([type, steps]) => [
        type,
        steps.map(([name, offset], index) => ({
          id: `${type}-${index}`,
          name,
          offset_days: offset,
          version: 1,
        })),
      ]),
    );
    this.counter = 0;
  }

  private value(key: ThresholdKey): number {
    return Number(this.thresholds.find((each) => each.key === key)?.value);
  }

  /** Числа всех порогов — после любой записи: горячие дни зависят друг от друга. */
  private recount(): void {
    this.thresholds = this.thresholds.map((each) => ({
      ...each,
      affected: this.impact(each.key, each.value),
    }));
  }

  view(): ManagementView {
    const now = this.now();
    const [from, to] = week(now);
    const quiet = this.value('quiet_days');
    const staleDays = this.value('impediment_stale_days');
    return {
      as_of: now.toISOString(),
      round: {
        week_from: from,
        week_to: to,
        items: this.items
          .filter((item) => inRound(item, quiet, staleDays))
          .map((item) => ({
            ...item,
            record: { kind: RECORD[item.reason], id: item.id, version: 1 },
          })),
        done: this.done,
      },
      thresholds: this.thresholds.map((each) => ({ ...each })),
      dictionaries: this.groups.map((group) => ({
        ...group,
        entries: group.entries.map((each) => ({ ...each })),
      })),
      templates: Object.fromEntries(
        Object.entries(this.templates).map(([type, steps]) => [
          type,
          [...steps].sort((a, b) => a.offset_days - b.offset_days).map((each) => ({ ...each })),
        ]),
      ),
      people: PEOPLE,
      links: [
        {
          role: 'assistant',
          issued_at: `${dayIn(now, -17)}T09:12:00+05:00`,
          last_login_at: `${dayIn(now, 0)}T08:40:00+05:00`,
        },
        {
          role: 'leader',
          issued_at: `${dayIn(now, -17)}T09:20:00+05:00`,
          last_login_at: `${dayIn(now, -1)}T21:15:00+05:00`,
        },
      ],
      is_demo: true,
    };
  }

  /** Действие обхода: данные меняются, пункт уходит, неделя засчитывает его. */
  act(id: string, action: RoundAction, input?: string): void {
    const item = this.items.find((each) => each.id === id) ?? fail('Пункта обхода уже нет');
    if (!item.actions.includes(action)) fail('У этого пункта нет такого действия');
    if ((action === 'note' || action === 'hold') && !input?.trim()) {
      fail(action === 'note' ? 'Напишите, что мешает' : 'Напишите причину паузы');
    }
    if (action === 'assign' && !PEOPLE.some((person) => person.id === input)) {
      fail('Выберите ответственного');
    }
    this.items = this.items.filter((each) => each.id !== id);
    this.done += 1;
    this.recount();
  }

  /** Сколько строк сделает сигналом порог с этим значением. Ничего не пишет. */
  impact(key: ThresholdKey, raw: number | string): number | null {
    const value = Number(raw);
    switch (key) {
      case 'summary_at':
        return null;
      // Горит, если до срока не больше порога.
      case 'burn_days':
        return BURN.filter((days) => days <= value).length;
      // Молчит, если без движения дольше порога.
      case 'quiet_days':
        return QUIET.filter((days) => days > value).length;
      // Устарело, если старше порога, — те же записи, что стоят в обходе.
      case 'impediment_stale_days':
        return this.items.filter((item) => item.reason === 'impediment_stale' && item.days > value)
          .length;
      // «Мало данных», если закрыто меньше порога.
      case 'min_closed_for_pace':
        return CLOSED.filter((closed) => closed < value).length;
      case 'hot_day_threshold':
        return AHEAD.filter(
          ([inDays, deadlines]) => deadlines >= value && inDays < this.value('hot_window_days'),
        ).length;
      case 'hot_window_days':
        return AHEAD.filter(
          ([inDays, deadlines]) => inDays < value && deadlines >= this.value('hot_day_threshold'),
        ).length;
    }
  }

  setThreshold(key: ThresholdKey, value: number | string, version: number): Threshold {
    const current = this.thresholds.find((each) => each.key === key) ?? fail('Нет такого порога');
    if (current.version !== version) {
      fail(
        `Порог изменили, пока вы его правили: сейчас ${String(current.value)}. Проверьте и сохраните снова`,
      );
    }
    if (current.kind === 'time') {
      if (typeof value !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) {
        fail('Время — часы и минуты, например 08:30');
      }
    } else if (
      typeof value !== 'number' ||
      !Number.isInteger(value) ||
      value < (current.min ?? 0) ||
      value > (current.max ?? Infinity)
    ) {
      fail(`Порог — целое число от ${current.min} до ${current.max}`);
    }
    this.thresholds = this.thresholds.map((each) =>
      each.key === key ? { ...each, value, version: version + 1 } : each,
    );
    this.recount();
    return this.thresholds.find((each) => each.key === key)!;
  }

  private group(kind: DictionaryKind): DictionaryGroup {
    return this.groups.find((each) => each.kind === kind) ?? fail('Нет такого справочника');
  }

  private entry(kind: DictionaryKind, id: string): DictionaryEntry {
    return this.group(kind).entries.find((each) => each.id === id) ?? fail('Значения уже нет');
  }

  rename(
    kind: DictionaryKind,
    id: string,
    name: string,
    version: number,
    orgKind?: OrganizationKind,
  ): void {
    const value = name.trim();
    if (!value) fail('Напишите название');
    const group = this.group(kind);
    if (group.entries.some((each) => each.id !== id && each.name === value)) {
      fail('Такое название уже есть');
    }
    const entry = this.entry(kind, id);
    stale(version, entry.version);
    entry.name = value;
    if (kind === 'organizations' && orgKind) entry.org_kind = orgKind;
    entry.version += 1;
  }

  toggle(kind: DictionaryKind, id: string, version: number): void {
    if (!this.group(kind).can_disable) fail('Статус выключить нельзя: на нём правила переходов');
    const entry = this.entry(kind, id);
    stale(version, entry.version);
    entry.is_active = !entry.is_active;
    entry.version += 1;
  }

  /** Порядок в формах. Версию поднимают обе переставленные записи: это правка обеих. */
  move(kind: DictionaryKind, id: string, step: -1 | 1, version: number): void {
    const entries = this.group(kind).entries;
    const from = entries.findIndex((each) => each.id === id);
    const to = from + step;
    if (from < 0 || to < 0 || to >= entries.length) return;
    stale(version, entries[from]!.version);
    [entries[from], entries[to]] = [entries[to]!, entries[from]!];
    entries[from]!.version += 1;
    entries[to]!.version += 1;
  }

  add(kind: DictionaryKind, name: string, orgKind?: OrganizationKind): DictionaryEntry {
    const group = this.group(kind);
    if (!group.can_add) fail('В этот справочник значения не добавляются');
    const value = name.trim();
    if (!value) fail('Напишите название');
    if (group.entries.some((each) => each.name === value)) fail('Такое название уже есть');
    this.counter += 1;
    const created: DictionaryEntry = {
      id: `${kind}-new-${this.counter}`,
      name: value,
      is_active: true,
      used: 0,
      version: 1,
      ...(kind === 'organizations' ? { org_kind: orgKind ?? 'ministry', is_center: false } : {}),
    };
    group.entries.push(created);
    if (kind === 'project_types') this.templates[created.id] = [];
    return created;
  }

  saveStep(
    type: string,
    step: { id?: string; name: string; offset_days: number; version?: number },
  ): void {
    const steps = this.templates[type] ?? fail('Нет такого типа проекта');
    const name = step.name.trim();
    if (!name) fail('Напишите название вехи');
    if (!Number.isInteger(step.offset_days) || step.offset_days < 0 || step.offset_days > 3650) {
      fail('Через сколько дней — целое число от 0 до 3650');
    }
    if (step.id) {
      const found = steps.find((each) => each.id === step.id) ?? fail('Вехи уже нет');
      stale(step.version ?? 0, found.version);
      found.name = name;
      found.offset_days = step.offset_days;
      found.version += 1;
      return;
    }
    this.counter += 1;
    steps.push({
      id: `${type}-new-${this.counter}`,
      name,
      offset_days: step.offset_days,
      version: 1,
    });
  }

  removeStep(type: string, id: string, version: number): void {
    const steps = this.templates[type] ?? fail('Нет такого типа проекта');
    const found = steps.find((each) => each.id === id) ?? fail('Вехи уже нет');
    stale(version, found.version);
    this.templates[type] = steps.filter((each) => each.id !== id);
  }
}

type Reply = [status: number, body: unknown];

function problem(error: unknown): Reply {
  const detail = error instanceof Error ? error.message : String(error);
  const stale = detail.includes('изменили');
  return [stale ? 409 : 422, { detail, status: stale ? 409 : 422 }];
}

/**
 * Запрос экрана — ответ сервера. `path` — как его строит клиент API, со строкой запроса.
 */
export function handle(
  server: FakeManagement,
  method: string,
  path: string,
  body: Record<string, unknown> | undefined,
): Reply | null {
  const [bare = path, search = ''] = path.split('?');
  if (!bare.startsWith('/api/v1/management')) return null;
  const rest = bare.slice('/api/v1/management'.length).split('/').filter(Boolean);
  const input = body ?? {};
  try {
    if (method === 'GET' && rest.length === 0) return [200, server.view()];
    if (method === 'POST' && rest[0] === 'round') {
      server.act(String(input.record_id), input.action as RoundAction, input.input as string);
      return [204, undefined];
    }
    if (rest[0] === 'thresholds') {
      const key = rest[1] as ThresholdKey;
      if (method === 'GET' && rest[2] === 'preview') {
        const raw = new URLSearchParams(search).get('value') ?? '';
        const value = /^\d+$/.test(raw) ? Number(raw) : raw;
        return [200, { affected: server.impact(key, value) }];
      }
      server.setThreshold(key, input.value as number | string, Number(input.version));
      return [204, undefined];
    }
    if (rest[0] === 'dictionaries') {
      const kind = rest[1] as DictionaryKind;
      if (method === 'POST' && rest.length === 2) {
        return [
          201,
          { id: server.add(kind, String(input.name), input.org_kind as OrganizationKind).id },
        ];
      }
      const id = String(rest[2]);
      if (method === 'PUT') {
        server.rename(
          kind,
          id,
          String(input.name),
          Number(input.version),
          input.org_kind as OrganizationKind | undefined,
        );
      } else if (rest[3] === 'toggle') {
        server.toggle(kind, id, Number(input.version));
      } else if (rest[3] === 'move') {
        server.move(kind, id, input.step as -1 | 1, Number(input.version));
      }
      return [204, undefined];
    }
    if (rest[0] === 'templates') {
      const type = String(rest[1]);
      const step = rest[3];
      if (method === 'POST') {
        server.saveStep(type, { name: String(input.name), offset_days: Number(input.offset_days) });
        return [201, { id: 'new' }];
      }
      if (method === 'PUT' && step) {
        server.saveStep(type, {
          id: step,
          name: String(input.name),
          offset_days: Number(input.offset_days),
          version: Number(input.version),
        });
        return [204, undefined];
      }
      if (method === 'DELETE' && step) {
        server.removeStep(type, step, Number(new URLSearchParams(search).get('version')));
        return [204, undefined];
      }
    }
    return [404, { detail: `нет пути ${method} ${path}` }];
  } catch (error) {
    return problem(error);
  }
}

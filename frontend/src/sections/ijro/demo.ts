/**
 * Вымышленный сервер раздела «Ижро» — пока экран не утверждён и API нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит, потом API под
 * утверждённый экран (CLAUDE.md, цикл блока). Изменённое во вкладке живёт до перезагрузки.
 * После утверждения файл становится сервером тестов, а данные переезжают в `app/demo.py`.
 *
 * **Одни данные — все числа.** Виджеты, списки, стена и карточка считаются из одного набора
 * записей одними функциями: ответ вопроса и его список — одно вычисление (ТЗ 5, инвариант 2).
 * Настоящий сервер считает то же в `services/metrics.py`; экран только показывает.
 *
 * **Лестница** — порядок проверок сервера (`domain/attention.attention_of`): ждёт решения →
 * просрочено → горит (только срок с известным днём, V33) → зависит от чужих (мы соисполнитель
 * и тишина дольше порога) → молчит → по плану. Сданное и снятое с контроля в лестницу не
 * входит (V32). Признак жизни — самое свежее из контрольной отметки, движения связанной
 * задачи и промежуточной информации (ТЗ 4).
 *
 * Сроки заданы от сегодняшнего дня по Ташкенту, чтобы лестница была живой в любой день.
 * Содержание поручений — узбекская кириллица, как в таблицах источника: это данные.
 */

import type { DecisionKind, Step } from '@/sections/pult/model';
import type { TaskStatus } from '@/sections/tasks/model';
import type { Role } from '@/shared/api/orbita';
import { AGENCY_TIMEZONE } from '@/shared/time';

import {
  CHANGE_CLASSES,
  OPEN_STAGES,
  QUESTIONS,
  type ApplyChoices,
  type ApplyResult,
  type AssignmentCard,
  type AssignmentRow,
  type Batch,
  type ChangeClass,
  type Comment,
  type ControlMark,
  type DuePrecision,
  type Extension,
  type ExtensionKind,
  type IjroDocument,
  type IjroSource,
  type IjroView,
  type LifeSource,
  type LinkedTask,
  type MarkKind,
  type Organization,
  type Person,
  type Preview,
  type PreviewRow,
  type QuestionAnswer,
  type QuestionKey,
  type SpravkaLine,
  type Stage,
  type TaskPrefill,
  type Thresholds,
  type UploadInput,
  type WallDocument,
} from './model';

const DAY_MS = 86_400_000;

/** Пороги со значениями ТЗ 4; на сервере — справочник порогов (`metrics.load_thresholds`). */
const THRESHOLDS: Thresholds = {
  burn_days: 7,
  quiet_days: 14,
  near_due_days: 30,
  pace_window_days: 90,
  min_closed_for_pace: 5,
};

/** V34: задача — за три рабочих дня до срока поручения. */
const WORKDAYS_BEFORE = 3;

const RANK: Record<Step, number> = {
  awaiting_decision: 0,
  overdue: 1,
  burning: 2,
  blocked_by_others: 3,
  silent: 4,
};

function dayOf(moment: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(moment);
}

function shift(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

/** Сколько дней от `from` до `to`. */
function between(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

function moment(day: string): string {
  return `${day}T10:00:00+05:00`;
}

/** Дата за `count` рабочих дней до `day`: суббота и воскресенье не в счёт. */
function workdaysBefore(day: string, count: number): string {
  let left = count;
  let current = day;
  while (left > 0) {
    current = shift(current, -1);
    const weekday = new Date(`${current}T00:00:00Z`).getUTCDay();
    if (weekday !== 0 && weekday !== 6) left -= 1;
  }
  return current;
}

const PEOPLE: Person[] = [
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-abdullaev', name: 'Абдуллаев Н.' },
];

const ORGANIZATIONS: Organization[] = [
  {
    id: 'o-eco',
    name: 'Министерство экологии, охраны окружающей среды и изменения климата',
    short_name: 'Минэкологии',
  },
  { id: 'o-trans', name: 'Министерство транспорта', short_name: 'Минтранс' },
  { id: 'o-digital', name: 'Министерство цифровых технологий', short_name: 'Минцифры' },
];

interface DocumentSpec {
  id: string;
  kind: IjroDocument['kind'];
  code: string;
  issued: number;
  title: string;
  source: IjroSource;
}

const DOCUMENTS: DocumentSpec[] = [
  {
    id: 'd-pf155',
    kind: 'farmon',
    code: 'ПФ-155',
    issued: -210,
    title: 'Космик фаолиятни ривожлантириш стратегиясини амалга ошириш чора-тадбирлари тўғрисида',
    source: 'pa',
  },
  {
    id: 'd-pq312',
    kind: 'qaror',
    code: 'ПҚ-312',
    issued: -150,
    title:
      'Ерни масофадан зондлаш маълумотларидан фойдаланиш самарадорлигини ошириш чора-тадбирлари тўғрисида',
    source: 'pa',
  },
  {
    id: 'd-vmq512',
    kind: 'qaror',
    code: 'ВМҚ-512',
    issued: -95,
    title: 'Сунъий йўлдош алоқаси инфратузилмасини ривожлантириш дастурини тасдиқлаш ҳақида',
    source: 'vm',
  },
  {
    id: 'd-orq897',
    kind: 'qonun',
    code: 'ЎРҚ-897',
    issued: -120,
    title: '«Космик фаолият тўғрисида»ги Қонун ижросини таъминлаш бўйича чора-тадбирлар режаси',
    source: 'legal',
  },
];

type DueSpec = number | 'year_end' | 'month_end' | null;

interface Spec {
  id: string;
  doc: string;
  band: string;
  content: string;
  mechanism?: string;
  due: DueSpec;
  /** Продления: сроки «было → стало» и день таблицы — в днях от сегодня. */
  history?: { from: number; to: number; on: number; kind: ExtensionKind }[];
  raw: string;
  person: string | null;
  lead?: string;
  stage: Stage;
  /** Когда сменился этап и когда строка появилась в реестре — в днях от сегодня. */
  staged: number;
  seen: number;
  marks?: { kind: MarkKind; at: number; promised?: number; comment?: string; author: Role }[];
  tasks?: { code: string; title: string; status: TaskStatus; moved: number; due: number | null }[];
  /** Промежуточная информация сдана — в днях от сегодня. */
  interim?: number;
  problem?: { text: string; proposal: string; on: number };
  question?: { text: string; asked: number };
  requested?: boolean;
  batch: string;
}

const SPECS: Spec[] = [
  {
    id: 'a01',
    doc: 'd-pf155',
    band: '3-банд',
    content:
      'Космик технологиялар соҳасида кадрлар тайёрлаш ва малакасини ошириш дастури ишлаб чиқилсин ҳамда Вазирлар Маҳкамасига киритилсин.',
    mechanism: 'Дастур лойиҳаси манфаатдор вазирликлар билан келишилади.',
    due: -12,
    raw: 'А.Каримов',
    person: 'p-karimov',
    stage: 'in_progress',
    staged: -60,
    seen: -120,
    marks: [{ kind: 'no_answer', at: -9, author: 'assistant' }],
    tasks: [
      {
        code: 'TSK-2026-0118',
        title: 'Проект программы подготовки кадров',
        status: 'in_progress',
        moved: -10,
        due: -14,
      },
    ],
    problem: {
      text: 'Олий таълим вазирлиги квоталар бўйича таклифларини тақдим этмади.',
      proposal: 'Вазирликка қўшимча хат юбориш ва муддатни 25 октябргача узайтириш.',
      on: -6,
    },
    batch: 'b1',
  },
  {
    id: 'a02',
    doc: 'd-pf155',
    band: '5.1-банд',
    content:
      'Миллий космик дастур лойиҳаси бўйича жамоатчилик муҳокамаси ўтказилсин ва якунлари умумлаштирилсин.',
    due: -5,
    raw: 'Юсупова Д.',
    person: 'p-yusupova',
    stage: 'not_started',
    staged: -120,
    seen: -120,
    marks: [{ kind: 'no_answer', at: -33, author: 'assistant' }],
    batch: 'b1',
  },
  {
    id: 'a03',
    doc: 'd-pq312',
    band: '2-банд',
    content:
      'Сув ҳавзалари ҳолатини космик мониторинг қилиш тартиби тўғрисидаги низом лойиҳаси ишлаб чиқилсин.',
    mechanism: 'Низом лойиҳаси Экология вазирлиги билан биргаликда тайёрланади.',
    due: -2,
    raw: 'Турсунов Б.Б.',
    person: 'p-tursunov',
    lead: 'o-eco',
    stage: 'in_progress',
    staged: -40,
    seen: -120,
    marks: [{ kind: 'contacted', at: -20, author: 'assistant' }],
    batch: 'b1',
  },
  {
    id: 'a04',
    doc: 'd-pf155',
    band: '7-банд',
    content:
      'Ерни масофадан зондлаш маълумотларининг ягона геопортали ишга туширилсин ва давлат органларига уланиш таъминлансин.',
    due: 2,
    raw: 'Каримов А.А.',
    person: 'p-karimov',
    stage: 'in_progress',
    staged: -30,
    seen: -120,
    marks: [
      {
        kind: 'doing',
        at: -1,
        promised: 1,
        comment: 'Тест синовлари якунланмоқда',
        author: 'leader',
      },
    ],
    tasks: [
      {
        code: 'TSK-2026-0131',
        title: 'Подключение ведомств к геопорталу',
        status: 'in_progress',
        moved: -1,
        due: 1,
      },
      {
        code: 'TSK-2026-0132',
        title: 'Акт ввода геопортала',
        status: 'new',
        moved: -6,
        due: 2,
      },
    ],
    batch: 'b1',
  },
  {
    id: 'a05',
    doc: 'd-pq312',
    band: '4-банд',
    content:
      'Қишлоқ хўжалиги экинлари майдонларини космик суратлар асосида ҳисобга олиш бўйича услубий қўлланма тасдиқлансин.',
    due: 4,
    raw: 'Юсупова Д.',
    person: 'p-yusupova',
    stage: 'in_progress',
    staged: -35,
    seen: -120,
    marks: [{ kind: 'doing', at: -18, author: 'assistant' }],
    batch: 'b1',
  },
  {
    id: 'a06',
    doc: 'd-vmq512',
    band: '12-банд',
    content:
      'Сунъий йўлдош алоқаси ер усти станцияларини жойлаштириш схемаси қайта ишлансин ва киритилсин.',
    due: 6,
    raw: 'Рахимов Ш.',
    person: 'p-rakhimov',
    stage: 'returned',
    staged: -4,
    seen: -45,
    marks: [{ kind: 'doing', at: -3, author: 'assistant' }],
    tasks: [
      {
        code: 'TSK-2026-0140',
        title: 'Доработка схемы размещения станций',
        status: 'in_progress',
        moved: -3,
        due: 4,
      },
    ],
    batch: 'b2',
  },
  {
    id: 'a07',
    doc: 'd-vmq512',
    band: '1-илова 3-банд',
    content:
      'Алоқа операторлари билан сунъий йўлдош каналларидан фойдаланиш бўйича ҳамкорлик меморандуми имзолансин.',
    due: 7,
    raw: 'Н.Абдуллаев',
    person: null,
    stage: 'not_started',
    staged: -30,
    seen: -30,
    batch: 'b2',
  },
  {
    id: 'a08',
    doc: 'd-pq312',
    band: '6-банд',
    content: 'Космик мониторинг маълумотлари асосида яйловлар деградацияси харитаси тайёрлансин.',
    due: 10,
    raw: 'Юсупова Д.',
    person: 'p-yusupova',
    stage: 'in_progress',
    staged: -25,
    seen: -120,
    marks: [{ kind: 'doing', at: -7, author: 'assistant' }],
    question: { text: 'Поддержать продление срока до 25 ноября?', asked: -6 },
    requested: true,
    batch: 'b1',
  },
  {
    id: 'a09',
    doc: 'd-vmq512',
    band: '5-банд',
    content: 'Дастурни амалга ошириш бўйича идоралараро ишчи гуруҳ таркиби тасдиқлансин.',
    due: 20,
    raw: 'Каримов А.',
    person: 'p-karimov',
    stage: 'in_progress',
    staged: -12,
    seen: -45,
    marks: [{ kind: 'contacted', at: -3, author: 'assistant' }],
    question: { text: 'Утвердить состав рабочей группы?', asked: -2 },
    batch: 'b2',
  },
  {
    id: 'a10',
    doc: 'd-vmq512',
    band: '8-банд',
    content:
      'Транспорт йўлакларида навигация хизматларини ривожлантириш бўйича «йўл харитаси» ишлаб чиқилсин.',
    due: 25,
    raw: 'Турсунов Б.',
    person: 'p-tursunov',
    lead: 'o-trans',
    stage: 'in_progress',
    staged: -40,
    seen: -45,
    marks: [{ kind: 'contacted', at: -22, author: 'assistant' }],
    batch: 'b2',
  },
  {
    id: 'a11',
    doc: 'd-pq312',
    band: '11-банд',
    content:
      'Ўрмон фонди ерларини космик мониторинг қилиш натижалари ҳар чоракда Вазирлар Маҳкамасига киритиб борилсин.',
    due: 40,
    raw: 'Рахимов Ш.',
    person: 'p-rakhimov',
    lead: 'o-eco',
    stage: 'not_started',
    staged: -35,
    seen: -35,
    batch: 'b1',
  },
  {
    id: 'a12',
    doc: 'd-orq897',
    band: '14-модда',
    content:
      'Космик фаолият субъектларининг ягона электрон реестри яратилсин ва юритилиши таъминлансин.',
    due: 'month_end',
    raw: 'Абдуллаев Н.',
    person: 'p-abdullaev',
    lead: 'o-digital',
    stage: 'in_progress',
    staged: -50,
    seen: -120,
    marks: [{ kind: 'contacted', at: -16, author: 'assistant' }],
    batch: 'b1',
  },
  {
    id: 'a13',
    doc: 'd-pf155',
    band: '9-банд',
    content:
      'Космик мониторинг марказининг моддий-техника базасини мустаҳкамлаш бўйича таклифлар киритилсин.',
    due: 18,
    raw: 'Турсунов Б.',
    person: 'p-tursunov',
    stage: 'in_progress',
    staged: -60,
    seen: -120,
    marks: [{ kind: 'doing', at: -25, author: 'assistant' }],
    batch: 'b1',
  },
  {
    id: 'a14',
    doc: 'd-pf155',
    band: '10-банд',
    content: 'Хорижий космик агентликлар билан ҳамкорлик дастурлари рўйхати шакллантирилсин.',
    due: 45,
    raw: 'Рахимов Ш.',
    person: 'p-rakhimov',
    stage: 'not_started',
    staged: -40,
    seen: -40,
    batch: 'b1',
  },
  {
    id: 'a15',
    doc: 'd-orq897',
    band: '6-модда',
    content: 'Космик фаолиятни лицензиялаш тартиби тўғрисидаги низом лойиҳаси ишлаб чиқилсин.',
    due: 'year_end',
    history: [
      { from: -90, to: -30, on: -100, kind: 'extension' },
      { from: -30, to: 0, on: -45, kind: 'extension' },
    ],
    raw: 'Юсупова Д.',
    person: 'p-yusupova',
    stage: 'in_progress',
    staged: -70,
    seen: -120,
    tasks: [
      {
        code: 'TSK-2026-0097',
        title: 'Положение о лицензировании — черновик',
        status: 'in_review',
        moved: -19,
        due: null,
      },
    ],
    batch: 'b1',
  },
  {
    id: 'a16',
    doc: 'd-vmq512',
    band: '9-банд',
    content:
      'Чекка ҳудудларни сунъий йўлдош интернети билан қамраб олиш бўйича пилот лойиҳа амалга оширилсин.',
    due: 28,
    raw: 'Каримов А.',
    person: 'p-karimov',
    stage: 'in_progress',
    staged: -40,
    seen: -45,
    interim: -17,
    batch: 'b2',
  },
  {
    id: 'a17',
    doc: 'd-pq312',
    band: '8-банд',
    content: 'Космик суратлар архивини рақамлаштириш ва сақлаш тизими жорий этилсин.',
    due: 'year_end',
    raw: 'Турсунов Б.',
    person: 'p-tursunov',
    stage: 'not_started',
    staged: -21,
    seen: -21,
    batch: 'b1',
  },
  {
    id: 'a18',
    doc: 'd-pf155',
    band: '12-банд',
    content: 'Стратегия ижроси юзасидан йиллик ҳисобот Президент Администрациясига киритилсин.',
    due: 'year_end',
    raw: 'Каримов А.',
    person: 'p-karimov',
    stage: 'in_progress',
    staged: -20,
    seen: -120,
    marks: [{ kind: 'doing', at: -3, author: 'assistant' }],
    tasks: [
      {
        code: 'TSK-2026-0150',
        title: 'Годовой отчёт по Стратегии — сбор сведений',
        status: 'in_progress',
        moved: -2,
        due: 60,
      },
    ],
    batch: 'b1',
  },
  {
    id: 'a19',
    doc: 'd-orq897',
    band: '9-модда',
    content: 'Космик объектларни давлат рўйхатидан ўтказиш тартиби ишлаб чиқилсин.',
    due: 'year_end',
    raw: 'Рахимов Ш.',
    person: 'p-rakhimov',
    stage: 'not_started',
    staged: -3,
    seen: -3,
    batch: 'b3',
  },
  {
    id: 'a20',
    doc: 'd-pq312',
    band: '10-банд',
    content:
      'Кадастр маълумотларини космик суратлар билан солиштириш натижалари бўйича ахборот тайёрлансин.',
    due: 60,
    history: [
      { from: -40, to: 10, on: -45, kind: 'extension' },
      { from: 10, to: 60, on: -3, kind: 'extension' },
    ],
    raw: 'Юсупова Д.',
    person: 'p-yusupova',
    stage: 'in_progress',
    staged: -50,
    seen: -120,
    marks: [{ kind: 'doing', at: -5, author: 'assistant' }],
    problem: {
      text: 'Кадастр агентлиги маълумотлар базасига уланиш рухсатини бермаяпти.',
      proposal: 'Масалани идоралараро ишчи гуруҳ йиғилишига киритиш.',
      on: -5,
    },
    batch: 'b1',
  },
  {
    id: 'a21',
    doc: 'd-vmq512',
    band: '2-банд',
    content:
      'Дастурни молиялаштириш манбалари аниқлансин ва келгуси йил бюджети параметрларига киритилсин.',
    due: 'year_end',
    raw: 'Турсунов Б.',
    person: 'p-tursunov',
    stage: 'in_progress',
    staged: -30,
    seen: -45,
    tasks: [
      {
        code: 'TSK-2026-0144',
        title: 'Расчёт финансирования программы',
        status: 'in_progress',
        moved: -2,
        due: 30,
      },
    ],
    problem: {
      text: 'Иқтисодиёт ва молия вазирлиги лимитларни тасдиқламади.',
      proposal: 'Муддатни бюджет қабул қилингунга қадар узайтириш сўралсин.',
      on: -2,
    },
    requested: true,
    batch: 'b2',
  },
  {
    id: 'a22',
    doc: 'd-orq897',
    band: '3-модда',
    content: 'Қонун ижроси бўйича идоравий норматив ҳужжатлар рўйхати тасдиқлансин.',
    due: 90,
    raw: 'Абдуллаев Н.',
    person: 'p-abdullaev',
    stage: 'not_started',
    staged: -3,
    seen: -3,
    batch: 'b3',
  },
  {
    id: 'a23',
    doc: 'd-pf155',
    band: '1-банд',
    content: 'Стратегияни амалга ошириш бўйича «йўл харитаси» тасдиқлансин.',
    due: -30,
    raw: 'Каримов А.',
    person: 'p-karimov',
    stage: 'submitted',
    staged: -20,
    seen: -120,
    batch: 'b1',
  },
  {
    id: 'a24',
    doc: 'd-pq312',
    band: '1-банд',
    content: 'Қарор ижросини ташкил этиш бўйича масъуллар белгилансин.',
    due: -45,
    raw: 'Юсупова Д.',
    person: 'p-yusupova',
    stage: 'submitted',
    staged: -50,
    seen: -120,
    batch: 'b1',
  },
  {
    id: 'a25',
    doc: 'd-vmq512',
    band: '3-банд',
    content: 'Дастур кўрсаткичларининг мақсадли параметрлари ишлаб чиқилсин.',
    due: 5,
    raw: 'Рахимов Ш.',
    person: 'p-rakhimov',
    stage: 'submitted',
    staged: -8,
    seen: -45,
    batch: 'b2',
  },
  {
    id: 'a26',
    doc: 'd-pf155',
    band: '2-банд',
    content: 'Космик фаолият соҳасидаги норматив-ҳуқуқий ҳужжатлар хатловдан ўтказилсин.',
    due: -80,
    raw: 'Турсунов Б.',
    person: 'p-tursunov',
    stage: 'removed_from_control',
    staged: -70,
    seen: -120,
    batch: 'b1',
  },
  {
    id: 'a27',
    doc: 'd-pq312',
    band: '3-банд',
    content: 'Масофадан зондлаш маълумотларига эҳтиёж бўйича сўровнома ўтказилсин.',
    due: -40,
    raw: 'Рахимов Ш.',
    person: 'p-rakhimov',
    stage: 'removed_from_control',
    staged: -35,
    seen: -120,
    batch: 'b1',
  },
  {
    id: 'a28',
    doc: 'd-orq897',
    band: '1-модда',
    content: 'Қонуннинг мазмун-моҳияти аҳоли ўртасида тушунтирилсин.',
    due: -20,
    raw: 'Абдуллаев Н.',
    person: 'p-abdullaev',
    stage: 'removed_from_control',
    staged: -15,
    seen: -120,
    batch: 'b1',
  },
  {
    id: 'a29',
    doc: 'd-vmq512',
    band: '7-банд',
    content:
      'Ер усти станциялари учун ер участкаларини ажратиш масаласи ҳокимликлар билан ҳал этилсин.',
    due: 15,
    raw: 'Каримов А.',
    person: 'p-karimov',
    stage: 'returned',
    staged: -9,
    seen: -45,
    marks: [{ kind: 'contacted', at: -2, author: 'assistant' }],
    problem: {
      text: 'Самарқанд вилояти ҳокимлиги ер ажратиш бўйича қарор қабул қилмади.',
      proposal: 'Ҳокимликка Вазирлар Маҳкамаси номидан топшириқ хати юбориш.',
      on: -2,
    },
    batch: 'b2',
  },
];

interface BatchSpec {
  id: string;
  file: string;
  source: IjroSource;
  table: number;
  counts: Partial<Record<ChangeClass, number>>;
}

const BATCHES: BatchSpec[] = [
  {
    id: 'b1',
    file: 'АП топшириқлари 2-чорак.docx',
    source: 'pa',
    table: -120,
    counts: { new: 20 },
  },
  { id: 'b2', file: 'ВМ назорат жадвали.docx', source: 'vm', table: -45, counts: { new: 9 } },
  {
    id: 'b3',
    file: 'АП топшириқлари 3-чорак.docx',
    source: 'pa',
    table: -3,
    counts: {
      new: 2,
      unchanged: 15,
      text_changed: 1,
      responsible_changed: 1,
      due_moved: 2,
      vanished: 1,
    },
  },
];

/** Что изменила последняя применённая таблица: из этого считается двенадцатый вопрос. */
interface BatchEffect {
  created: string[];
  changed: string[];
  vanished: number;
  /** Переносы срока, которые человек ещё не подтвердил (ТЗ 7). */
  pending: { assignment_id: string; from: string; to: string }[];
}

/** Файл следующей таблицы: вымышленный предпросмотр выдаётся один раз, дальше — «без изменений». */
const NEXT_BATCH_ID = 'b4';

interface Row {
  id: string;
  document_id: string;
  band: string;
  band_order: number;
  content: string;
  mechanism: string | null;
  due_on: string | null;
  due_precision: DuePrecision;
  original_due_on: string | null;
  history: Extension[];
  extension_requested: boolean;
  responsible_raw: string;
  person_id: string | null;
  lead_id: string | null;
  stage: Stage;
  stage_changed_on: string;
  first_seen_on: string;
  marks: ControlMark[];
  tasks: LinkedTask[];
  interim_report_on: string | null;
  problem: string | null;
  proposal: string | null;
  problem_updated_on: string | null;
  question: { id: string; text: string; asked_on: string } | null;
  last_decision: { id: string; kind: DecisionKind; decided_on: string } | null;
  comments: Comment[];
  batch_id: string;
  version: number;
}

function bandOrder(band: string): number {
  const numbers = band.match(/\d+/g)?.map(Number) ?? [0];
  return numbers.reduce((total, each) => total * 100 + each, 0);
}

export class DemoIjro {
  private readonly now: () => Date;
  private documents: IjroDocument[] = [];
  private rows: Row[] = [];
  private batches: Batch[] = [];
  private effect: BatchEffect = { created: [], changed: [], vanished: 0, pending: [] };
  private nextApplied = false;
  private counter = 0;
  /** Что вернуть «Отменить»: решение закрыло вопрос, отмена его возвращает. */
  private undo = new Map<
    string,
    { id: string; question: Row['question']; previous: Row['last_decision'] }
  >();

  constructor(now: () => Date = () => new Date()) {
    this.now = now;
    this.reset();
  }

  private today(): string {
    return dayOf(this.now());
  }

  private nextId(prefix: string): string {
    this.counter += 1;
    return `${prefix}-${this.counter}`;
  }

  reset(): void {
    const today = this.today();
    const year = Number(today.slice(0, 4));
    const monthEnd = (): string => {
      // Последний день следующего месяца: срок «месяцем» никогда не оказывается в прошлом.
      const [y, m] = [Number(today.slice(0, 4)), Number(today.slice(5, 7))];
      return new Date(Date.UTC(y, m + 1, 0)).toISOString().slice(0, 10);
    };
    const due = (spec: DueSpec): [string | null, DuePrecision] => {
      if (spec === null) return [null, 'day'];
      if (spec === 'year_end') return [`${year}-12-31`, 'end_of_year'];
      if (spec === 'month_end') return [monthEnd(), 'month'];
      return [shift(today, spec), 'day'];
    };

    this.counter = 0;
    this.undo.clear();
    this.nextApplied = false;
    this.documents = DOCUMENTS.map((each) => ({
      id: each.id,
      kind: each.kind,
      code: each.code,
      issued_on: shift(today, each.issued),
      title: each.title,
      source: each.source,
    }));
    this.batches = BATCHES.map((each) => ({
      id: each.id,
      file: each.file,
      source: each.source,
      table_on: shift(today, each.table),
      uploaded_at: moment(shift(today, each.table)),
      state: 'applied' as const,
      counts: Object.fromEntries(
        CHANGE_CLASSES.map((name) => [name, each.counts[name] ?? 0]),
      ) as Record<ChangeClass, number>,
    }));
    this.rows = SPECS.map((spec) => {
      const [dueOn, precision] = due(spec.due);
      const history: Extension[] = (spec.history ?? []).map((each) => ({
        from: shift(today, each.from),
        // Последнее продление ведёт к нынешнему сроку, каким бы он ни был по точности.
        to: shift(today, each.to),
        on: shift(today, each.on),
        batch_id: spec.batch,
        kind: each.kind,
      }));
      const last = history.at(-1);
      if (last && dueOn) last.to = dueOn;
      return {
        id: spec.id,
        document_id: spec.doc,
        band: spec.band,
        band_order: bandOrder(spec.band),
        content: spec.content,
        mechanism: spec.mechanism ?? null,
        due_on: dueOn,
        due_precision: precision,
        original_due_on: history[0]?.from ?? dueOn,
        history,
        extension_requested: spec.requested ?? false,
        responsible_raw: spec.raw,
        person_id: spec.person,
        lead_id: spec.lead ?? null,
        stage: spec.stage,
        stage_changed_on: shift(today, spec.staged),
        first_seen_on: shift(today, spec.seen),
        marks: (spec.marks ?? []).map((each, index) => ({
          id: `${spec.id}-m${index}`,
          kind: each.kind,
          promised_on: each.promised === undefined ? null : shift(today, each.promised),
          comment: each.comment ?? null,
          made_at: moment(shift(today, each.at)),
          author: each.author,
        })),
        tasks: (spec.tasks ?? []).map((each, index) => ({
          id: `${spec.id}-t${index}`,
          code: each.code,
          title: each.title,
          status: each.status,
          step: null,
          due_on: each.due === null ? null : shift(today, each.due),
          moved_on: shift(today, each.moved),
        })),
        interim_report_on: spec.interim === undefined ? null : shift(today, spec.interim),
        problem: spec.problem?.text ?? null,
        proposal: spec.problem?.proposal ?? null,
        problem_updated_on: spec.problem ? shift(today, spec.problem.on) : null,
        question: spec.question
          ? {
              id: `${spec.id}-q`,
              text: spec.question.text,
              asked_on: shift(today, spec.question.asked),
            }
          : null,
        last_decision: null,
        comments: [],
        batch_id: spec.batch,
        version: 1,
      };
    });
    const pending = this.find('a08');
    this.effect = {
      created: ['a19', 'a22'],
      changed: ['a05', 'a13', 'a20'],
      vanished: 1,
      pending: pending.due_on
        ? [{ assignment_id: 'a08', from: pending.due_on, to: shift(pending.due_on, 45) }]
        : [],
    };
  }

  // --- расчёт ---------------------------------------------------------------------------

  private find(id: string): Row {
    const row = this.rows.find((each) => each.id === id);
    if (!row) throw new Error(`нет поручения ${id}`);
    return row;
  }

  private signOfLife(row: Row): { on: string; source: LifeSource } | null {
    const events: { on: string; source: LifeSource }[] = [
      ...row.marks.map((each) => ({
        on: each.made_at.slice(0, 10),
        source: 'control_mark' as const,
      })),
      ...row.tasks.map((each) => ({ on: each.moved_on, source: 'task_movement' as const })),
      ...(row.interim_report_on
        ? [{ on: row.interim_report_on, source: 'interim_report' as const }]
        : []),
    ];
    return events.reduce<{ on: string; source: LifeSource } | null>(
      (best, each) => (best === null || each.on > best.on ? each : best),
      null,
    );
  }

  /** Сколько дней тишины: от последнего признака жизни, а без него — от появления строки. */
  private quietDays(row: Row): number {
    return between(this.signOfLife(row)?.on ?? row.first_seen_on, this.today());
  }

  private stepOf(row: Row): { step: Step | null; deviation: number } {
    const today = this.today();
    if (!OPEN_STAGES.has(row.stage)) return { step: null, deviation: 0 };
    if (row.question) {
      return { step: 'awaiting_decision', deviation: between(row.question.asked_on, today) };
    }
    if (row.due_on) {
      const left = between(today, row.due_on);
      if (left < 0) return { step: 'overdue', deviation: -left };
      // Месяц и конец года по дням не горят (V33): дня у такого срока нет.
      if (row.due_precision === 'day' && left <= THRESHOLDS.burn_days) {
        return { step: 'burning', deviation: left };
      }
    }
    const quiet = this.quietDays(row);
    if (quiet > THRESHOLDS.quiet_days) {
      return { step: row.lead_id ? 'blocked_by_others' : 'silent', deviation: quiet };
    }
    return { step: null, deviation: 0 };
  }

  /** Середина срока, если срок длиннее трёх месяцев (ТЗ 3.3, V3). */
  private interimOn(row: Row): string | null {
    if (!row.due_on) return null;
    const length = between(row.first_seen_on, row.due_on);
    return length > 92 ? shift(row.first_seen_on, Math.round(length / 2)) : null;
  }

  private document(id: string): IjroDocument {
    const found = this.documents.find((each) => each.id === id);
    if (!found) throw new Error(`нет документа ${id}`);
    return found;
  }

  private row(row: Row): AssignmentRow {
    const document = this.document(row.document_id);
    const { step, deviation } = this.stepOf(row);
    return {
      id: row.id,
      document: { id: document.id, code: document.code, source: document.source },
      band: row.band,
      band_order: row.band_order,
      content: row.content,
      due_on: row.due_on,
      due_precision: row.due_precision,
      original_due_on: row.original_due_on,
      interim_on: this.interimOn(row),
      extensions: row.history.length,
      extension_requested: row.extension_requested,
      responsible_raw: row.responsible_raw,
      responsible: PEOPLE.find((each) => each.id === row.person_id) ?? null,
      lead_organization: ORGANIZATIONS.find((each) => each.id === row.lead_id) ?? null,
      is_co_executor: row.lead_id !== null,
      stage: row.stage,
      stage_changed_on: row.stage_changed_on,
      step,
      deviation,
      sign_of_life: this.signOfLife(row),
      has_problem: row.problem !== null,
      question: row.question,
      last_decision: row.last_decision,
      tasks: row.tasks.length,
      first_seen_on: row.first_seen_on,
      version: row.version,
    };
  }

  /** Порядок лестницы: ступень, внутри — что острее, затем срок и пункт. */
  private ordered(): AssignmentRow[] {
    const urgency = (row: AssignmentRow) =>
      row.step === 'burning' ? row.deviation : -row.deviation;
    return this.rows
      .map((each) => this.row(each))
      .sort(
        (a, b) =>
          (a.step ? RANK[a.step] : 9) - (b.step ? RANK[b.step] : 9) ||
          urgency(a) - urgency(b) ||
          (a.due_on ?? '9999').localeCompare(b.due_on ?? '9999') ||
          a.id.localeCompare(b.id),
      );
  }

  private questions(items: AssignmentRow[]): QuestionAnswer[] {
    const today = this.today();
    const open = items.filter((each) => OPEN_STAGES.has(each.stage));
    const ids = (rows: AssignmentRow[]) => rows.map((each) => each.id);
    const oldest = (rows: AssignmentRow[], days: (row: AssignmentRow) => number) => {
      const top = [...rows].sort((a, b) => days(b) - days(a))[0];
      return top ? { id: top.id, days: days(top) } : null;
    };

    const answers: Record<QuestionKey, () => QuestionAnswer> = {
      burning: () => {
        const rows = open.filter((each) => each.step === 'overdue' || each.step === 'burning');
        const people = new Map<
          string,
          { person: Person | null; responsible_raw: string; overdue: number; burning: number }
        >();
        for (const each of rows) {
          const key = each.responsible?.id ?? `raw:${each.responsible_raw}`;
          const entry = people.get(key) ?? {
            person: each.responsible,
            responsible_raw: each.responsible_raw,
            overdue: 0,
            burning: 0,
          };
          if (each.step === 'overdue') entry.overdue += 1;
          else entry.burning += 1;
          people.set(key, entry);
        }
        const overdue = rows.filter((each) => each.step === 'overdue');
        return {
          key: 'burning',
          burning: rows.length - overdue.length,
          overdue: overdue.length,
          oldest: oldest(overdue, (each) => each.deviation),
          by_person: [...people.values()].sort(
            (a, b) => b.overdue - a.overdue || b.burning - a.burning,
          ),
          rows: ids(rows),
        };
      },
      silent: () => {
        // «Молчит N дн» при близком сроке: срок не дальше порога или уже прошёл.
        const quiet = (each: AssignmentRow) =>
          between(each.sign_of_life?.on ?? each.first_seen_on, today);
        const rows = open.filter(
          (each) =>
            each.due_on !== null &&
            between(today, each.due_on) <= THRESHOLDS.near_due_days &&
            quiet(each) > THRESHOLDS.quiet_days,
        );
        const worst = oldest(rows, quiet);
        const top = worst ? rows.find((each) => each.id === worst.id) : undefined;
        return {
          key: 'silent',
          count: rows.length,
          worst:
            worst && top
              ? {
                  id: top.id,
                  person: top.responsible,
                  responsible_raw: top.responsible_raw,
                  days: worst.days,
                }
              : null,
          rows: ids([...rows].sort((a, b) => quiet(b) - quiet(a))),
        };
      },
      foreign: () => {
        // Сорвётся из-за чужого ведомства: мы соисполнитель, и строка уже на лестнице.
        const rows = open.filter(
          (each) => each.is_co_executor && each.step !== null && each.step !== 'awaiting_decision',
        );
        const groups = new Map<
          string,
          { organization: Organization; count: number; rows: string[] }
        >();
        for (const each of rows) {
          const organization = each.lead_organization;
          if (!organization) continue;
          const entry = groups.get(organization.id) ?? { organization, count: 0, rows: [] };
          entry.count += 1;
          entry.rows.push(each.id);
          groups.set(organization.id, entry);
        }
        return {
          key: 'foreign',
          count: rows.length,
          organizations: [...groups.values()].sort((a, b) => b.count - a.count),
          rows: ids(rows),
        };
      },
      awaiting: () => {
        const rows = open.filter((each) => each.step === 'awaiting_decision');
        return {
          key: 'awaiting',
          count: rows.length,
          oldest: oldest(rows, (each) => each.deviation),
          rows: ids(rows),
        };
      },
      returned: () => {
        const rows = items.filter((each) => each.stage === 'returned');
        return {
          key: 'returned',
          count: rows.length,
          oldest: oldest(rows, (each) => between(each.stage_changed_on, today)),
          rows: ids(rows),
        };
      },
      extension_requested: () => {
        const rows = open.filter((each) => each.extension_requested);
        return { key: 'extension_requested', count: rows.length, rows: ids(rows) };
      },
      report_up: () => {
        const rows = open.filter((each) => each.has_problem);
        const dates = rows
          .map((each) => this.find(each.id).problem_updated_on)
          .filter((each): each is string => each !== null)
          .sort();
        return {
          key: 'report_up',
          count: rows.length,
          freshest_on: dates.at(-1) ?? null,
          rows: ids(rows),
        };
      },
      without_tasks: () => {
        // Полнота по ADR-0033: открытые с точным сроком, у которых нет ни одной задачи.
        const exact = open.filter((each) => each.due_precision === 'day' && each.due_on !== null);
        const rows = exact.filter((each) => each.tasks === 0);
        return { key: 'without_tasks', count: rows.length, total: exact.length, rows: ids(rows) };
      },
      chronic: () => {
        const rows = open.filter((each) => each.extensions >= 2);
        const top = rows[0];
        return {
          key: 'chronic',
          count: rows.length,
          sample:
            top?.original_due_on && top.due_on
              ? {
                  id: top.id,
                  original_due_on: top.original_due_on,
                  due_on: top.due_on,
                  extensions: top.extensions,
                }
              : null,
          rows: ids(rows),
        };
      },
      year_end: () => {
        const yearEnd = `${today.slice(0, 4)}-12-31`;
        const upcoming = open.filter(
          (each) => each.due_on !== null && each.due_on >= today && each.due_on <= yearEnd,
        );
        const closed = items.filter(
          (each) =>
            !OPEN_STAGES.has(each.stage) &&
            between(each.stage_changed_on, today) <= THRESHOLDS.pace_window_days,
        ).length;
        return {
          key: 'year_end',
          upcoming: upcoming.length,
          closed,
          window_days: THRESHOLDS.pace_window_days,
          min_closed: THRESHOLDS.min_closed_for_pace,
          verdict:
            closed < THRESHOLDS.min_closed_for_pace
              ? 'little_data'
              : closed >= upcoming.length
                ? 'on_track'
                : 'behind',
          rows: ids(upcoming.filter((each) => each.stage === 'not_started')),
        };
      },
      last_batch: () => {
        const batch = this.batches.filter((each) => each.state === 'applied').at(-1);
        const known = new Set(items.map((each) => each.id));
        return {
          key: 'last_batch',
          batch: batch
            ? { id: batch.id, table_on: batch.table_on, file: batch.file, source: batch.source }
            : null,
          created: this.effect.created.length,
          changed: this.effect.changed.length,
          vanished: this.effect.vanished,
          pending_extensions: this.effect.pending.length,
          rows: [...this.effect.created, ...this.effect.changed].filter((id) => known.has(id)),
        };
      },
      documents: () => {
        const wall = this.wall(items);
        const worst = [...wall]
          .filter((each) => each.total > 0 && each.done < each.total)
          .sort((a, b) => a.done / a.total - b.done / b.total)[0];
        return {
          key: 'documents',
          worst: worst ? { document: worst.document, done: worst.done, total: worst.total } : null,
          rows: worst ? ids(open.filter((each) => each.document.id === worst.document.id)) : [],
        };
      },
    };
    return QUESTIONS.map((key) => answers[key]());
  }

  private wall(items: AssignmentRow[]): WallDocument[] {
    return this.documents.map((document) => {
      const own = items
        .filter((each) => each.document.id === document.id)
        .sort((a, b) => a.band_order - b.band_order);
      const open = own.filter((each) => OPEN_STAGES.has(each.stage));
      const counts = new Map<string, { person: Person; open: number }>();
      for (const each of open) {
        if (!each.responsible) continue;
        const entry = counts.get(each.responsible.id) ?? { person: each.responsible, open: 0 };
        entry.open += 1;
        counts.set(each.responsible.id, entry);
      }
      return {
        document,
        done: own.length - open.length,
        total: own.length,
        cells: own.map((each) => ({
          id: each.id,
          band: each.band,
          stage: each.stage,
          step: each.step,
        })),
        call_for_report: [...counts.values()].sort((a, b) => b.open - a.open)[0] ?? null,
      };
    });
  }

  view(): IjroView {
    const items = this.ordered();
    return {
      as_of: this.now().toISOString(),
      table_on: this.batches.filter((each) => each.state === 'applied').at(-1)?.table_on ?? null,
      thresholds: THRESHOLDS,
      questions: this.questions(items),
      items,
      documents: this.wall(items),
      people: PEOPLE,
      organizations: ORGANIZATIONS,
      batches: [...this.batches].reverse(),
      is_demo: true,
    };
  }

  card(id: string): AssignmentCard {
    const row = this.find(id);
    const batch = this.batches.find((each) => each.id === row.batch_id);
    const surname = row.responsible_raw.replace(/[А-ЯЁ]\./g, '').trim();
    return {
      ...this.row(row),
      document: this.document(row.document_id),
      mechanism: row.mechanism,
      // Копии: ответ сервера не меняется от следующей правки.
      extension_history: [...row.history],
      problem: row.problem,
      proposal: row.proposal,
      problem_updated_on: row.problem_updated_on,
      marks: [...row.marks].reverse(),
      linked_tasks: [...row.tasks],
      comments: [...row.comments],
      // Система только предлагает по фамилии; подтверждает человек (ТЗ 7).
      suggestions:
        row.person_id === null
          ? PEOPLE.filter((each) => surname !== '' && each.name.startsWith(surname))
          : [],
      import: {
        batch_id: row.batch_id,
        table_on: batch?.table_on ?? row.first_seen_on,
        file: batch?.file ?? '',
      },
    };
  }

  /** Справка по проблемным поручениям: открытые с записанной проблемой, в порядке лестницы. */
  spravka(): SpravkaLine[] {
    return this.ordered()
      .filter((each) => OPEN_STAGES.has(each.stage) && each.has_problem)
      .map((each) => {
        const row = this.find(each.id);
        return {
          id: each.id,
          place: each.band ? `${each.document.code} · ${each.band}` : each.document.code,
          content: each.content,
          due_on: each.due_on,
          due_precision: each.due_precision,
          responsible: each.responsible?.name ?? each.responsible_raw,
          problem: row.problem ?? '',
          proposal: row.proposal,
          problem_updated_on: row.problem_updated_on,
        };
      });
  }

  // --- правки ---------------------------------------------------------------------------

  private touch(row: Row): void {
    row.version += 1;
  }

  /** Контрольная отметка — оба пользователя (V35); она же признак жизни. */
  mark(
    id: string,
    input: { kind: MarkKind; promised_on?: string | null; comment?: string | null },
    author: Role,
  ): void {
    const row = this.find(id);
    row.marks.push({
      id: this.nextId('m'),
      kind: input.kind,
      promised_on: input.promised_on ?? null,
      comment: input.comment?.trim() ? input.comment.trim() : null,
      made_at: this.now().toISOString(),
      author,
    });
    this.touch(row);
  }

  setStage(id: string, stage: Stage): void {
    const row = this.find(id);
    if (row.stage === stage) return;
    row.stage = stage;
    row.stage_changed_on = this.today();
    this.touch(row);
  }

  setProblem(id: string, problem: string, proposal: string): void {
    const row = this.find(id);
    row.problem = problem.trim() || null;
    row.proposal = row.problem ? proposal.trim() || null : null;
    row.problem_updated_on = row.problem ? this.today() : null;
    this.touch(row);
  }

  setExtensionRequested(id: string, value: boolean): void {
    const row = this.find(id);
    row.extension_requested = value;
    this.touch(row);
  }

  /** Сопоставление подтверждает человек; псевдоним запоминается для всех строк с этим написанием. */
  matchPerson(id: string, personId: string): void {
    const raw = this.find(id).responsible_raw;
    for (const row of this.rows) {
      if (row.responsible_raw === raw && row.person_id === null) {
        row.person_id = personId;
        this.touch(row);
      }
    }
  }

  decide(id: string, kind: DecisionKind): string {
    const row = this.find(id);
    const decisionId = this.nextId('dec');
    this.undo.set(decisionId, { id, question: row.question, previous: row.last_decision });
    row.question = null;
    row.last_decision = { id: decisionId, kind, decided_on: this.today() };
    this.touch(row);
    return decisionId;
  }

  undoDecision(decisionId: string): void {
    const saved = this.undo.get(decisionId);
    if (!saved) return;
    const row = this.find(saved.id);
    row.question = saved.question;
    row.last_decision = saved.previous;
    this.undo.delete(decisionId);
    this.touch(row);
  }

  ask(id: string, text: string): string {
    const row = this.find(id);
    const questionId = this.nextId('q');
    row.question = { id: questionId, text: text.trim(), asked_on: this.today() };
    this.touch(row);
    return questionId;
  }

  undoQuestion(questionId: string): void {
    const row = this.rows.find((each) => each.question?.id === questionId);
    if (!row) return;
    row.question = null;
    this.touch(row);
  }

  comment(id: string, text: string, author: Role): void {
    const row = this.find(id);
    row.comments.push({
      id: this.nextId('c'),
      text: text.trim(),
      author,
      created_at: this.now().toISOString(),
    });
    this.touch(row);
  }

  /** «Разложить на задачу» (ADR-0033, V34): что покажет лист подтверждения. */
  taskPrefill(id: string): TaskPrefill {
    const row = this.find(id);
    const sentence = row.content.split(/(?<=[.!?])\s/)[0] ?? row.content;
    return {
      title: sentence.replace(/[.!?]$/, ''),
      type_code: 'ijro_report',
      assignee_id: row.person_id,
      due_on:
        row.due_on && row.due_precision === 'day'
          ? workdaysBefore(row.due_on, WORKDAYS_BEFORE)
          : null,
      ijro_assignment_id: id,
    };
  }

  createTask(id: string): void {
    const row = this.find(id);
    const prefill = this.taskPrefill(id);
    row.tasks.push({
      id: this.nextId('t'),
      code: `TSK-2026-${String(200 + this.counter).padStart(4, '0')}`,
      title: prefill.title,
      status: 'new',
      step: null,
      due_on: prefill.due_on,
      moved_on: this.today(),
    });
    this.touch(row);
  }

  // --- загрузка -------------------------------------------------------------------------

  private counts(rows: PreviewRow[]): Record<ChangeClass, number> {
    return Object.fromEntries(
      CHANGE_CLASSES.map((name) => [name, rows.filter((each) => each.class === name).length]),
    ) as Record<ChangeClass, number>;
  }

  /**
   * Предпросмотр таблицы. Файл в этом шаге не разбирается: вымышленный сервер выдаёт один и
   * тот же набор классов для первой новой таблицы, а после её применения — «без изменений».
   */
  preview(input: UploadInput): Preview {
    const today = this.today();
    const applied = this.batches.find(
      (each) => each.state === 'applied' && each.file === input.file.name,
    );
    const source = input.source ?? 'pa';
    const base = {
      batch_id: NEXT_BATCH_ID,
      file: input.file.name,
      source,
      table_year: input.table_year ?? Number(today.slice(0, 4)),
      table_on: today,
    };
    const unchanged = (skip: Set<string>): PreviewRow[] =>
      this.rows
        .filter((each) => OPEN_STAGES.has(each.stage) && !skip.has(each.id))
        .map((each) => ({
          id: `pv-same-${each.id}`,
          class: 'unchanged' as const,
          assignment_id: each.id,
          document_code: this.document(each.document_id).code,
          band: each.band,
          content: each.content,
          diff: null,
          due_move: null,
          unmatched: null,
          raw: null,
        }));
    if (applied) {
      return {
        ...base,
        batch_id: applied.id,
        counts: this.counts([]),
        rows: [],
        already_applied_on: applied.table_on,
      };
    }
    if (this.nextApplied) {
      const rows = unchanged(new Set());
      return { ...base, counts: this.counts(rows), rows, already_applied_on: null };
    }

    const late = this.find('a02');
    const pilot = this.find('a16');
    const base13 = this.find('a13');
    const vanished = this.find('a18');
    const renamed = this.find('a14');
    const pending = this.effect.pending[0];
    const changed: PreviewRow[] = [
      {
        id: 'pv-new-1',
        class: 'new',
        assignment_id: null,
        document_code: 'ПҚ-312',
        band: '12-банд',
        content:
          'Космик мониторинг маълумотларини давлат органларига тақдим этиш регламенти тасдиқлансин.',
        diff: null,
        due_move: null,
        unmatched: null,
        raw: null,
      },
      {
        id: 'pv-new-2',
        class: 'new',
        assignment_id: null,
        document_code: 'ПҚ-312',
        band: '13-банд',
        content: 'Ҳудудий бошқармаларда космик мониторинг бўйича масъул ходимлар бириктирилсин.',
        diff: null,
        due_move: null,
        unmatched: { raw: 'С.Ҳамидов', suggestions: [] },
        raw: null,
      },
      {
        id: 'pv-text-1',
        class: 'text_changed',
        assignment_id: base13.id,
        document_code: this.document(base13.document_id).code,
        band: base13.band,
        content: base13.content,
        diff: {
          field: 'content',
          from: base13.content,
          to: base13.content.replace('таклифлар киритилсин', 'асосланган таклифлар киритилсин'),
        },
        due_move: null,
        unmatched: null,
        raw: null,
      },
      {
        id: 'pv-resp-1',
        class: 'responsible_changed',
        assignment_id: renamed.id,
        document_code: this.document(renamed.document_id).code,
        band: renamed.band,
        content: renamed.content,
        diff: { field: 'responsible_raw', from: renamed.responsible_raw, to: 'Ш.Т.Рахимов' },
        due_move: null,
        unmatched: {
          raw: 'Ш.Т.Рахимов',
          suggestions: PEOPLE.filter((each) => each.id === 'p-rakhimov'),
        },
        raw: null,
      },
      {
        id: 'pv-due-1',
        class: 'due_moved',
        assignment_id: late.id,
        document_code: this.document(late.document_id).code,
        band: late.band,
        content: late.content,
        diff: null,
        due_move: late.due_on
          ? { from: late.due_on, to: shift(late.due_on, 30), suggested_kind: 'extension' }
          : null,
        unmatched: null,
        raw: null,
      },
      {
        id: 'pv-due-2',
        class: 'due_moved',
        assignment_id: pilot.id,
        document_code: this.document(pilot.document_id).code,
        band: pilot.band,
        content: pilot.content,
        diff: null,
        due_move: pilot.due_on
          ? { from: pilot.due_on, to: shift(pilot.due_on, 2), suggested_kind: 'correction' }
          : null,
        unmatched: null,
        raw: null,
      },
      ...(pending
        ? [
            {
              id: 'pv-due-3',
              class: 'due_moved' as const,
              assignment_id: pending.assignment_id,
              document_code: this.document(this.find(pending.assignment_id).document_id).code,
              band: this.find(pending.assignment_id).band,
              content: this.find(pending.assignment_id).content,
              diff: null,
              due_move: {
                from: pending.from,
                to: pending.to,
                suggested_kind: 'extension' as const,
              },
              unmatched: null,
              raw: null,
            },
          ]
        : []),
      {
        id: 'pv-gone-1',
        class: 'vanished',
        assignment_id: vanished.id,
        document_code: this.document(vanished.document_id).code,
        band: vanished.band,
        content: vanished.content,
        diff: null,
        due_move: null,
        unmatched: null,
        raw: null,
      },
      {
        id: 'pv-raw-1',
        class: 'unrecognized',
        assignment_id: null,
        document_code: null,
        band: null,
        content: '',
        diff: null,
        due_move: null,
        unmatched: null,
        raw: '7 | — | Ижро ҳолати: назоратда | 25 | масъул кўрсатилмаган',
      },
    ];
    const touched = new Set(
      changed.map((each) => each.assignment_id).filter((each): each is string => each !== null),
    );
    const rows = [...changed, ...unchanged(touched)].sort(
      (a, b) => CHANGE_CLASSES.indexOf(a.class) - CHANGE_CLASSES.indexOf(b.class),
    );
    return { ...base, counts: this.counts(rows), rows, already_applied_on: null };
  }

  /**
   * Применить таблицу. Привоз меняет только поля источника (инвариант 4): текст, написание
   * ответственного, срок. Перенос срока записывается только подтверждённый человеком и
   * попадает в историю продлений; неподтверждённый остаётся ждать (ТЗ 7).
   */
  apply(input: UploadInput, choices: ApplyChoices): ApplyResult {
    const preview = this.preview(input);
    if (preview.already_applied_on) {
      return { outcome: 'already_applied', applied_on: preview.already_applied_on };
    }
    const meaningful = preview.rows.filter((each) => each.class !== 'unchanged');
    if (meaningful.length === 0) return { outcome: 'no_changes' };

    const today = this.today();
    const created: string[] = [];
    const changed: string[] = [];
    const pending: BatchEffect['pending'] = [];
    let extensions = 0;
    let removed = 0;
    let vanished = 0;

    for (const each of meaningful) {
      if (each.class === 'new') {
        const id = this.nextId('n');
        const personId = choices.aliases[each.id] ?? null;
        this.rows.push({
          id,
          document_id:
            this.documents.find((doc) => doc.code === each.document_code)?.id ?? 'd-pq312',
          band: each.band ?? '',
          band_order: bandOrder(each.band ?? ''),
          content: each.content,
          mechanism: null,
          due_on: shift(today, 75),
          due_precision: 'day',
          original_due_on: shift(today, 75),
          history: [],
          extension_requested: false,
          responsible_raw: each.unmatched?.raw ?? 'Каримов А.',
          person_id: each.unmatched ? personId : 'p-karimov',
          lead_id: null,
          stage: 'not_started',
          stage_changed_on: today,
          first_seen_on: today,
          marks: [],
          tasks: [],
          interim_report_on: null,
          problem: null,
          proposal: null,
          problem_updated_on: null,
          question: null,
          last_decision: null,
          comments: [],
          batch_id: NEXT_BATCH_ID,
          version: 1,
        });
        created.push(id);
        continue;
      }
      if (each.class === 'unrecognized' || !each.assignment_id) continue;
      const row = this.find(each.assignment_id);
      if (each.class === 'text_changed' && each.diff) {
        row.content = each.diff.to;
        changed.push(row.id);
      } else if (each.class === 'responsible_changed' && each.diff) {
        row.responsible_raw = each.diff.to;
        row.person_id = choices.aliases[each.id] ?? null;
        changed.push(row.id);
      } else if (each.class === 'due_moved' && each.due_move) {
        const kind = choices.due_moves[each.id];
        if (kind) {
          row.history.push({
            from: each.due_move.from,
            to: each.due_move.to,
            on: today,
            batch_id: NEXT_BATCH_ID,
            kind,
          });
          row.due_on = each.due_move.to;
          extensions += 1;
          changed.push(row.id);
        } else {
          pending.push({ assignment_id: row.id, from: each.due_move.from, to: each.due_move.to });
        }
      } else if (each.class === 'vanished') {
        vanished += 1;
        if (choices.removed.includes(each.id)) {
          row.stage = 'removed_from_control';
          row.stage_changed_on = today;
          removed += 1;
        }
      }
      this.touch(row);
    }

    this.batches.push({
      id: NEXT_BATCH_ID,
      file: input.file.name,
      source: preview.source,
      table_on: today,
      uploaded_at: this.now().toISOString(),
      state: 'applied',
      counts: preview.counts,
    });
    this.effect = { created, changed, vanished, pending };
    this.nextApplied = true;
    return {
      outcome: 'applied',
      created: created.length,
      changed: changed.length,
      vanished,
      removed,
      extensions,
      pending_extensions: pending.length,
    };
  }
}

export const demoIjro = new DemoIjro();

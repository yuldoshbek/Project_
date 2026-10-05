/**
 * Сервер «Взаимодействия» в памяти — для тестов экрана.
 *
 * Был вымышленным сервером экрана на утверждение (01.10.2026); после утверждения API написан
 * под него (`backend/app/api/routes/interaction.py`), данные переехали в
 * `backend/app/demo_interaction.py`, а этот файл отвечает на те же пути в тестах (`handle`).
 * Сам сервер проверяют `backend/tests/test_interaction.py`; здесь — что экран делает с
 * ответами.
 *
 * **Одни данные — все числа.** Ответы вопросов, списки, карточки считаются из одного набора
 * записей одними функциями (ТЗ 5, инвариант 2). Настоящий сервер считает то же в
 * `services/metrics.py`.
 *
 * **Ступени** — те же, что у лестницы Пульта (`domain/attention`): входящее со сроком горит
 * и просрочивается, как задача; наше исходящее без ответа — «зависит от чужих», когда
 * попрошенный срок прошёл или, без срока, молчание дольше порога (V39); соглашение со
 * следующим шагом в прошлом — просрочено, без движения дольше 90 дней — «спит» (ТЗ 5).
 *
 * Сроки заданы от сегодняшнего дня по Ташкенту, чтобы картина была живой в любой день.
 */

import type { Step } from '@/sections/pult/model';
import { AGENCY_TIMEZONE } from '@/shared/time';

import {
  QUESTIONS,
  RATINGS,
  type Agreement,
  type AgreementKind,
  type Direction,
  type InteractionView,
  type LetterRow,
  type LinkType,
  type NewLetter,
  type OrganizationCard,
  type OrganizationKind,
  type OrganizationRef,
  type OrganizationRole,
  type OrganizationRow,
  type Person,
  type QuestionAnswer,
  type QuestionKey,
  type Rating,
  type Thresholds,
} from './model';

const DAY_MS = 86_400_000;

/** Пороги ТЗ 4–5; на сервере — справочник порогов. */
const THRESHOLDS: Thresholds = { burn_days: 7, quiet_days: 14, sleeping_days: 90, min_letters: 5 };

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

function between(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[middle]!
    : Math.round((sorted[middle - 1]! + sorted[middle]!) / 2);
}

const PEOPLE: Person[] = [
  { id: 'p-karimov', name: 'Каримов А.' },
  { id: 'p-yusupova', name: 'Юсупова Д.' },
  { id: 'p-tursunov', name: 'Турсунов Б.' },
  { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
];

interface OrganizationSpec {
  id: string;
  name: string;
  short_name: string | null;
  kind: OrganizationKind;
  founded?: boolean;
  phone?: string;
  email?: string;
  ijro?: { id: string; place: string; content: string; step: Step | null }[];
  projects?: { id: string; code: string; title: string; role: OrganizationRole }[];
}

const ORGANIZATIONS: OrganizationSpec[] = [
  {
    id: 'o-eco',
    name: 'Министерство экологии, охраны окружающей среды и изменения климата',
    short_name: 'Минэкологии',
    kind: 'ministry',
    phone: '+998 71 207-00-00',
    email: 'info@eco.example.uz',
    ijro: [
      {
        id: 'i-a03',
        place: 'ПҚ-312 · 2-банд',
        content:
          'Сув ҳавзалари ҳолатини космик мониторинг қилиш тартиби тўғрисидаги низом лойиҳаси ишлаб чиқилсин.',
        step: 'overdue',
      },
      {
        id: 'i-a11',
        place: 'ПҚ-312 · 11-банд',
        content:
          'Ўрмон фонди ерларини космик мониторинг қилиш натижалари ҳар чоракда Вазирлар Маҳкамасига киритиб борилсин.',
        step: 'blocked_by_others',
      },
    ],
    projects: [
      {
        id: 'pr-geodata',
        code: 'PRJ-2026-004',
        title: 'Геоданные для мониторинга засухи',
        role: 'lead_agency',
      },
    ],
  },
  {
    id: 'o-trans',
    name: 'Министерство транспорта',
    short_name: 'Минтранс',
    kind: 'ministry',
    phone: '+998 71 233-00-00',
    ijro: [
      {
        id: 'i-a10',
        place: 'ВМҚ-512 · 8-банд',
        content:
          'Транспорт йўлакларида навигация хизматларини ривожлантириш бўйича «йўл харитаси» ишлаб чиқилсин.',
        step: 'blocked_by_others',
      },
    ],
  },
  {
    id: 'o-digital',
    name: 'Министерство цифровых технологий',
    short_name: 'Минцифры',
    kind: 'ministry',
    email: 'office@digital.example.uz',
  },
  {
    id: 'o-center',
    name: 'Центр космического мониторинга и геоинформационных технологий',
    short_name: 'Центр',
    kind: 'agency',
    founded: true,
    phone: '+998 71 150-00-00',
    projects: [
      {
        id: 'pr-portal',
        code: 'PRJ-2026-002',
        title: 'Геопортал агентства',
        role: 'executor',
      },
      {
        id: 'pr-station',
        code: 'PRJ-2026-006',
        title: 'Наземная станция приёма',
        role: 'co_executor',
      },
    ],
  },
  {
    id: 'o-samarkand',
    name: 'Хокимият Самаркандской области',
    short_name: 'Самаркандский хокимият',
    kind: 'khokimiyat',
  },
  {
    id: 'o-unoosa',
    name: 'Управление ООН по вопросам космического пространства',
    short_name: 'UNOOSA',
    kind: 'international',
    email: 'unoosa@example.org',
  },
  {
    id: 'o-minvuz',
    name: 'Министерство высшего образования, науки и инноваций',
    short_name: 'Минвуз',
    kind: 'ministry',
  },
  {
    id: 'o-telecom',
    name: 'АК «Узбектелеком»',
    short_name: 'Узбектелеком',
    kind: 'company',
  },
];

interface LetterSpec {
  id: string;
  dir: Direction;
  org: string;
  subject: string;
  number?: string;
  /** Все даты — в днях от сегодня. */
  sent: number;
  due?: number;
  answered?: number;
  reply?: string;
  author?: string;
  link?: { type: LinkType; id: string; title: string };
  rating?: Rating;
}

const LETTERS: LetterSpec[] = [
  // Минэкологии: шесть исходящих с ответом — скорость считается.
  ...[
    { sent: -150, answered: -142, rating: 'substance' as const },
    { sent: -128, answered: -116, rating: 'substance' as const },
    { sent: -110, answered: -101, rating: 'formal' as const },
    { sent: -90, answered: -80 },
    { sent: -70, answered: -63, rating: 'substance' as const },
    { sent: -52, answered: -41 },
  ].map((each, index): LetterSpec => ({
    id: `l-eco-${index + 1}`,
    dir: 'outgoing',
    org: 'o-eco',
    subject: [
      'О предоставлении данных наземных метеостанций',
      'О согласовании методики оценки засухи',
      'О доступе к реестру водных объектов',
      'О совместной рабочей группе по мониторингу',
      'О замечаниях к проекту положения',
      'О данных по лесному фонду за полугодие',
    ][index]!,
    number: `03-11/${2100 + index * 37}`,
    sent: each.sent,
    answered: each.answered,
    reply: `02-${1400 + index * 21}`,
    author: index % 2 === 0 ? 'p-yusupova' : 'p-rakhimov',
    ...(each.rating ? { rating: each.rating } : {}),
  })),
  {
    id: 'l-eco-7',
    dir: 'outgoing',
    org: 'o-eco',
    subject: 'О границах водоохранных зон для космической съёмки',
    number: '03-11/2420',
    sent: -26,
    due: -6,
    author: 'p-yusupova',
    link: { type: 'ijro', id: 'i-a03', title: 'ПҚ-312 · 2-банд' },
  },
  {
    id: 'l-eco-in-1',
    dir: 'incoming',
    org: 'o-eco',
    subject: 'Запрос космических снимков пастбищ Каракалпакстана',
    number: '04-2/887',
    sent: -4,
    due: 3,
    author: 'p-rakhimov',
  },
  // Минтранс: пять ответов — медленный, двое ждут.
  ...[
    { sent: -160, answered: -131 },
    { sent: -140, answered: -118, rating: 'formal' as const },
    { sent: -120, answered: -95, rating: 'off_topic' as const },
    { sent: -100, answered: -66 },
    { sent: -75, answered: -52, rating: 'formal' as const },
  ].map((each, index): LetterSpec => ({
    id: `l-trans-${index + 1}`,
    dir: 'outgoing',
    org: 'o-trans',
    subject: [
      'О навигационном обеспечении грузовых коридоров',
      'О доступе к данным ГЛОНАСС/GPS мониторинга',
      'О пилотном участке трассы',
      'О замечаниях к «дорожной карте» навигации',
      'О составе межведомственной группы',
    ][index]!,
    number: `03-07/${1700 + index * 41}`,
    sent: each.sent,
    answered: each.answered,
    reply: `11-${900 + index * 13}`,
    author: 'p-tursunov',
    ...(each.rating ? { rating: each.rating } : {}),
  })),
  {
    id: 'l-trans-6',
    dir: 'outgoing',
    org: 'o-trans',
    subject: 'О согласовании «дорожной карты» навигационных услуг',
    number: '03-07/1985',
    sent: -40,
    due: -19,
    author: 'p-tursunov',
    link: { type: 'ijro', id: 'i-a10', title: 'ВМҚ-512 · 8-банд' },
  },
  {
    id: 'l-trans-7',
    dir: 'outgoing',
    org: 'o-trans',
    subject: 'О данных о трафике для модели загруженности',
    number: '03-07/2044',
    sent: -12,
    due: 8,
    author: 'p-tursunov',
  },
  // Минцифры: мало писем.
  {
    id: 'l-digital-1',
    dir: 'outgoing',
    org: 'o-digital',
    subject: 'О размещении геопортала в облаке госорганов',
    number: '03-09/1802',
    sent: -60,
    answered: -48,
    reply: '05-312',
    author: 'p-abdullaeva',
    rating: 'substance',
  },
  {
    id: 'l-digital-in-1',
    dir: 'incoming',
    org: 'o-digital',
    subject: 'О подключении к единому реестру космической деятельности',
    number: '05-1/455',
    sent: -15,
    due: -2,
    author: 'p-abdullaeva',
  },
  // Центр — учреждена агентством.
  {
    id: 'l-center-in-1',
    dir: 'incoming',
    org: 'o-center',
    subject: 'Отчёт о загрузке наземной станции за квартал',
    number: '01-02/118',
    sent: -6,
    due: 2,
    author: 'p-karimov',
    link: { type: 'project', id: 'pr-station', title: 'Наземная станция приёма' },
  },
  {
    id: 'l-center-2',
    dir: 'outgoing',
    org: 'o-center',
    subject: 'О сроках выгрузки данных в субплатформу',
    number: '03-01/2301',
    sent: -20,
    answered: -17,
    reply: '01-02/104',
    author: 'p-karimov',
    rating: 'substance',
  },
  {
    id: 'l-center-in-2',
    dir: 'incoming',
    org: 'o-center',
    subject: 'Предложения в план работ на следующий год',
    number: '01-02/96',
    sent: -30,
    answered: -24,
    reply: '03-01/2288',
    author: 'p-karimov',
  },
  // Самаркандский хокимият: без срока, молчит.
  {
    id: 'l-samarkand-1',
    dir: 'outgoing',
    org: 'o-samarkand',
    subject: 'О выделении участка под наземную станцию',
    number: '03-14/1950',
    sent: -38,
    author: 'p-karimov',
    link: { type: 'project', id: 'pr-station', title: 'Наземная станция приёма' },
  },
  // UNOOSA.
  {
    id: 'l-unoosa-in-1',
    dir: 'incoming',
    org: 'o-unoosa',
    subject: 'Invitation: Space Applications workshop — confirmation of participants',
    number: 'OOSA/2026/118',
    sent: -9,
    due: 12,
    author: 'p-rakhimov',
    link: { type: 'preparation', id: 'ev-congress', title: 'Международный конгресс' },
  },
  // Минвуз.
  {
    id: 'l-minvuz-1',
    dir: 'outgoing',
    org: 'o-minvuz',
    subject: 'О квотах магистратуры по космическим технологиям',
    number: '03-05/1890',
    sent: -45,
    answered: -30,
    reply: '07-221',
    author: 'p-yusupova',
    rating: 'formal',
  },
  {
    id: 'l-minvuz-2',
    dir: 'outgoing',
    org: 'o-minvuz',
    subject: 'О стажировках студентов в Центре',
    number: '03-05/2210',
    sent: -10,
    due: 10,
    author: 'p-yusupova',
  },
];

interface AgreementSpec {
  id: string;
  org: string;
  kind: AgreementKind;
  title: string;
  signed: number;
  until?: number;
  next?: string;
  next_on?: number;
  who?: string;
  moved: number;
}

const AGREEMENTS: AgreementSpec[] = [
  {
    id: 'g-eco',
    org: 'o-eco',
    kind: 'memorandum',
    title: 'Меморандум о мониторинге водных ресурсов',
    signed: -300,
    until: 430,
    next: 'Утвердить план совместных работ на 2027 год',
    next_on: 40,
    who: 'p-yusupova',
    moved: -12,
  },
  {
    id: 'g-trans',
    org: 'o-trans',
    kind: 'memorandum',
    title: 'Меморандум о навигационных услугах',
    signed: -420,
    until: 310,
    next: 'Пилотный участок на трассе Ташкент — Самарканд',
    who: 'p-tursunov',
    moved: -134,
  },
  {
    id: 'g-unoosa',
    org: 'o-unoosa',
    kind: 'memorandum',
    title: 'Memorandum on Space Applications cooperation',
    signed: -510,
    until: 220,
    who: 'p-rakhimov',
    moved: -201,
  },
  {
    id: 'g-telecom',
    org: 'o-telecom',
    kind: 'contract',
    title: 'Договор на каналы связи наземной станции',
    signed: -200,
    until: 165,
    next: 'Подписать акт сверки за третий квартал',
    next_on: -5,
    who: 'p-karimov',
    moved: -33,
  },
  {
    id: 'g-center',
    org: 'o-center',
    kind: 'contract',
    title: 'Договор на обработку снимков',
    signed: -150,
    until: 215,
    next: 'Приёмка этапа «каталог снимков»',
    next_on: 5,
    who: 'p-karimov',
    moved: -3,
  },
  {
    id: 'g-minvuz',
    org: 'o-minvuz',
    kind: 'memorandum',
    title: 'Меморандум о подготовке кадров',
    signed: -95,
    until: 1000,
    next: 'Согласовать программу стажировок',
    next_on: 60,
    who: 'p-yusupova',
    moved: -20,
  },
];

interface Letter extends Omit<LetterRow, 'state' | 'step' | 'deviation' | 'days'> {
  link: LetterRow['link'];
}

interface StoredAgreement extends Omit<
  Agreement,
  'sleeping' | 'quiet_days' | 'step' | 'deviation'
> {
  org_id: string;
}

export class FakeInteraction {
  private readonly now: () => Date;
  private letters: Letter[] = [];
  private agreements: StoredAgreement[] = [];
  private counter = 0;

  constructor(now: () => Date = () => new Date()) {
    this.now = now;
    this.reset();
  }

  private today(): string {
    return dayOf(this.now());
  }

  reset(): void {
    const today = this.today();
    const on = (days: number) => shift(today, days);
    this.counter = 0;
    this.letters = LETTERS.map((spec) => ({
      id: spec.id,
      direction: spec.dir,
      organization: this.ref(spec.org),
      subject: spec.subject,
      number: spec.number ?? null,
      sent_on: on(spec.sent),
      due_on: spec.due === undefined ? null : on(spec.due),
      author: PEOPLE.find((each) => each.id === spec.author) ?? null,
      link: spec.link ?? null,
      answered_on: spec.answered === undefined ? null : on(spec.answered),
      reply:
        spec.answered === undefined
          ? null
          : { number: spec.reply ?? null, sent_on: on(spec.answered) },
      rating: spec.rating ?? null,
      version: 1,
    }));
    this.agreements = AGREEMENTS.map((spec) => ({
      id: spec.id,
      org_id: spec.org,
      organization: this.ref(spec.org),
      kind: spec.kind,
      title: spec.title,
      signed_on: on(spec.signed),
      valid_until: spec.until === undefined ? null : on(spec.until),
      next_step: spec.next ?? null,
      next_step_on: spec.next_on === undefined ? null : on(spec.next_on),
      responsible: PEOPLE.find((each) => each.id === spec.who) ?? null,
      moved_on: on(spec.moved),
      version: 1,
    }));
  }

  private spec(id: string): OrganizationSpec {
    const found = ORGANIZATIONS.find((each) => each.id === id);
    if (!found) throw new Error(`нет организации ${id}`);
    return found;
  }

  private ref(id: string): OrganizationRef {
    const spec = this.spec(id);
    return { id: spec.id, name: spec.name, short_name: spec.short_name };
  }

  // --- расчёт ---------------------------------------------------------------------------

  private letterRow(letter: Letter): LetterRow {
    const today = this.today();
    const answered = letter.answered_on !== null;
    const state = answered
      ? 'answered'
      : letter.direction === 'outgoing'
        ? 'waiting_reply'
        : 'to_answer';
    let step: Step | null = null;
    let deviation = 0;
    const waiting = between(letter.sent_on, today);
    if (state === 'to_answer' && letter.due_on) {
      const left = between(today, letter.due_on);
      if (left < 0) [step, deviation] = ['overdue', -left];
      else if (left <= THRESHOLDS.burn_days) [step, deviation] = ['burning', left];
    } else if (state === 'waiting_reply') {
      // Попрошенный срок прошёл — ждём чужих; без срока — после порога молчания (V39).
      if (letter.due_on && letter.due_on < today) {
        [step, deviation] = ['blocked_by_others', between(letter.due_on, today)];
      } else if (!letter.due_on && waiting > THRESHOLDS.quiet_days) {
        [step, deviation] = ['blocked_by_others', waiting];
      }
    }
    return {
      ...letter,
      state,
      step,
      deviation,
      days: answered ? between(letter.sent_on, letter.answered_on!) : waiting,
    };
  }

  private agreementRow(agreement: StoredAgreement): Agreement {
    const today = this.today();
    const quiet = between(agreement.moved_on, today);
    const sleeping = quiet > THRESHOLDS.sleeping_days;
    let step: Step | null = null;
    let deviation = 0;
    if (agreement.next_step_on && agreement.next_step_on < today) {
      [step, deviation] = ['overdue', between(agreement.next_step_on, today)];
    } else if (
      agreement.next_step_on &&
      between(today, agreement.next_step_on) <= THRESHOLDS.burn_days
    ) {
      [step, deviation] = ['burning', between(today, agreement.next_step_on)];
    } else if (sleeping) {
      [step, deviation] = ['silent', quiet];
    }
    return {
      id: agreement.id,
      organization: agreement.organization,
      kind: agreement.kind,
      title: agreement.title,
      signed_on: agreement.signed_on,
      valid_until: agreement.valid_until,
      next_step: agreement.next_step,
      next_step_on: agreement.next_step_on,
      responsible: agreement.responsible,
      moved_on: agreement.moved_on,
      version: agreement.version,
      sleeping,
      quiet_days: quiet,
      step,
      deviation,
    };
  }

  private ordered<T extends { step: Step | null; deviation: number }>(
    rows: T[],
    date: (row: T) => string,
  ): T[] {
    const urgency = (row: T) => (row.step === 'burning' ? row.deviation : -row.deviation);
    return [...rows].sort(
      (a, b) =>
        (a.step ? RANK[a.step] : 9) - (b.step ? RANK[b.step] : 9) ||
        urgency(a) - urgency(b) ||
        date(b).localeCompare(date(a)),
    );
  }

  private letterRows(): LetterRow[] {
    return this.ordered(
      this.letters.map((each) => this.letterRow(each)),
      (row) => row.sent_on,
    );
  }

  private agreementRows(): Agreement[] {
    return this.ordered(
      this.agreements.map((each) => this.agreementRow(each)),
      (row) => row.moved_on,
    );
  }

  private organizationRow(spec: OrganizationSpec, letters: LetterRow[]): OrganizationRow {
    const own = letters.filter((each) => each.organization.id === spec.id);
    const replies = own.filter(
      (each) => each.direction === 'outgoing' && each.state === 'answered',
    );
    const agreements = this.agreementRows().filter((each) => each.organization.id === spec.id);
    const ratings = Object.fromEntries(RATINGS.map((rating) => [rating, 0])) as Record<
      Rating,
      number
    >;
    for (const each of replies) if (each.rating) ratings[each.rating] += 1;
    return {
      id: spec.id,
      name: spec.name,
      short_name: spec.short_name,
      kind: spec.kind,
      is_founded_by_agency: spec.founded ?? false,
      phone: spec.phone ?? null,
      email: spec.email ?? null,
      waiting: own.filter((each) => each.state === 'waiting_reply').length,
      to_answer: own.filter((each) => each.state === 'to_answer').length,
      agreement_count: agreements.length,
      sleeping: agreements.filter((each) => each.sleeping).length,
      overdue_steps: agreements.filter((each) => each.step === 'overdue').length,
      ijro_lead: spec.ijro?.length ?? 0,
      project_count: spec.projects?.length ?? 0,
      speed: {
        letters: replies.length,
        median_days:
          replies.length >= THRESHOLDS.min_letters
            ? median(replies.map((each) => each.days))
            : null,
      },
      ratings,
    };
  }

  private organizationRows(letters: LetterRow[]): OrganizationRow[] {
    // Кого ждём и кому должны — первыми; остальные по названию.
    return ORGANIZATIONS.map((spec) => this.organizationRow(spec, letters)).sort(
      (a, b) =>
        b.waiting + b.to_answer - (a.waiting + a.to_answer) ||
        (a.short_name ?? a.name).localeCompare(b.short_name ?? b.name, 'ru'),
    );
  }

  private questions(
    letters: LetterRow[],
    organizations: OrganizationRow[],
    agreements: Agreement[],
  ): QuestionAnswer[] {
    const today = this.today();
    const answers: Record<QuestionKey, () => QuestionAnswer> = {
      not_answering: () => {
        const rows = letters.filter((each) => each.state === 'waiting_reply');
        const groups = new Map<
          string,
          { organization: OrganizationRef; count: number; oldest_days: number; rows: string[] }
        >();
        for (const each of rows) {
          const entry = groups.get(each.organization.id) ?? {
            organization: each.organization,
            count: 0,
            oldest_days: 0,
            rows: [],
          };
          entry.count += 1;
          entry.oldest_days = Math.max(entry.oldest_days, each.days);
          entry.rows.push(each.id);
          groups.set(each.organization.id, entry);
        }
        return {
          key: 'not_answering',
          count: rows.length,
          organizations: [...groups.values()].sort(
            (a, b) => b.count - a.count || b.oldest_days - a.oldest_days,
          ),
          rows: rows.map((each) => each.id),
        };
      },
      to_answer: () => {
        const rows = letters.filter((each) => each.state === 'to_answer');
        const upcoming = rows
          .filter((each) => each.due_on && each.due_on >= today)
          .sort((a, b) => a.due_on!.localeCompare(b.due_on!))[0];
        return {
          key: 'to_answer',
          count: rows.length,
          overdue: rows.filter((each) => each.step === 'overdue').length,
          nearest: upcoming
            ? {
                id: upcoming.id,
                due_on: upcoming.due_on!,
                days: between(today, upcoming.due_on!),
              }
            : null,
          rows: rows.map((each) => each.id),
        };
      },
      speed: () => {
        const measured = organizations
          .filter((each) => each.speed.median_days !== null)
          .map((each) => ({
            organization: { id: each.id, name: each.name, short_name: each.short_name },
            median_days: each.speed.median_days!,
            letters: each.speed.letters,
          }))
          .sort((a, b) => b.median_days - a.median_days);
        return {
          key: 'speed',
          measured,
          little_data: organizations.filter(
            (each) => each.speed.letters > 0 && each.speed.median_days === null,
          ).length,
          min_letters: THRESHOLDS.min_letters,
          rows: measured.map((each) => each.organization.id),
        };
      },
      sleeping: () => {
        const rows = agreements.filter((each) => each.sleeping);
        const top = [...rows].sort((a, b) => b.quiet_days - a.quiet_days)[0];
        return {
          key: 'sleeping',
          count: rows.length,
          oldest: top ? { id: top.id, days: top.quiet_days } : null,
          rows: rows.map((each) => each.id),
        };
      },
    };
    return QUESTIONS.map((key) => answers[key]());
  }

  view(): InteractionView {
    const letters = this.letterRows();
    const organizations = this.organizationRows(letters);
    const agreements = this.agreementRows();
    return {
      as_of: this.now().toISOString(),
      thresholds: THRESHOLDS,
      questions: this.questions(letters, organizations, agreements),
      letters,
      organizations,
      agreements,
      people: PEOPLE,
      choices: ORGANIZATIONS.map((spec) => this.ref(spec.id)),
      is_demo: true,
    };
  }

  organization(id: string): OrganizationCard {
    const spec = this.spec(id);
    const letters = this.letterRows();
    return {
      ...this.organizationRow(spec, letters),
      letters: letters.filter((each) => each.organization.id === id),
      agreements: this.agreementRows().filter((each) => each.organization.id === id),
      ijro: [...(spec.ijro ?? [])],
      projects: [...(spec.projects ?? [])],
    };
  }

  // --- правки ---------------------------------------------------------------------------

  private letter(id: string): Letter {
    const found = this.letters.find((each) => each.id === id);
    if (!found) throw new Error(`нет письма ${id}`);
    return found;
  }

  /** Оценка ответа — руководитель, одно касание; только у полученного ответа (V38). */
  rate(id: string, rating: Rating | null): void {
    const letter = this.letter(id);
    if (letter.direction !== 'outgoing' || letter.answered_on === null) {
      throw new Error('Оценивается полученный ответ на наше письмо');
    }
    letter.rating = rating;
    letter.version += 1;
  }

  /** «Ответ получен» у исходящего, «Ответили» у входящего — помощник. */
  answer(id: string, input: { on: string; number: string | null }): void {
    const letter = this.letter(id);
    if (input.on < letter.sent_on) throw new Error('Ответ не может быть раньше письма');
    letter.answered_on = input.on;
    letter.reply = { number: input.number?.trim() || null, sent_on: input.on };
    letter.version += 1;
  }

  add(input: NewLetter): string {
    if (!input.subject.trim()) throw new Error('Напишите тему письма');
    this.counter += 1;
    const id = `l-new-${this.counter}`;
    this.letters.push({
      id,
      direction: input.direction,
      organization: this.ref(input.organization_id),
      subject: input.subject.trim(),
      number: input.number?.trim() || null,
      sent_on: input.sent_on,
      due_on: input.due_on,
      author: PEOPLE.find((each) => each.id === input.author_id) ?? null,
      link: null,
      answered_on: null,
      reply: null,
      rating: null,
      version: 1,
    });
    return id;
  }

  /** Следующий шаг соглашения — это и есть его движение (V40). */
  setNextStep(id: string, input: { next_step: string; next_step_on: string | null }): void {
    const agreement = this.agreements.find((each) => each.id === id);
    if (!agreement) throw new Error(`нет соглашения ${id}`);
    agreement.next_step = input.next_step.trim() || null;
    agreement.next_step_on = input.next_step_on;
    agreement.moved_on = this.today();
    agreement.version += 1;
  }
}

type Reply = [number, unknown];

/**
 * Ответ на запрос экрана: те же пути и роли, что у сервера. `null` — путь не раздела, и
 * отвечает следующая подмена теста.
 */
export function handle(
  server: FakeInteraction,
  method: string,
  path: string,
  body: Record<string, unknown> | undefined,
  role: 'assistant' | 'leader',
): Reply | null {
  const BASE = '/api/v1/interaction';
  if (!path.startsWith(BASE)) return null;
  const rest = path.slice(BASE.length).split('/').filter(Boolean);
  const input = body ?? {};
  const refused: Reply = [403, { detail: 'Это действие другой роли' }];
  try {
    if (method === 'GET' && rest.length === 0) return [200, server.view()];
    if (method === 'GET' && rest[0] === 'organizations' && rest[1]) {
      return [200, server.organization(rest[1])];
    }
    if (rest[0] === 'letters') {
      if (method === 'POST' && rest.length === 1) {
        if (role !== 'assistant') return refused;
        return [201, { id: server.add(input as unknown as NewLetter) }];
      }
      const id = String(rest[1]);
      if (rest[2] === 'answer') {
        if (role !== 'assistant') return refused;
        server.answer(id, {
          on: String(input.on),
          number: (input.number as string | null) ?? null,
        });
        return [204, undefined];
      }
      if (rest[2] === 'rating') {
        if (role !== 'leader') return refused;
        server.rate(id, (input.rating as Rating | null) ?? null);
        return [204, undefined];
      }
    }
    if (rest[0] === 'agreements' && rest[2] === 'next-step') {
      if (role !== 'assistant') return refused;
      server.setNextStep(String(rest[1]), {
        next_step: String(input.next_step ?? ''),
        next_step_on: (input.next_step_on as string | null) ?? null,
      });
      return [204, undefined];
    }
    return [404, { detail: `нет пути ${method} ${path}` }];
  } catch (error) {
    return [422, { detail: error instanceof Error ? error.message : String(error) }];
  }
}

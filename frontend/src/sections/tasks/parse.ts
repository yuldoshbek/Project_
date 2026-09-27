/**
 * Разбор строки задачи — правила ТЗ 7: тип, срок и ответственный из одной фразы, без
 * внешних моделей.
 *
 *     «к пятнице рассмотрение проекта постановления Минэкологии, Каримов»
 *       → тип «Рассмотрение и визирование», срок — ближайшая пятница, ответственный Каримов А.
 *
 * Пока экран на утверждении, правила живут здесь и работают на вымышленных данных. После
 * утверждения они переезжают в домен сервера (`POST /api/v1/tasks/parse`) вместе с
 * примерами из `parse.test.ts`: разбор — правило предметной области, и у экрана и у захвата
 * с телефона оно должно быть одно.
 *
 * Разбор только предлагает. Каждое распознанное — отдельная подсказка, которую человек
 * видит до сохранения и может поправить: ошибка разбора не должна молча стать сроком.
 */

import type { ParsedLine, Ref, TaskType } from './model';

const DAY_MS = 86_400_000;

function shift(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

function weekday(day: string): number {
  // 0 — понедельник: неделя в Узбекистане начинается с понедельника.
  return (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/** Дни недели во всех падежах, в которых их говорят: «к пятнице», «в пятницу», «до среды». */
const WEEKDAYS: { pattern: string; index: number }[] = [
  { pattern: 'понедельник[аиу]?', index: 0 },
  { pattern: 'вторник[аиу]?', index: 1 },
  { pattern: 'сред[аеуы]', index: 2 },
  { pattern: 'четверг[аиу]?', index: 3 },
  { pattern: 'пятниц[аеуы]', index: 4 },
  { pattern: 'суббот[аеуы]', index: 5 },
  { pattern: 'воскресень[еяю]', index: 6 },
];

const MONTHS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
];

/** Предлог перед сроком — уходит из названия вместе со сроком. */
const PREP = '(?:(?:к|до|в|во|на|не позднее)\\s+)?';

/** Граница слова для кириллицы: `\b` в JavaScript её не знает. */
const START = '(?<![\\p{L}\\d])';
const END = '(?![\\p{L}\\d])';

interface Found {
  due: string;
  fragment: string;
}

/**
 * Дата: либо полная дата (день и месяц задан), либо ближайшая в будущем. «15.03» в
 * октябре — это март следующего года, а не прошедший: срок в прошлом никто не ставит.
 */
function dated(today: string, day: number, month: number, year?: number): string | null {
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const thisYear = Number(today.slice(0, 4));
  let candidate = `${year ?? thisYear}-${pad(month)}-${pad(day)}`;
  if (Number.isNaN(Date.parse(`${candidate}T00:00:00Z`))) return null;
  if (new Date(`${candidate}T00:00:00Z`).getUTCDate() !== day) return null;
  if (year === undefined && candidate < today)
    candidate = `${thisYear + 1}-${pad(month)}-${pad(day)}`;
  return candidate;
}

function findDue(text: string, today: string): Found | null {
  const rules: { regex: RegExp; due: (match: RegExpExecArray) => string | null }[] = [
    { regex: new RegExp(`${START}${PREP}послезавтра${END}`, 'iu'), due: () => shift(today, 2) },
    { regex: new RegExp(`${START}${PREP}завтра${END}`, 'iu'), due: () => shift(today, 1) },
    { regex: new RegExp(`${START}${PREP}сегодня${END}`, 'iu'), due: () => today },
    {
      regex: new RegExp(`${START}через\\s+(\\d{1,3})\\s+(?:дн(?:я|ей)|день)${END}`, 'iu'),
      due: (match) => shift(today, Number(match[1])),
    },
    {
      regex: new RegExp(`${START}через\\s+(\\d{1,2})\\s+недел[иью]${END}`, 'iu'),
      due: (match) => shift(today, 7 * Number(match[1])),
    },
    { regex: new RegExp(`${START}через\\s+неделю${END}`, 'iu'), due: () => shift(today, 7) },
    {
      // Конец недели — пятница этой недели; сказанное в пятницу — сегодня, в выходные —
      // следующая пятница: суббота и воскресенье в аппарате не рабочие.
      regex: new RegExp(`${START}${PREP}конц[ау]\\s+недели${END}`, 'iu'),
      due: () => shift(today, (4 - weekday(today) + 7) % 7),
    },
    {
      regex: new RegExp(`${START}${PREP}конц[ау]\\s+месяца${END}`, 'iu'),
      due: () => {
        const [year, month] = today.split('-').map(Number) as [number, number];
        return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
      },
    },
    {
      regex: new RegExp(`${START}${PREP}(\\d{1,2})\\.(\\d{1,2})(?:\\.(\\d{4}))?${END}`, 'iu'),
      due: (match) =>
        dated(today, Number(match[1]), Number(match[2]), match[3] ? Number(match[3]) : undefined),
    },
    {
      regex: new RegExp(
        `${START}${PREP}(\\d{1,2})\\s+(${MONTHS.join('|')})(?:\\s+(\\d{4}))?${END}`,
        'iu',
      ),
      due: (match) =>
        dated(
          today,
          Number(match[1]),
          MONTHS.indexOf(match[2]!.toLowerCase()) + 1,
          match[3] ? Number(match[3]) : undefined,
        ),
    },
    ...WEEKDAYS.map(({ pattern, index }) => ({
      // День недели — ближайший впереди: «в пятницу», сказанное в пятницу, — это через
      // неделю; сегодняшний срок называют словом «сегодня».
      regex: new RegExp(`${START}${PREP}${pattern}${END}`, 'iu'),
      due: () => shift(today, (index - weekday(today) + 7) % 7 || 7),
    })),
  ];

  for (const rule of rules) {
    const match = rule.regex.exec(text);
    if (!match) continue;
    const due = rule.due(match);
    if (due) return { due, fragment: match[0] };
  }
  return null;
}

/**
 * Типы задач по ключевым словам (ТЗ 3.9). Порядок важен: «внесение в Кабмин» раньше
 * «согласования», потому что строка «согласовать и внести в Кабмин» — про внесение.
 */
const TYPE_RULES: { code: string; pattern: RegExp }[] = [
  { code: 'cabinet_submission', pattern: /кабмин|кабинет\s+министров|внес[теиё]/iu },
  { code: 'ijro_report', pattern: /ижро|сведени[яй]\s+по\s+поручени|по\s+поручению/iu },
  { code: 'technical_spec', pattern: /(?<![\p{L}])тз(?![\p{L}])|техническ\p{L}*\s+задани/iu },
  { code: 'review_and_endorse', pattern: /рассмотр|визир/iu },
  { code: 'approval', pattern: /согласов/iu },
  { code: 'analytical_note', pattern: /справк|аналитическ|информаци/iu },
  { code: 'site_visit', pattern: /выезд|командиров|полигон/iu },
  { code: 'request_or_survey', pattern: /запрос|опрос/iu },
  { code: 'subplatform_upload', pattern: /выгруз|субплатформ/iu },
  { code: 'participant_selection', pattern: /отбор/iu },
];

function findType(text: string, types: TaskType[]): { code: string; fragment: string } | null {
  const known = new Set(types.map((type) => type.code));
  for (const rule of TYPE_RULES) {
    const match = rule.pattern.exec(text);
    if (match && known.has(rule.code)) return { code: rule.code, fragment: match[0] };
  }
  return null;
}

/**
 * Ответственный — по фамилии в любом падеже: «Каримов», «Каримову», «Юсуповой». Инициалы
 * рядом уходят вместе с фамилией. Две подходящие фамилии — не угадываем: одинаковые
 * фамилии склеивать нельзя (CLAUDE.md), выбор остаётся человеку.
 */
function findAssignee(text: string, people: Ref[]): { id: string; fragment: string } | null {
  const hits: { id: string; fragment: string; exact: boolean }[] = [];
  for (const person of people) {
    const surname = person.name.split(/\s+/)[0]!.toLowerCase();
    const stem = surname.endsWith('а') ? surname.slice(0, -1) : surname;
    const regex = new RegExp(
      `${START}(${stem}\\p{L}{0,3})${END}(?:\\s+(?:\\p{Lu}\\.\\s?){1,2})?`,
      'giu',
    );
    for (const match of text.matchAll(regex)) {
      hits.push({
        id: person.id,
        fragment: match[0].trimEnd(),
        exact: match[1]!.toLowerCase() === surname,
      });
    }
  }
  const people_ = new Set(hits.map((hit) => hit.id));
  if (people_.size === 1) return hits[0]!;
  // Точное совпадение сильнее падежной формы: «Юсупова» — это Юсупова, а не Юсупов.
  const exact = hits.filter((hit) => hit.exact);
  if (new Set(exact.map((hit) => hit.id)).size === 1) return exact[0]!;
  return null;
}

/** Название — строка без срока и ответственного, с заглавной буквы и без висящих знаков. */
function titleOf(text: string, cut: (string | null)[]): string {
  let rest = text;
  for (const fragment of cut) if (fragment) rest = rest.replace(fragment, ' ');
  rest = rest
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.;:])/g, '$1')
    .replace(/^[\s,.;:—–-]+|[\s,.;:—–-]+$/g, '');
  return rest ? rest.charAt(0).toLocaleUpperCase('ru') + rest.slice(1) : '';
}

export function parseLine(
  text: string,
  { today, people, types }: { today: string; people: Ref[]; types: TaskType[] },
): ParsedLine {
  const due = findDue(text, today);
  const assignee = findAssignee(text, people);
  const type = findType(text, types);
  return {
    title: titleOf(text, [due?.fragment ?? null, assignee?.fragment ?? null]),
    type_code: type?.code ?? null,
    due_on: due?.due ?? null,
    assignee_id: assignee?.id ?? null,
    matched: {
      type: type?.fragment ?? null,
      due: due?.fragment ?? null,
      assignee: assignee?.fragment ?? null,
    },
  };
}

/**
 * Вымышленный сервер раздела «Календарь» — пока экран не утверждён и API нет.
 *
 * Правило блока: сначала экран на вымышленных данных, заказчик смотрит, потом API под
 * утверждённый экран (CLAUDE.md, цикл блока). Сроки проектов, вехи, задачи и решения —
 * вымышленной базы (`backend/app/demo.py`) после визита, как их видит Пульт в день загрузки:
 * срок в днях от сегодня, ступени те же, что у `metrics.ladder`, — на превью Пульт и
 * Календарь показывают одну и ту же запись одинаково. Как в базе, годовые отчёты Стратегии
 * — по 15 февраля, а годы в названиях программ — из их же сроков: записанные числом, они
 * разошлись бы с базой, загруженной в другой день. Взяты сроки, до которых календарь
 * листается: от прошлого месяца до горизонта. Годовые циклы выдуманы: в базе их нет.
 *
 * Правила повторяют сервер, чтобы экран утверждали на правильных числах: ступени —
 * `domain/attention`, даты циклов — `domain/cycles`, горячий день — порог незакрытых сроков
 * в один день (допущение V15). После утверждения файл удаляется, считать начинает сервер.
 */

import { LADDER, type DecisionKind, type Step } from '@/sections/pult/model';
import { AGENCY_TIMEZONE } from '@/shared/time';

import {
  KINDS,
  type CalendarItem,
  type CalendarView,
  type CycleDetail,
  type CyclePreview,
  type CycleRuleFields,
  type CycleSummary,
  type HotDay,
  type ItemKind,
  type NewCycle,
  type Ref,
} from './model';

const DAY_MS = 86_400_000;
const BURN_DAYS = 7;
const HOT_THRESHOLD = 3;
const HOT_WINDOW_DAYS = 28;
const HORIZON_MONTHS = 12;

function todayInTashkent(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(now);
}

export function shift(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

function plusMonths(day: string, months: number): string {
  const [year, month, date] = day.split('-').map(Number) as [number, number, number];
  const total = month - 1 + months;
  const nextYear = year + Math.floor(total / 12);
  const nextMonth = (total % 12) + 1;
  const last = new Date(Date.UTC(nextYear, nextMonth, 0)).getUTCDate();
  return `${nextYear}-${String(nextMonth).padStart(2, '0')}-${String(Math.min(date, last)).padStart(2, '0')}`;
}

const PEOPLE: Record<string, Ref> = {
  abdullaeva: { id: 'p-abdullaeva', name: 'Абдуллаева Н.' },
  karimov: { id: 'p-karimov', name: 'Каримов А.' },
  rakhimov: { id: 'p-rakhimov', name: 'Рахимов Ш.' },
  tursunov: { id: 'p-tursunov', name: 'Турсунов Б.' },
  yusupova: { id: 'p-yusupova', name: 'Юсупова Д.' },
};

/**
 * Проекты и программы базы: ключ — как в `backend/app/demo.py`. У программы в названии
 * годы начала и срока (`{start}`, `{due}`) — считаются от сегодня по её же срокам, как
 * `demo.title_of`.
 */
const PROJECTS: Record<
  string,
  { title: string; who: string; done?: true; start?: number; due?: number }
> = {
  mission: { title: 'Спутниковая миссия «Навоий-2»', who: 'karimov' },
  drought: { title: 'Цикл мониторинга: засуха-2026', who: 'rakhimov' },
  crops: { title: 'Пилот: мониторинг посевов', who: 'abdullaeva' },
  standard: { title: 'Стандарт на снимки ДЗЗ', who: 'yusupova' },
  air: { title: 'Совместная программа наблюдения за качеством воздуха', who: 'yusupova' },
  aerial: { title: 'Заказ услуги: аэрофотосъёмка Ферганской долины', who: 'tursunov' },
  floods: { title: 'Цикл мониторинга: паводки', who: 'rakhimov' },
  forest: { title: 'Цикл мониторинга: лесные пожары', who: 'tursunov' },
  atlas: { title: 'Цифровой атлас земель', who: 'tursunov' },
  uav: { title: 'Заказ услуги: съёмка с БПЛА Каракалпакстана', who: 'karimov' },
  cadastre: { title: 'Пилот с кадастром: границы участков', who: 'abdullaeva' },
  snow: { title: 'Цикл мониторинга: снежный покров', who: 'rakhimov' },
  glossary: { title: 'Терминологический стандарт ДЗЗ', who: 'yusupova', done: true },
  hydro: { title: 'Поручение по мониторингу водохранилищ', who: 'karimov', done: true },
  iac: {
    title: 'IAC-{due}: Международный астронавтический конгресс в Ташкенте',
    who: 'yusupova',
    due: 740,
  },
  infrastructure: {
    title: 'Наземная инфраструктура ДЗЗ {start}–{due}',
    who: 'tursunov',
    start: -258,
    due: 1430,
  },
  staff: {
    title: 'Подготовка кадров космической отрасли {start}–{due}',
    who: 'abdullaeva',
    start: -237,
    due: 1370,
  },
  catalogue: {
    title: 'Национальный каталог космических снимков {start}–{due}',
    who: 'yusupova',
    start: -600,
    due: 45,
  },
  strategy: {
    title: 'Стратегия развития космической деятельности до {due} года',
    who: 'rakhimov',
    due: 3200,
  },
  digital: {
    title: 'Цифровизация агентства {start}–{due}',
    who: 'yusupova',
    done: true,
    start: -1100,
    due: -282,
  },
  interns: { title: 'Кадры: стажировки в Центре мониторинга', who: 'abdullaeva' },
  calibration: { title: 'Пилот: калибровка снимков', who: 'karimov' },
  lab: { title: 'Учебная лаборатория ДЗЗ в вузе', who: 'abdullaeva' },
  insurance: { title: 'Страхование запуска и работы на орбите', who: 'tursunov' },
  venue: { title: 'Конгресс IAC: площадка и логистика', who: 'tursunov' },
  science: { title: 'Конгресс IAC: научная программа', who: 'rakhimov' },
  volunteers: { title: 'Конгресс IAC: волонтёры и кадры', who: 'abdullaeva' },
  station: { title: 'Приём наземной станции по соглашению о сотрудничестве', who: 'rakhimov' },
  portal: { title: 'Геопортал агентства', who: 'tursunov' },
  health: { title: 'Пилот с Минздравом: мониторинг вспышек', who: 'abdullaeva' },
  geodata: { title: 'Постановление о порядке обмена геоданными', who: 'yusupova' },
};

function projectTitle(key: string, today: string): string {
  const { title, start = 0, due = 0 } = PROJECTS[key]!;
  return title
    .replace('{start}', shift(today, start).slice(0, 4))
    .replace('{due}', shift(today, due).slice(0, 4));
}

function projectRef(key: string, today: string): { id: string; title: string } {
  return { id: `pr-${key}`, title: projectTitle(key, today) };
}

/**
 * Отметки записи. Ступени «просрочено» и «горит» выводятся из срока, как на сервере;
 * остальное задаёт база: вопрос руководителю (`ask` — дней ждёт), тишина и «зависит от
 * чужих» — дней без движения.
 */
interface Marks {
  done?: true;
  ask?: number;
  silent?: number;
  blocked?: number;
}

const DONE: Marks = { done: true };

/** Срок — дней от сегодня или день календаря: (лет от текущего, месяц, день). */
type Due = number | readonly [number, number, number];

interface Spec extends Marks {
  kind: Exclude<ItemKind, 'cycle'>;
  due: Due;
  /** У срока проекта — `null`: название из `PROJECTS`; `{year}` — год, за который отчёт. */
  title: string | null;
  project: string | null;
  who: string | null;
  decision_kind?: DecisionKind;
}

function m(due: Due, title: string, project: string, marks: Marks = {}): Spec {
  return { kind: 'milestone', due, title, project, who: PROJECTS[project]!.who, ...marks };
}

function p(due: number, project: string, marks: Marks = {}): Spec {
  return { kind: 'project', due, title: null, project, who: PROJECTS[project]!.who, ...marks };
}

function t(
  due: number,
  title: string,
  project: string | null,
  who: string | null,
  marks: Marks = {},
): Spec {
  return { kind: 'task', due, title, project, who, ...marks };
}

function d(
  due: number,
  title: string | null,
  project: string | null,
  who: string | null,
  decision_kind: DecisionKind,
  marks: Marks = {},
): Spec {
  return { kind: 'decision', due, title, project, who, decision_kind, ...marks };
}

/**
 * Сроки базы по дню. Горячие дни на четыре недели — сегодня, через 10 и через 20 дней;
 * дальше — через 30, 40, 45 и 60: за окном карточки, но горячие на сетке своего месяца.
 * Через 6 дней стажировки кончаются итоговой вехой в день срока проекта — один срок, не
 * два: день не горячий. Годовые отчёты Стратегии — в конце: их день — по календарю.
 */
const SPECS: Spec[] = [
  m(-63, 'План исполнения', 'hydro', DONE),
  m(-58, 'Разработка проекта стандарта', 'standard', DONE),
  m(-50, 'Разработка проекта акта', 'geodata', DONE),
  m(-40, 'Получение космических снимков', 'drought', DONE),
  m(-30, 'Программа и отбор участников', 'lab', DONE),
  m(-26, 'Первая группа магистрантов зачислена', 'staff', DONE),
  m(-25, 'Исполнение', 'hydro', DONE),
  m(-24, 'Обучение', 'interns', DONE),
  m(-20, 'Согласование с министерствами и ведомствами', 'geodata', DONE),
  m(-20, 'Утверждение и регистрация', 'glossary', DONE),
  m(-15, 'Переговоры и проект документа', 'station', DONE),
  m(-10, 'Доклад об исполнении', 'hydro', DONE),
  m(-10, 'Обработка и анализ данных', 'drought', DONE),
  m(-10, 'Получение космических снимков', 'snow', DONE),
  m(-10, 'Соглашение с отраслью', 'crops', DONE),
  m(-10, 'Техническое задание', 'atlas', DONE),
  p(-10, 'glossary', DONE),
  m(-9, 'Приёмка опытного образца платформы', 'portal'),
  m(-8, 'Площадка станции приёма в Самарканде', 'infrastructure'),
  p(-8, 'hydro', DONE),
  m(-7, 'Заявка и техническое задание', 'aerial', DONE),
  m(-5, 'Разработка ТЗ', 'mission', DONE),
  t(-3, 'Аналитическая справка по засухе для Кабинета министров', 'drought', 'rakhimov'),
  d(-1, 'Поторопить: выезд на полигон в Джизаке', 'calibration', 'karimov', 'hurry'),
  t(-1, 'Сведения по поручению ПФ-155 §5.1', null, 'rakhimov'),
  m(0, 'Получение космических снимков', 'floods'),
  t(0, 'Отбор участников пилота с Минсельхозом', 'crops', 'abdullaeva'),
  t(0, 'Позвонить в Минфин по смете миссии на следующий год', null, 'karimov'),
  t(0, 'Разработка ТЗ спутниковой группировки', 'mission', 'karimov', DONE),
  t(1, 'Сведения для Администрации Президента по мониторингу водохранилищ', null, 'yusupova'),
  t(1, 'Сведения по поручению ПФ-155 для Администрации Президента', 'drought', 'rakhimov', DONE),
  m(2, 'Внесение стандарта в агентство «Узстандарт»', 'standard'),
  m(3, 'Согласование ТЗ на спутниковую группировку', 'mission', { ask: 6 }),
  t(3, 'Согласование проекта постановления с Минэкологии', 'geodata', 'yusupova'),
  t(4, 'Выезд на полигон в Джизаке', 'calibration', 'karimov'),
  t(5, 'Выгрузка данных в субплатформу', 'portal', 'tursunov'),
  t(5, 'Запрос сведений у хокимиятов о паводках', 'floods', 'rakhimov'),
  m(6, 'Итоги и отчёт', 'interns'),
  p(6, 'interns'),
  t(6, 'Внесение проекта постановления в Кабинет министров', 'geodata', 'yusupova', { ask: 2 }),
  m(8, 'Заявка и техническое задание', 'uav'),
  m(8, 'Презентация Ташкента на ежегодном конгрессе IAC', 'iac'),
  m(9, 'Договор', 'aerial'),
  m(10, 'Архив снимков перенесён', 'catalogue'),
  m(10, 'Внесение в Кабинет Министров', 'geodata'),
  m(10, 'Переговоры и проект документа', 'air'),
  m(10, 'Соглашение с отраслью', 'calibration'),
  t(12, 'Сводка по паводкам за сентябрь', 'floods', 'rakhimov'),
  m(15, 'Поиск и предпросмотр снимков', 'catalogue'),
  t(18, 'Договор с исполнителем аэрофотосъёмки', 'aerial', 'tursunov', { silent: 21 }),
  m(20, 'Интеграция с геопорталом', 'catalogue'),
  m(20, 'Обработка и анализ данных', 'snow'),
  m(20, 'Опытная эксплуатация', 'portal'),
  m(20, 'Отчёт по результатам мониторинга', 'drought'),
  p(20, 'drought'),
  t(20, 'ТЗ на модуль каталога снимков', 'portal', 'tursunov'),
  m(21, 'Соглашение с отраслью', 'cadastre'),
  m(24, 'Договор', 'uav'),
  m(25, 'Доступ ведомств к каталогу', 'catalogue'),
  t(25, 'Рассмотрение замечаний к стандарту', 'standard', 'yusupova'),
  m(26, 'Получение космических снимков', 'forest'),
  m(30, 'Нагрузочное испытание каталога', 'catalogue'),
  m(30, 'Обработка и анализ данных', 'floods'),
  m(30, 'Соглашение с отраслью', 'health'),
  t(30, 'План работ по группировке на квартал', 'mission', 'karimov'),
  m(33, 'Три варианта площадки', 'venue'),
  m(35, 'Опытная эксплуатация каталога', 'catalogue'),
  m(40, 'Принятие', 'geodata'),
  m(40, 'Регламент пополнения каталога утверждён', 'catalogue'),
  p(40, 'geodata', { ask: 2 }),
  t(40, 'Опросник для хокимиятов по снежному покрову', 'snow', 'rakhimov'),
  m(45, 'Ввод каталога в эксплуатацию', 'catalogue'),
  m(45, 'Внутригосударственное согласование', 'station'),
  p(45, 'catalogue'),
  t(45, 'Программа занятий для стажёров', 'interns', 'abdullaeva'),
  m(50, 'Отчёт по результатам мониторинга', 'snow'),
  m(50, 'Смета конгресса на следующий год внесена в Кабмин', 'iac', { ask: 1 }),
  p(50, 'snow'),
  m(54, 'Оказание услуги', 'aerial'),
  m(56, 'Обработка и анализ данных', 'forest'),
  m(60, 'Ввод в эксплуатацию', 'portal'),
  m(60, 'Обучение', 'lab'),
  m(60, 'Отчёт по результатам мониторинга', 'floods'),
  p(60, 'portal'),
  p(60, 'floods'),
  m(62, 'Утверждение и регистрация', 'standard'),
  p(62, 'standard'),
  m(69, 'Акт приёмки', 'aerial'),
  m(69, 'Оказание услуги', 'uav'),
  p(69, 'aerial', { silent: 21 }),
  m(70, 'Внутригосударственное согласование', 'air'),
  m(74, 'Проект центра обработки данных', 'infrastructure'),
  m(75, 'Подписание', 'station'),
  p(75, 'station'),
  m(80, 'Проведение пилота', 'crops'),
  m(80, 'Разработка', 'atlas'),
  m(84, 'Акт приёмки', 'uav'),
  p(84, 'uav'),
  m(85, 'Дорожная карта на два следующих года внесена', 'strategy'),
  m(86, 'Отчёт по результатам мониторинга', 'forest'),
  p(86, 'forest'),
  m(90, 'Итоги и отчёт', 'lab'),
  p(90, 'lab', { silent: 30 }),
  m(100, 'Подписание', 'air'),
  m(100, 'Проведение пилота', 'calibration'),
  p(100, 'air', { blocked: 25 }),
  m(110, 'Опытная эксплуатация', 'atlas'),
  m(110, 'Отчёт и предложения по масштабированию', 'crops'),
  p(110, 'crops'),
  m(111, 'Проведение пилота', 'cadastre'),
  m(120, 'Договор с изготовителем', 'mission'),
  m(120, 'Проведение пилота', 'health'),
  p(120, 'health'),
  m(127, 'Технические комитеты сформированы', 'science'),
  m(130, 'Отчёт и предложения по масштабированию', 'calibration'),
  p(130, 'calibration'),
  m(140, 'Ввод в эксплуатацию', 'atlas'),
  p(140, 'atlas'),
  m(141, 'Отчёт и предложения по масштабированию', 'cadastre'),
  p(141, 'cadastre'),
  m(150, 'Отчёт и предложения по масштабированию', 'health'),
  m(155, 'Договор с площадкой', 'iac'),
  m(155, 'Запрос предложений страховщиков', 'insurance'),
  m(276, 'Выпуск первого потока стажёров', 'staff'),
  m(276, 'Монтаж станции приёма', 'infrastructure'),
  m(339, 'Набор волонтёров объявлен', 'volunteers'),
  m(339, 'Приём докладов открыт', 'iac'),
  m(369, 'Передача флага IAC', 'iac'),
  m(397, 'Каталог снимков в геопортале', 'infrastructure'),
  m([0, 2, 15], 'Отчёт об исполнении за {year} год', 'strategy'),
  m([1, 2, 15], 'Отчёт об исполнении за {year} год', 'strategy'),
  m([2, 2, 15], 'Отчёт об исполнении за {year} год', 'strategy'),
  m([3, 2, 15], 'Отчёт об исполнении за {year} год', 'strategy'),
  m([4, 2, 15], 'Отчёт об исполнении за {year} год', 'strategy'),
];

interface CycleSpec extends CycleRuleFields {
  id: string;
  title: string;
  project?: string;
  who?: string;
}

/**
 * Циклы выдуманы — и не повторяют сроков базы: годовой отчёт по Стратегии там вехами
 * «Отчёт об исполнении за … год», и цикл на тот же день показал бы одно дело дважды.
 * Переаттестация — «раз в два года», и за год вперёд дат у неё нет: такой цикл виден только
 * в списке «Годовые циклы».
 */
function cycleSpecs(year: number): CycleSpec[] {
  return [
    {
      id: 'cy-cabinet',
      title: 'Сведения в Кабмин по программе космического мониторинга',
      rule: 'quarterly',
      month: 1,
      day: 5,
      every_years: 1,
      anchor_year: year,
      who: 'rakhimov',
    },
    {
      id: 'cy-images',
      title: 'Сводка о снимках, выданных ведомствам',
      rule: 'quarterly',
      month: 1,
      day: 12,
      every_years: 1,
      anchor_year: year,
      who: 'tursunov',
    },
    {
      id: 'cy-decree',
      title: 'Годовой отчёт об исполнении Указа ПФ-155',
      rule: 'annual',
      month: 1,
      day: 20,
      every_years: 1,
      anchor_year: year,
      who: 'yusupova',
    },
    {
      id: 'cy-datasets',
      title: 'Пересмотр перечня открытых данных ДЗЗ',
      rule: 'every_n_years',
      month: 3,
      day: 1,
      every_years: 3,
      anchor_year: year + 1,
      who: 'tursunov',
    },
    {
      id: 'cy-operators',
      title: 'Переаттестация операторов станции приёма',
      rule: 'every_n_years',
      month: 11,
      day: 15,
      every_years: 2,
      anchor_year: year - 1,
      project: 'station',
      who: 'rakhimov',
    },
  ];
}

interface Cycle extends CycleSpec {
  active: boolean;
  version: number;
}

/** Даты цикла с `since` по `until` включительно — `domain/cycles._dates`. */
function datesBetween(cycle: CycleRuleFields, since: string, until: string): string[] {
  // Дня −3 или 1,5 нет ни в одном месяце: сервер пропускает их так же, как 31 февраля.
  if (!Number.isInteger(cycle.day) || cycle.day < 1) return [];
  const every = Math.max(cycle.every_years, 1);
  const months = cycle.rule === 'quarterly' ? [1, 4, 7, 10] : [cycle.month];
  const found: string[] = [];
  for (let year = Number(since.slice(0, 4)); year <= Number(until.slice(0, 4)); year += 1) {
    // Годы до начала не в счёт: подпись цикла говорит «с такого-то года».
    if (
      cycle.rule === 'every_n_years' &&
      (year < cycle.anchor_year || (year - cycle.anchor_year) % every !== 0)
    ) {
      continue;
    }
    for (const month of months) {
      const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
      // 31 февраля не существует: дата пропускается, как на сервере.
      if (cycle.day > last) continue;
      const day = `${year}-${String(month).padStart(2, '0')}-${String(cycle.day).padStart(2, '0')}`;
      if (day >= since && day <= until) found.push(day);
    }
  }
  return found.sort();
}

/** Даты цикла на год вперёд — `domain/cycles.occurrences`. */
export function occurrences(cycle: CycleRuleFields, since: string): string[] {
  return datesBetween(cycle, since, plusMonths(since, HORIZON_MONTHS));
}

/**
 * Ближайшая дата и за горизонтом — `domain/cycles.next_date`. Четыре шага цикла считаются
 * от первого года, который цикл признаёт: у цикла «с 2036 года» от текущего их не хватило
 * бы, и настоящий день выглядел бы несуществующим.
 */
export function nextDate(cycle: CycleRuleFields, since: string): string | null {
  const year = Number(since.slice(0, 4));
  const start = cycle.rule === 'every_n_years' ? Math.max(year, cycle.anchor_year) : year;
  const until = `${start + 4 * Math.max(cycle.every_years, 1) + 1}-12-31`;
  return datesBetween(cycle, since, until)[0] ?? null;
}

/** День срока: дни от сегодня или день календаря в году от текущего — `demo._day`. */
function dateOf(due: Due, today: string): string {
  if (typeof due === 'number') return shift(today, due);
  const [years, month, day] = due;
  const year = Number(today.slice(0, 4)) + years;
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/** Порядок — порядок лестницы: вопрос руководителю важнее сорванного срока. */
function stepOf(spec: Spec, left: number, done: boolean): { step: Step | null; deviation: number } {
  if (done) return { step: null, deviation: 0 };
  if (spec.ask !== undefined) return { step: 'awaiting_decision', deviation: spec.ask };
  if (left < 0) return { step: 'overdue', deviation: -left };
  if (left <= BURN_DAYS) return { step: 'burning', deviation: left };
  if (spec.blocked !== undefined) return { step: 'blocked_by_others', deviation: spec.blocked };
  if (spec.silent !== undefined) return { step: 'silent', deviation: spec.silent };
  return { step: null, deviation: 0 };
}

function rank(item: CalendarItem): [string, number, number, string] {
  return [
    item.date,
    item.step ? LADDER.indexOf(item.step) : LADDER.length,
    KINDS.indexOf(item.kind),
    item.title ?? '',
  ];
}

function byRank(left: CalendarItem, right: CalendarItem): number {
  const a = rank(left);
  const b = rank(right);
  for (let index = 0; index < a.length; index += 1) {
    if (a[index]! < b[index]!) return -1;
    if (a[index]! > b[index]!) return 1;
  }
  return 0;
}

function stepRank(step: Step | null): number {
  return step ? LADDER.indexOf(step) : LADDER.length;
}

/**
 * Срок проекта в день его же вехи — одна запись: веха с отметкой «и срок проекта» (V15).
 * Итоговая веха обычно и стоит в день срока, и двумя строками это одно дело считалось бы
 * дважды: любой конец проекта плюс одна чужая задача делал бы день «тесным», а строк под
 * «горячий день: N сроков» было бы больше N. Ступень — старшая из двух: вопрос по проекту
 * не пропадает оттого, что строка — веха.
 */
function mergeEnds(items: CalendarItem[]): CalendarItem[] {
  const merged = new Set<CalendarItem>();
  for (const end of items) {
    if (end.kind !== 'project') continue;
    const mark = items.find(
      (item) =>
        item.kind === 'milestone' &&
        item.date === end.date &&
        item.target.id === end.target.id &&
        item.is_done === end.is_done,
    );
    if (!mark) continue;
    mark.ends_project = true;
    if (stepRank(end.step) < stepRank(mark.step)) {
      mark.step = end.step;
      mark.deviation = end.deviation;
    }
    merged.add(end);
  }
  return items.filter((item) => !merged.has(item));
}

function hotOf(date: string, items: CalendarItem[]): HotDay | null {
  const open = items.filter((item) => item.date === date && !item.is_done);
  if (open.length < HOT_THRESHOLD) return null;
  const kinds: HotDay['kinds'] = {};
  for (const item of open) kinds[item.kind] = (kinds[item.kind] ?? 0) + 1;
  return { date, count: open.length, kinds };
}

function hotBetween(from: string, to: string, items: CalendarItem[]): HotDay[] {
  const hot: HotDay[] = [];
  for (let day = from; day <= to; day = shift(day, 1)) {
    const found = hotOf(day, items);
    if (found) hot.push(found);
  }
  return hot;
}

export class DemoCalendar {
  private cycles: Cycle[] = [];
  private counter = 0;

  constructor(private readonly now: () => Date = () => new Date()) {
    this.reset();
  }

  reset(): void {
    const year = Number(this.today().slice(0, 4));
    this.cycles = cycleSpecs(year).map((spec) => ({ ...spec, active: true, version: 1 }));
    this.counter = 0;
  }

  private today(): string {
    return todayInTashkent(this.now());
  }

  /** Все даты с `from` по `to`: сроки базы и даты циклов, прошедшие тоже — без ступени. */
  private between(today: string, from: string, to: string): CalendarItem[] {
    const items: CalendarItem[] = [];
    SPECS.forEach((spec, index) => {
      const date = dateOf(spec.due, today);
      if (date < from || date > to) return;
      const owner =
        spec.project && spec.kind !== 'project' ? projectRef(spec.project, today) : null;
      // Веха по календарю пройдена, если её день позади, — как в базе.
      const done = spec.done === true || (typeof spec.due !== 'number' && date < today);
      items.push({
        id: `it-${index}`,
        kind: spec.kind,
        date,
        title:
          spec.kind === 'project'
            ? projectTitle(spec.project!, today)
            : (spec.title?.replace('{year}', String(Number(date.slice(0, 4)) - 1)) ?? null),
        decision_kind: spec.decision_kind ?? null,
        owner,
        target:
          spec.kind === 'task'
            ? { kind: 'task', id: `ts-${index}` }
            : spec.kind === 'decision'
              ? { kind: 'decision', id: `dc-${index}` }
              : { kind: 'project', id: `pr-${spec.project!}` },
        responsible: spec.who ? PEOPLE[spec.who]! : null,
        ...stepOf(spec, daysBetween(today, date), done),
        is_done: done,
        ends_project: false,
        cycle: null,
      });
    });
    const horizon = plusMonths(today, HORIZON_MONTHS);
    for (const cycle of this.cycles) {
      if (!cycle.active) continue;
      for (const day of datesBetween(cycle, from, to < horizon ? to : horizon)) {
        items.push({
          id: `${cycle.id}:${day}`,
          kind: 'cycle',
          date: day,
          title: cycle.title,
          decision_kind: null,
          owner: cycle.project ? projectRef(cycle.project, today) : null,
          target: { kind: 'cycle', id: cycle.id },
          responsible: cycle.who ? PEOPLE[cycle.who]! : null,
          step: null,
          deviation: 0,
          is_done: false,
          ends_project: false,
          cycle: {
            rule: cycle.rule,
            month: cycle.month,
            day: cycle.day,
            every_years: cycle.every_years,
            anchor_year: cycle.anchor_year,
          },
        });
      }
    }
    return mergeEnds(items).sort(byRank);
  }

  view(range: { from: string; to: string }): CalendarView {
    const moment = this.now();
    const today = todayInTashkent(moment);
    const window = shift(today, HOT_WINDOW_DAYS - 1);
    const items = this.between(today, range.from, range.to);
    const ahead = this.between(today, today, window);
    const overdue = this.between(today, shift(today, -10_000), shift(today, -1)).filter(
      (item) => !item.is_done && item.kind !== 'cycle',
    );

    return {
      as_of: moment.toISOString(),
      range,
      items,
      overdue,
      hot_days: hotBetween(range.from < today ? today : range.from, range.to, items),
      hot_ahead: hotBetween(today, window, ahead),
      hot_window_days: HOT_WINDOW_DAYS,
      hot_threshold: HOT_THRESHOLD,
      horizon_to: plusMonths(today, HORIZON_MONTHS),
      people: Object.values(PEOPLE),
      projects: Object.entries(PROJECTS)
        .filter(([, project]) => !project.done)
        .map(([key]) => projectRef(key, today)),
      is_demo: true,
    };
  }

  private summary(found: Cycle): CycleSummary {
    return {
      id: found.id,
      title: found.title,
      rule: found.rule,
      month: found.month,
      day: found.day,
      every_years: found.every_years,
      anchor_year: found.anchor_year,
      owner: found.project ? projectRef(found.project, this.today()) : null,
      responsible: found.who ? PEOPLE[found.who]! : null,
      next_date: nextDate(found, this.today()),
    };
  }

  /** Все действующие циклы — по ближайшей дате; и те, у которых за год дат нет. */
  list(): CycleSummary[] {
    return this.cycles
      .filter((each) => each.active)
      .map((each) => this.summary(each))
      .sort((a, b) =>
        (a.next_date ?? '9999') === (b.next_date ?? '9999')
          ? a.title.localeCompare(b.title, 'ru')
          : (a.next_date ?? '9999') < (b.next_date ?? '9999')
            ? -1
            : 1,
      );
  }

  cycle(id: string): CycleDetail {
    const found = this.cycles.find((each) => each.id === id && each.active);
    if (!found) throw new Error('Цикл не найден: его могли отменить');
    return {
      ...this.summary(found),
      dates: occurrences(found, this.today()),
      version: found.version,
    };
  }

  /** Даты будущего цикла до записи — чтобы помощник видел, что заводит. */
  preview(input: CycleRuleFields): CyclePreview {
    const today = this.today();
    return { dates: occurrences(input, today), next_date: nextDate(input, today) };
  }

  create(input: NewCycle): CycleDetail {
    const title = input.title.trim();
    if (!title) throw new Error('Нужно название цикла');
    if (nextDate(input, this.today()) === null) {
      throw new Error('Такого дня нет ни в одном году: проверьте месяц и число');
    }
    this.counter += 1;
    const project = Object.keys(PROJECTS).find((key) => `pr-${key}` === input.project_id);
    const who = Object.entries(PEOPLE).find(([, each]) => each.id === input.responsible_id);
    const cycle: Cycle = {
      id: `cy-new-${this.counter}`,
      title,
      rule: input.rule,
      month: input.month,
      day: input.day,
      every_years: input.rule === 'every_n_years' ? input.every_years : 1,
      anchor_year: input.anchor_year,
      ...(project ? { project } : {}),
      ...(who ? { who: who[0] } : {}),
      active: true,
      version: 1,
    };
    this.cycles.push(cycle);
    return this.cycle(cycle.id);
  }

  /** Цикл отменяют, а не удаляют: запись о нём остаётся в журнале. */
  cancel(id: string, version: number): void {
    const found = this.cycles.find((each) => each.id === id && each.active);
    if (!found) throw new Error('Цикл не найден: его могли отменить');
    if (found.version !== version) throw new Error('Запись изменил помощник — обновите');
    found.active = false;
    found.version += 1;
  }
}

export const demoCalendar = new DemoCalendar();

/**
 * Повестка совещания и панели обзора на мониторе — из ответов разделов.
 *
 * Слайд — один вопрос руководителя: вопрос, ответ фразой, подробность, до пяти строк,
 * свежесть и раздел, куда идти за действием (инвариант 3). Ответ собирают те же функции, что
 * экраны разделов (`answerText` каждого раздела), — на совещании та же цифра, что в разделе
 * (инвариант 2); своих расчётов здесь нет.
 */

import type { TFunction } from 'i18next';

import { sectionPath } from '@/app/sections';
import type { CalendarView } from '@/sections/calendar/model';
import { hotDayTitle, hotText } from '@/sections/calendar/text';
import type { IdeasView } from '@/sections/ideas/model';
import { awaitingText } from '@/sections/ideas/text';
import type { IjroView } from '@/sections/ijro/model';
import { answerText as ijroAnswer } from '@/sections/ijro/text';
import type { InteractionView } from '@/sections/interaction/model';
import { answerText as interactionAnswer } from '@/sections/interaction/text';
import { LADDER, rowKey, type PultView } from '@/sections/pult/model';
import { rowTitle } from '@/sections/pult/text';
import type { ReportsView } from '@/sections/reports/model';
import { answerText as reportsAnswer } from '@/sections/reports/text';
import { formatDate, formatDateTime } from '@/shared/time';

export type AgendaSection = 'pult' | 'ijro' | 'reports' | 'interaction' | 'ideas' | 'calendar';

/**
 * Строка слайда с ключом записи: две задачи «Подготовить справку» у одного ответственного
 * дают одинаковый текст, а ключ React по тексту путал бы их при обновлении повестки.
 */
export interface Line {
  key: string;
  text: string;
}

export interface Slide {
  key: string;
  /** Раздел: подпись слайда и куда ведёт действие. */
  section: AgendaSection;
  path: string;
  question: string;
  main: string;
  detail: string | null;
  lines: Line[];
  /** Нет только у слайда без данных: свежесть показывать не у чего. */
  freshness: string | null;
  /** Ничего не горит: слайд остаётся в повестке — «всё спокойно» тоже ответ. */
  empty: boolean;
  /** Запрос раздела не прошёл: вопрос остаётся, а ответа нет. */
  failed: boolean;
  /**
   * Горячие дни для полосы на четыре недели — только у слайда Календаря: на мониторе
   * «где тесно» видно глазом раньше, чем прочитано словами (блок 4, пакет C).
   */
  strip?: { today: string; hot: { date: string; count: number }[] };
}

const LINES = 5;

/** Вопрос раздела в повестке — один и у слайда с ответом, и у слайда без данных. */
const QUESTION: Record<AgendaSection, string> = {
  pult: 'meeting.pult.question',
  ijro: 'ijro.questions.burning.title',
  reports: 'reports.questions.readiness.title',
  interaction: 'interaction.questions.not_answering.title',
  ideas: 'ideas.awaiting.title',
  calendar: 'calendar.hot.title',
};

function base(t: TFunction, section: AgendaSection) {
  return {
    key: section,
    section,
    path: sectionPath(section),
    question: t(QUESTION[section]),
    failed: false,
  };
}

/**
 * Раздел, чей запрос упал, остаётся в повестке своим вопросом. Пропавший слайд читается
 * как «там ничего не горит», а на деле там неизвестно что — и это надо видеть.
 */
export function failedSlide(t: TFunction, section: AgendaSection, detail: string): Slide {
  return {
    ...base(t, section),
    main: t('meeting.failed'),
    detail,
    lines: [],
    freshness: null,
    empty: false,
    failed: true,
  };
}

export function pultSlide(t: TFunction, view: PultView): Slide {
  const steps = LADDER.filter((step) => view.counts[step] > 0);
  return {
    ...base(t, 'pult'),
    main:
      steps.length === 0
        ? t('meeting.pult.none')
        : steps.map((step) => `${t(`pult.steps.${step}`)} ${view.counts[step]}`).join(' · '),
    detail: t('meeting.pult.onTrack', { count: view.on_track }),
    lines: view.rows.slice(0, LINES).map((row) => ({
      key: rowKey(row),
      text: `${t(`pult.steps.${row.step}`)} — ${rowTitle(t, row)}${row.responsible ? ` · ${row.responsible.name}` : ''}`,
    })),
    freshness: t('pult.asOf', { when: formatDateTime(view.as_of) }),
    empty: steps.length === 0,
  };
}

export function ijroSlide(t: TFunction, view: IjroView): Slide | null {
  const answer = view.questions.find((each) => each.key === 'burning');
  if (!answer) return null;
  const text = ijroAnswer(t, answer);
  return {
    ...base(t, 'ijro'),
    main: text.main,
    detail: text.detail,
    lines: [],
    freshness: view.table_on
      ? t('ijro.freshness', { date: formatDate(view.table_on) })
      : t('ijro.noTable'),
    empty: text.empty,
  };
}

export function reportsSlide(t: TFunction, view: ReportsView): Slide | null {
  const answer = view.questions.find((each) => each.key === 'readiness');
  if (!answer) return null;
  const text = reportsAnswer(t, answer);
  return {
    ...base(t, 'reports'),
    main: text.main,
    detail: text.detail,
    lines: [],
    freshness: t('reports.freshness', { when: formatDateTime(view.as_of) }),
    empty: text.empty,
  };
}

export function interactionSlide(t: TFunction, view: InteractionView): Slide | null {
  const answer = view.questions.find((each) => each.key === 'not_answering');
  if (!answer) return null;
  const text = interactionAnswer(t, answer);
  return {
    ...base(t, 'interaction'),
    main: text.main,
    detail: text.detail,
    lines: [],
    freshness: t('pult.asOf', { when: formatDateTime(view.as_of) }),
    empty: text.empty,
  };
}

export function ideasSlide(t: TFunction, view: IdeasView): Slide | null {
  const answer = view.questions[0];
  if (!answer) return null;
  const text = awaitingText(t, answer);
  const byId = new Map(view.items.map((each) => [each.id, each]));
  return {
    ...base(t, 'ideas'),
    main: text.main,
    detail: text.detail,
    lines: answer.rows.slice(0, LINES).flatMap((id) => {
      const idea = byId.get(id);
      return idea
        ? [{ key: id, text: `${idea.text} · ${t('ideas.waiting', { count: idea.waiting_days })}` }]
        : [];
    }),
    freshness: t('ideas.freshness', { when: formatDateTime(view.as_of) }),
    empty: answer.count === 0,
  };
}

export function calendarSlide(t: TFunction, view: CalendarView, today: string): Slide {
  const hot = view.hot_ahead;
  return {
    ...base(t, 'calendar'),
    main:
      hot.length === 0 ? t('calendar.hot.none') : t('calendar.hot.answer', { count: hot.length }),
    detail: null,
    lines: hot.slice(0, LINES).map((day) => ({
      key: day.date,
      text: `${hotDayTitle(t, day.date, today)} — ${hotText(t, day)}`,
    })),
    freshness: t('pult.asOf', { when: formatDateTime(view.as_of) }),
    empty: hot.length === 0,
    strip: { today, hot: hot.map((day) => ({ date: day.date, count: day.count })) },
  };
}

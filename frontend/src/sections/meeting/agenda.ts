/**
 * Повестка совещания и панели обзора на мониторе — из ответов разделов.
 *
 * Слайд — один вопрос руководителя: вопрос, ответ фразой, подробность, до пяти строк,
 * свежесть и раздел, куда идти за действием (инвариант 3). Ответ собирают те же функции, что
 * экраны разделов (`answerText` каждого раздела), — на совещании та же цифра, что в разделе
 * (инвариант 2); своих расчётов здесь нет.
 */

import type { TFunction } from 'i18next';

import type { CalendarView } from '@/sections/calendar/model';
import { hotDayTitle, hotText } from '@/sections/calendar/text';
import type { IdeasView } from '@/sections/ideas/model';
import { awaitingText } from '@/sections/ideas/text';
import type { IjroView } from '@/sections/ijro/model';
import { answerText as ijroAnswer } from '@/sections/ijro/text';
import type { InteractionView } from '@/sections/interaction/model';
import { answerText as interactionAnswer } from '@/sections/interaction/text';
import { LADDER, type PultView } from '@/sections/pult/model';
import { rowTitle } from '@/sections/pult/text';
import type { ReportsView } from '@/sections/reports/model';
import { answerText as reportsAnswer } from '@/sections/reports/text';
import { formatDate, formatDateTime } from '@/shared/time';

export interface Slide {
  key: string;
  /** Раздел: подпись слайда и куда ведёт действие. */
  section: 'pult' | 'ijro' | 'reports' | 'interaction' | 'ideas' | 'calendar';
  path: string;
  question: string;
  main: string;
  detail: string | null;
  lines: string[];
  freshness: string;
  /** Ничего не горит: слайд остаётся в повестке — «всё спокойно» тоже ответ. */
  empty: boolean;
}

const LINES = 5;

export function pultSlide(t: TFunction, view: PultView): Slide {
  const steps = LADDER.filter((step) => view.counts[step] > 0);
  return {
    key: 'pult',
    section: 'pult',
    path: '/',
    question: t('meeting.pult.question'),
    main:
      steps.length === 0
        ? t('meeting.pult.none')
        : steps.map((step) => `${t(`pult.steps.${step}`)} ${view.counts[step]}`).join(' · '),
    detail: t('meeting.pult.onTrack', { count: view.on_track }),
    lines: view.rows
      .slice(0, LINES)
      .map(
        (row) =>
          `${t(`pult.steps.${row.step}`)} — ${rowTitle(t, row)}${row.responsible ? ` · ${row.responsible.name}` : ''}`,
      ),
    freshness: t('pult.asOf', { when: formatDateTime(view.as_of) }),
    empty: steps.length === 0,
  };
}

export function ijroSlide(t: TFunction, view: IjroView): Slide | null {
  const answer = view.questions.find((each) => each.key === 'burning');
  if (!answer) return null;
  const text = ijroAnswer(t, answer);
  return {
    key: 'ijro',
    section: 'ijro',
    path: '/ijro',
    question: t(`ijro.questions.${answer.key}.title`),
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
    key: 'reports',
    section: 'reports',
    path: '/reports',
    question: t(`reports.questions.${answer.key}.title`),
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
    key: 'interaction',
    section: 'interaction',
    path: '/interaction',
    question: t(`interaction.questions.${answer.key}.title`),
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
    key: 'ideas',
    section: 'ideas',
    path: '/ideas',
    question: t('ideas.awaiting.title'),
    main: text.main,
    detail: text.detail,
    lines: answer.rows.slice(0, LINES).flatMap((id) => {
      const idea = byId.get(id);
      return idea ? [`${idea.text} · ${t('ideas.waiting', { count: idea.waiting_days })}`] : [];
    }),
    freshness: t('ideas.freshness', { when: formatDateTime(view.as_of) }),
    empty: answer.count === 0,
  };
}

export function calendarSlide(t: TFunction, view: CalendarView, today: string): Slide {
  const hot = view.hot_ahead;
  return {
    key: 'calendar',
    section: 'calendar',
    path: '/calendar',
    question: t('calendar.hot.title'),
    main:
      hot.length === 0 ? t('calendar.hot.none') : t('calendar.hot.answer', { count: hot.length }),
    detail: null,
    lines: hot
      .slice(0, LINES)
      .map((day) => `${hotDayTitle(t, day.date, today)} — ${hotText(t, day)}`),
    freshness: t('pult.asOf', { when: formatDateTime(view.as_of) }),
    empty: hot.length === 0,
  };
}

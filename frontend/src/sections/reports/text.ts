/**
 * Подписи раздела «Доклады и мероприятия»: дни до показа, ответы вопросов, напоминание.
 *
 * Числа приходят готовыми — их считает сервер; здесь они только становятся словами.
 */

import type { TFunction } from 'i18next';

import { formatDate } from '@/shared/time';

import type { Delay, InfoRequest, PreparationRow, QuestionAnswer } from './model';

/** «через 9 дн», «сегодня», «прошёл 6 дн назад». */
export function daysLeftText(t: TFunction, row: Pick<PreparationRow, 'days_left'>): string {
  if (row.days_left === 0) return t('reports.days.today');
  if (row.days_left > 0) return t('reports.days.left', { days: row.days_left });
  return t('reports.days.past', { days: -row.days_left });
}

export function delayText(t: TFunction, delay: Delay): string {
  return t('reports.delay', { name: delay.source.name, count: delay.count, days: delay.days });
}

/** Чего не хватает: «не хватает 2 сведений из 3» или «сведения собраны». */
export function missingText(t: TFunction, row: Pick<PreparationRow, 'requests'>): string {
  const missing = row.requests.total - row.requests.received;
  if (row.requests.total === 0) return t('reports.requests.none');
  if (missing === 0) return t('reports.requests.complete');
  return t('reports.requests.missing', { missing, total: row.requests.total });
}

export interface AnswerText {
  main: string;
  detail: string | null;
  empty: boolean;
}

export function answerText(t: TFunction, answer: QuestionAnswer): AnswerText {
  if (answer.key === 'start_now') {
    return answer.count === 0
      ? { main: t('reports.questions.start_now.empty'), detail: null, empty: true }
      : {
          main: t('reports.questions.start_now.answer', { count: answer.count }),
          detail: null,
          empty: false,
        };
  }
  const nearest = answer.nearest;
  if (!nearest) {
    return { main: t('reports.questions.readiness.empty'), detail: null, empty: true };
  }
  const main =
    nearest.missing === 0
      ? t('reports.questions.readiness.ready', { title: nearest.title })
      : t('reports.questions.readiness.missing', { title: nearest.title, count: nearest.missing });
  const parts = [
    t('reports.questions.readiness.when', { days: nearest.days_left }),
    nearest.delay ? delayText(t, nearest.delay) : null,
    answer.count > 0 ? t('reports.questions.readiness.others', { count: answer.count }) : null,
  ].filter(Boolean);
  return { main, detail: parts.join(' · '), empty: false };
}

/**
 * Текст напоминания тому, кто задерживает (V43): отправляет человек своим каналом — письмом,
 * в мессенджере, звонком. Система готовит текст, а не шлёт его сама.
 */
export function reminderText(
  t: TFunction,
  row: Pick<PreparationRow, 'title' | 'show_on'>,
  requests: InfoRequest[],
): string {
  const list = requests
    .map((each) =>
      each.due_on
        ? t('reports.reminder.lineDue', { what: each.what, date: formatDate(each.due_on) })
        : t('reports.reminder.line', { what: each.what }),
    )
    .join('\n');
  return t('reports.reminder.text', {
    title: row.title,
    date: formatDate(row.show_on),
    list,
  });
}

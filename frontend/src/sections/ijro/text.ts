/**
 * Подписи раздела «Ижро»: срок с точностью, место поручения, ответ вопроса словами.
 *
 * Отдельно от компонентов: нужны виджетам, списку, таблице, карточке и тестам. Числа сюда
 * приходят готовыми — их считает сервер; здесь они только становятся фразой.
 */

import type { TFunction } from 'i18next';

import { deviationText } from '@/sections/pult/text';
import { intlLocale } from '@/shared/i18n';
import { dateFormat } from '@/shared/i18n/format';
import { formatDate } from '@/shared/time';

import type { AssignmentRow, QuestionAnswer } from './model';

/**
 * «октябрь» — месяц внутри фразы срока, со строчной: отдельно стоящий месяц узбекский
 * `Intl` пишет с заглавной («Oktabr»), а во фразе «2026-yil oktabr» она лишняя.
 */
function monthInPhrase(date: string): string {
  return dateFormat({ month: 'long', timeZone: 'UTC' })
    .format(new Date(`${date}T00:00:00Z`))
    .toLocaleLowerCase(intlLocale());
}

/** Первая строка содержания для списка: текст источника не правится, только обрезается. */
export function firstLine(content: string, limit = 96): string {
  return content.length > limit ? `${content.slice(0, limit).trimEnd()}…` : content;
}

/** Срок с его точностью (V33): «до 25.10.2026», «октябрь 2026», «до конца 2026 года». */
export function dueLabel(
  t: TFunction,
  row: Pick<AssignmentRow, 'due_on' | 'due_precision'>,
): string {
  if (!row.due_on) return t('ijro.due.none');
  const year = row.due_on.slice(0, 4);
  if (row.due_precision === 'end_of_year') return t('ijro.due.yearEnd', { year });
  if (row.due_precision === 'month') {
    return t('ijro.due.month', { month: monthInPhrase(row.due_on), year });
  }
  return t('ijro.due.day', { date: formatDate(row.due_on) });
}

/** «ПҚ-312 · 4-банд» — документ и пункт как в источнике. */
export function place(row: Pick<AssignmentRow, 'document' | 'band'>): string {
  return row.band ? `${row.document.code} · ${row.band}` : row.document.code;
}

/** Сопоставленный сотрудник, а пока его нет — написание из таблицы (инвариант 6). */
export function who(row: Pick<AssignmentRow, 'responsible' | 'responsible_raw'>): string {
  return row.responsible?.name ?? row.responsible_raw;
}

export function leadName(row: Pick<AssignmentRow, 'lead_organization'>): string | null {
  const lead = row.lead_organization;
  return lead ? (lead.short_name ?? lead.name) : null;
}

/** «просрочено 5 дн», «через 2 дн» — словами ступени, теми же, что на Пульте. */
export function stepText(t: TFunction, row: Pick<AssignmentRow, 'step' | 'deviation'>): string {
  return row.step ? deviationText(t, { step: row.step, deviation: row.deviation }) : '';
}

export interface AnswerText {
  main: string;
  detail: string | null;
  /** Есть ли что открывать: у пустого ответа действия нет. */
  empty: boolean;
}

/** Ответ вопроса фразой. Пустой ответ — слова, а не ноль (ТЗ 5). */
export function answerText(t: TFunction, answer: QuestionAnswer): AnswerText {
  const base = `ijro.questions.${answer.key}`;
  const empty = (): AnswerText => ({ main: t(`${base}.empty`), detail: null, empty: true });

  switch (answer.key) {
    case 'burning':
      if (answer.burning + answer.overdue === 0) return empty();
      return {
        main: t(`${base}.answer`, { burning: answer.burning, overdue: answer.overdue }),
        detail: answer.oldest ? t(`${base}.oldest`, { days: answer.oldest.days }) : null,
        empty: false,
      };
    case 'silent':
      if (answer.count === 0) return empty();
      return {
        main: t(`${base}.answer`, { count: answer.count }),
        detail: answer.worst
          ? t(`${base}.worst`, {
              who: answer.worst.person?.name ?? answer.worst.responsible_raw,
              days: answer.worst.days,
            })
          : null,
        empty: false,
      };
    case 'foreign': {
      if (answer.count === 0) return empty();
      const [top] = answer.organizations;
      return {
        main: t(`${base}.answer`, { count: answer.count, orgs: answer.organizations.length }),
        detail: top
          ? t(`${base}.top`, {
              name: top.organization.short_name ?? top.organization.name,
              count: top.count,
            })
          : null,
        empty: false,
      };
    }
    case 'awaiting':
    case 'returned':
      if (answer.count === 0) return empty();
      return {
        main: t(`${base}.answer`, { count: answer.count }),
        detail: answer.oldest ? t(`${base}.oldest`, { days: answer.oldest.days }) : null,
        empty: false,
      };
    case 'extension_requested':
      if (answer.count === 0) return empty();
      return { main: t(`${base}.answer`, { count: answer.count }), detail: null, empty: false };
    case 'report_up':
      if (answer.count === 0) return empty();
      return {
        main: t(`${base}.answer`, { count: answer.count }),
        detail: answer.freshest_on
          ? t(`${base}.freshest`, { date: formatDate(answer.freshest_on) })
          : null,
        empty: false,
      };
    case 'without_tasks':
      if (answer.count === 0) return empty();
      return {
        main: t(`${base}.answer`, { count: answer.count, total: answer.total }),
        detail: t(`${base}.rule`),
        empty: false,
      };
    case 'chronic':
      if (answer.count === 0) return empty();
      return {
        main: t(`${base}.answer`, { count: answer.count }),
        detail: answer.sample
          ? t(`${base}.sample`, {
              from: formatDate(answer.sample.original_due_on),
              to: formatDate(answer.sample.due_on),
              count: answer.sample.extensions,
            })
          : null,
        empty: false,
      };
    case 'year_end':
      if (answer.upcoming === 0) return empty();
      return {
        main: t(`${base}.answer`, {
          upcoming: answer.upcoming,
          closed: answer.closed,
          days: answer.window_days,
        }),
        detail: t(`${base}.verdict.${answer.verdict}`, { min: answer.min_closed }),
        empty: answer.rows.length === 0,
      };
    case 'last_batch':
      if (!answer.batch) return empty();
      return {
        main: t(`${base}.answer`, {
          created: answer.created,
          changed: answer.changed,
          vanished: answer.vanished,
        }),
        detail:
          answer.pending_extensions > 0
            ? t(`${base}.pending`, { count: answer.pending_extensions })
            : t(`${base}.noPending`),
        empty: false,
      };
    case 'documents':
      if (!answer.worst) return empty();
      return {
        main: t(`${base}.answer`, {
          done: answer.worst.done,
          total: answer.worst.total,
          code: answer.worst.document.code,
        }),
        detail: null,
        empty: false,
      };
  }
}

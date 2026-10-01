/**
 * Подписи раздела «Взаимодействие»: ответ вопроса фразой, ступень письма и соглашения.
 *
 * Числа приходят готовыми — их считает сервер; здесь они только становятся словами.
 */

import type { TFunction } from 'i18next';

import { deviationText } from '@/sections/pult/text';
import { formatDate } from '@/shared/time';

import type {
  Agreement,
  LetterRow,
  OrganizationRef,
  OrganizationRow,
  QuestionAnswer,
} from './model';

/** Короткое имя организации для строки; полное — в карточке. */
export function orgName(organization: OrganizationRef): string {
  return organization.short_name ?? organization.name;
}

/** Номер и дата письма: «№ 03-11/2420 от 05.09.2026». */
export function letterNumber(t: TFunction, row: Pick<LetterRow, 'number' | 'sent_on'>): string {
  return row.number
    ? t('interaction.letter.number', { number: row.number, date: formatDate(row.sent_on) })
    : t('interaction.letter.noNumber', { date: formatDate(row.sent_on) });
}

/**
 * Что с письмом словами. У ждущего ответа — сколько ждём; у входящего — сколько осталось
 * или насколько просрочено; у отвеченного — за сколько ответили.
 */
export function letterStatus(t: TFunction, row: LetterRow): string {
  if (row.state === 'answered') return t('interaction.letters.answeredIn', { days: row.days });
  if (row.state === 'waiting_reply') return t('interaction.letters.waiting', { days: row.days });
  if (row.step) return deviationText(t, { step: row.step, deviation: row.deviation });
  return row.due_on
    ? t('interaction.letters.due', { date: formatDate(row.due_on) })
    : t('interaction.letters.noDue');
}

export function agreementStatus(t: TFunction, row: Agreement): string {
  if (row.step === 'silent') return t('interaction.agreements.quiet', { days: row.quiet_days });
  if (row.step) return deviationText(t, { step: row.step, deviation: row.deviation });
  return row.next_step_on
    ? t('interaction.agreements.nextOn', { date: formatDate(row.next_step_on) })
    : t('interaction.agreements.noNext');
}

/** Скорость ответа словами: медиана — только при пяти письмах и больше (ТЗ 4). */
export function speedText(t: TFunction, row: Pick<OrganizationRow, 'speed'>): string {
  if (row.speed.median_days !== null) {
    return t('interaction.organizations.speed', { days: row.speed.median_days });
  }
  return row.speed.letters > 0
    ? t('interaction.organizations.little', { count: row.speed.letters })
    : t('interaction.organizations.noLetters');
}

export interface AnswerText {
  main: string;
  detail: string | null;
  /** Есть ли что открывать: у пустого ответа действия нет. */
  empty: boolean;
}

/** Ответ вопроса фразой. Пустой ответ — слова, а не ноль (ТЗ 5). */
export function answerText(t: TFunction, answer: QuestionAnswer): AnswerText {
  const base = `interaction.questions.${answer.key}`;
  switch (answer.key) {
    case 'not_answering': {
      if (answer.count === 0) return { main: t(`${base}.empty`), detail: null, empty: true };
      const top = [...answer.organizations].sort((a, b) => b.oldest_days - a.oldest_days)[0];
      return {
        main: t(`${base}.answer`, { count: answer.count, orgs: answer.organizations.length }),
        detail: top
          ? t(`${base}.detail`, { name: orgName(top.organization), days: top.oldest_days })
          : null,
        empty: false,
      };
    }
    case 'to_answer': {
      if (answer.count === 0) return { main: t(`${base}.empty`), detail: null, empty: true };
      const parts = [
        answer.overdue > 0 ? t(`${base}.overdue`, { count: answer.overdue }) : null,
        answer.nearest
          ? answer.nearest.days === 0
            ? t(`${base}.nearestToday`)
            : t(`${base}.nearest`, {
                date: formatDate(answer.nearest.due_on),
                days: answer.nearest.days,
              })
          : null,
      ].filter(Boolean);
      return {
        main: t(`${base}.answer`, { count: answer.count }),
        detail: parts.length > 0 ? parts.join(' · ') : null,
        empty: false,
      };
    }
    case 'speed': {
      const slowest = answer.measured[0];
      const little =
        answer.little_data > 0
          ? t(`${base}.little`, { count: answer.little_data, min: answer.min_letters })
          : null;
      if (!slowest) {
        return {
          main: t(`${base}.empty`, { min: answer.min_letters }),
          detail: little,
          empty: true,
        };
      }
      return {
        main: t(`${base}.answer`, {
          name: orgName(slowest.organization),
          days: slowest.median_days,
        }),
        detail: [t(`${base}.detail`, { count: slowest.letters }), little]
          .filter(Boolean)
          .join(' · '),
        empty: false,
      };
    }
    case 'sleeping': {
      if (answer.count === 0) return { main: t(`${base}.empty`), detail: null, empty: true };
      return {
        main: t(`${base}.answer`, { count: answer.count }),
        detail: answer.oldest ? t(`${base}.detail`, { days: answer.oldest.days }) : null,
        empty: false,
      };
    }
  }
}

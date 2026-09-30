/**
 * Подписи проекта: срок с переносом, отставание от плана. Общие для доски, таблицы,
 * таймлайна и карточки — одна формулировка во всех четырёх местах.
 */

import type { TFunction } from 'i18next';

import type { Step } from '@/sections/pult/model';
import { formatDate } from '@/shared/time';

import type { ProjectCard } from './model';

/** «срок 12.10.2026» или «срок 28.09.2026 → 12.10.2026», если переносили. */
export function dueText(
  t: TFunction,
  card: Pick<ProjectCard, 'due_on' | 'original_due_on'>,
): string {
  if (card.original_due_on !== card.due_on) {
    return t('projects.card.moved', {
      from: formatDate(card.original_due_on),
      to: formatDate(card.due_on),
    });
  }
  return t('projects.card.due', { date: formatDate(card.due_on) });
}

/** «отстаёт на 9 дн», «с запасом 4 дн», «по графику» (ТЗ 4, отставание от плана). */
export function lagText(t: TFunction, lagDays: number): string {
  if (lagDays > 0) return t('projects.card.lag', { days: lagDays });
  if (lagDays < 0) return t('projects.card.ahead', { days: -lagDays });
  return t('projects.card.onPlan');
}

/** Ступень словами; у `null` — «по плану»: пустое место читалось бы как «нет данных». */
export function stepLabel(t: TFunction, step: Step | null): string {
  return step ? t(`pult.steps.${step}`) : t('projects.whatIf.onPlan');
}

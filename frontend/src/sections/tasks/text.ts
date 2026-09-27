/**
 * Подписи задачи: срок с переносом, привязка. Одна формулировка для списка, таблицы и
 * карточки.
 */

import type { TFunction } from 'i18next';

import { formatDate } from '@/shared/time';

import type { ProjectRef, TaskCard } from './model';

/** «срок 02.10.2026», «срок 25.09.2026 → 02.10.2026» или «без срока». */
export function dueText(t: TFunction, task: Pick<TaskCard, 'due_on' | 'original_due_on'>): string {
  if (!task.due_on) return t('tasks.card.noDue');
  if (task.original_due_on && task.original_due_on !== task.due_on) {
    return t('tasks.card.moved', {
      from: formatDate(task.original_due_on),
      to: formatDate(task.due_on),
    });
  }
  return t('tasks.card.due', { date: formatDate(task.due_on) });
}

/** К чему относится задача: номер проекта или поручение. Пусто — без привязки. */
export function linkText(t: TFunction, task: Pick<TaskCard, 'project' | 'ijro'>): string | null {
  if (task.project) return task.project.code;
  if (task.ijro) return t('tasks.card.ijro', { label: task.ijro.label });
  return null;
}

/** Проект в списках выбора: номер и название — по номеру его называют вслух. */
export function projectLabel(ref: ProjectRef): string {
  return `${ref.code} · ${ref.title}`;
}

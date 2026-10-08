/**
 * Фильтр списка поручений.
 *
 * Действие виджета — переход к отфильтрованному списку (ТЗ 5), и список под действием
 * обязан быть тем же, что посчитан в ответе: вопрос фильтрует по `rows` ответа, а не
 * пересчитывает условие на экране.
 */

import type { Step } from '@/sections/pult/model';

import type { AssignmentRow, IjroSource, IjroView, QuestionKey, Stage } from './model';

export interface Filter {
  question: QuestionKey | null;
  step: Step | null;
  source: IjroSource | null;
  stage: Stage | null;
  /** Идентификатор сотрудника или `raw:<написание>`, пока он не сопоставлен. */
  person: string | null;
  organization: string | null;
  document: string | null;
}

export const NO_FILTER: Filter = {
  question: null,
  step: null,
  source: null,
  stage: null,
  person: null,
  organization: null,
  document: null,
};

export function personKey(row: Pick<AssignmentRow, 'responsible' | 'responsible_raw'>): string {
  return row.responsible?.id ?? `raw:${row.responsible_raw}`;
}

export function isFiltered(filter: Filter): boolean {
  return Object.values(filter).some((value) => value !== null);
}

export function applyFilter(view: IjroView, filter: Filter): AssignmentRow[] {
  const answer = filter.question
    ? view.questions.find((each) => each.key === filter.question)
    : undefined;
  const ids = answer ? new Set(answer.rows) : null;
  const rows = view.items.filter(
    (row) =>
      (!ids || ids.has(row.id)) &&
      (!filter.step || row.step === filter.step) &&
      (!filter.source || row.document.source === filter.source) &&
      (!filter.stage || row.stage === filter.stage) &&
      (!filter.person || personKey(row) === filter.person) &&
      (!filter.organization || row.lead_organization?.id === filter.organization) &&
      (!filter.document || row.document.id === filter.document),
  );
  // Список вопроса идёт в порядке ответа: «молчит дольше всех» первым, а не по лестнице.
  if (!answer) return rows;
  const order = new Map(answer.rows.map((id, index) => [id, index]));
  return [...rows].sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
}

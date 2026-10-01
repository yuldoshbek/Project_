/**
 * Отбор писем на вкладке «Письма».
 *
 * Действие вопроса открывает **те же строки, что посчитаны в ответе** (ТЗ 5): отбор по
 * вопросу берёт `rows` ответа, а не пересчитывает правило на экране.
 */

import type { Direction, InteractionView, LetterRow, LetterState } from './model';

export interface Filter {
  /** Вопрос, чьи строки показаны: `not_answering` или `to_answer`. */
  question: 'not_answering' | 'to_answer' | null;
  state: LetterState | null;
  direction: Direction | null;
  organization: string | null;
}

export const NO_FILTER: Filter = {
  question: null,
  state: null,
  direction: null,
  organization: null,
};

export function filterLetters(view: InteractionView, filter: Filter): LetterRow[] {
  const answer = filter.question
    ? view.questions.find((each) => each.key === filter.question)
    : undefined;
  const wanted = answer ? new Set(answer.rows) : null;
  return view.letters.filter(
    (row) =>
      (!wanted || wanted.has(row.id)) &&
      (!filter.state || row.state === filter.state) &&
      (!filter.direction || row.direction === filter.direction) &&
      (!filter.organization || row.organization.id === filter.organization),
  );
}

export function isFiltered(filter: Filter): boolean {
  return Object.values(filter).some((value) => value !== null);
}

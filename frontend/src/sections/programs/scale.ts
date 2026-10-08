/**
 * Шкала горизонта лет: дата → доля ширины, вехи → по годам.
 *
 * Положение считается в днях, а не делением на пять равных лет: високосный год на
 * шкале шире на день, и веха 31 декабря не заезжает в соседний год.
 */

import type { ProgramMilestone, ProgramsView } from './model';

const DAY_MS = 86_400_000;

export function dayOf(date: string): number {
  return Math.round(Date.parse(`${date.slice(0, 10)}T00:00:00Z`) / DAY_MS);
}

export function yearsOf(horizon: ProgramsView['horizon']): number[] {
  return Array.from({ length: horizon.to - horizon.from + 1 }, (_, index) => horizon.from + index);
}

export interface Scale {
  from: number;
  to: number;
  /** Доля ширины, %, прижатая к краям шкалы. */
  at: (day: number) => number;
  inside: (day: number) => boolean;
}

export function scaleOf(horizon: ProgramsView['horizon']): Scale {
  const from = dayOf(`${horizon.from}-01-01`);
  const to = dayOf(`${horizon.to + 1}-01-01`);
  const span = to - from;
  return {
    from,
    to,
    at: (day) => ((Math.min(Math.max(day, from), to) - from) / span) * 100,
    inside: (day) => day >= from && day < to,
  };
}

/** Корзина вех: год горизонта, «раньше» или «позже» — за его краями. */
export type YearBucket = number | 'before' | 'after';

export function bucketOf(date: string, horizon: ProgramsView['horizon']): YearBucket {
  const year = Number(date.slice(0, 4));
  if (year < horizon.from) return 'before';
  if (year > horizon.to) return 'after';
  return year;
}

/** Вехи по годам горизонта; края — только если в них что-то есть. */
export function byYear<T extends Pick<ProgramMilestone, 'due_on'>>(
  milestones: T[],
  horizon: ProgramsView['horizon'],
): { bucket: YearBucket; items: T[] }[] {
  const buckets: YearBucket[] = ['before', ...yearsOf(horizon), 'after'];
  return buckets
    .map((bucket) => ({
      bucket,
      items: milestones
        .filter((milestone) => bucketOf(milestone.due_on, horizon) === bucket)
        .sort((left, right) => left.due_on.localeCompare(right.due_on)),
    }))
    .filter((group) => typeof group.bucket === 'number' || group.items.length > 0);
}

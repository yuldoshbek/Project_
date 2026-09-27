import { describe, expect, it } from 'vitest';

import { filterTasks, isFiltered, NO_FILTER } from './filter';
import { ITEMS } from './test-data';

describe('фильтры задач', () => {
  it('без фильтра — все задачи в серверном порядке', () => {
    expect(filterTasks(ITEMS, NO_FILTER)).toEqual(ITEMS);
    expect(isFiltered(NO_FILTER)).toBe(false);
  });

  it('поиск — по названию и номеру без учёта регистра', () => {
    expect(filterTasks(ITEMS, { ...NO_FILTER, search: 'tsk-2026-0003' }).map((t) => t.id)).toEqual([
      't-3',
    ]);
    expect(filterTasks(ITEMS, { ...NO_FILTER, search: 'ЗАСУХ' }).map((t) => t.id)).toEqual(['t-1']);
  });

  it('«без проекта» — только задачи без привязки к проекту', () => {
    expect(filterTasks(ITEMS, { ...NO_FILTER, project: 'none' }).map((t) => t.id)).toEqual([
      't-2',
      't-4',
      't-5',
      't-6',
    ]);
    expect(
      filterTasks(ITEMS, { ...NO_FILTER, project: 'pr-calibration' }).map((t) => t.id),
    ).toEqual(['t-3']);
  });

  it('ответственный, тип, требует внимания', () => {
    expect(filterTasks(ITEMS, { ...NO_FILTER, assignee: 'p-karimov' }).map((t) => t.id)).toEqual([
      't-2',
      't-3',
      't-6',
    ]);
    expect(filterTasks(ITEMS, { ...NO_FILTER, type: 'site_visit' }).map((t) => t.id)).toEqual([
      't-3',
    ]);
    expect(filterTasks(ITEMS, { ...NO_FILTER, attention: true }).map((t) => t.id)).toEqual([
      't-1',
      't-2',
      't-3',
    ]);
  });
});

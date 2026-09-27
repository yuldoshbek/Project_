import { describe, expect, it } from 'vitest';

import { DemoTasks } from './demo';
import { filterTasks, isFiltered, NO_FILTER } from './filter';

const items = new DemoTasks(() => new Date('2026-09-25T07:00:00Z')).view().items;

describe('фильтры задач', () => {
  it('без фильтра — все задачи в серверном порядке', () => {
    expect(filterTasks(items, NO_FILTER)).toEqual(items);
    expect(isFiltered(NO_FILTER)).toBe(false);
  });

  it('поиск — по названию и номеру без учёта регистра', () => {
    const [first] = items;
    expect(filterTasks(items, { ...NO_FILTER, search: first!.code.toLowerCase() })).toEqual([
      first,
    ]);
    expect(
      filterTasks(items, { ...NO_FILTER, search: 'ПАВОДК' }).every((task) =>
        task.title.toLowerCase().includes('паводк'),
      ),
    ).toBe(true);
  });

  it('«без проекта» — только задачи без привязки к проекту', () => {
    const loose = filterTasks(items, { ...NO_FILTER, project: 'none' });
    expect(loose.length).toBeGreaterThan(0);
    expect(loose.every((task) => task.project === null)).toBe(true);
  });

  it('ответственный, тип, требует внимания', () => {
    expect(
      filterTasks(items, { ...NO_FILTER, assignee: 'p-karimov' }).every(
        (task) => task.assignee?.id === 'p-karimov',
      ),
    ).toBe(true);
    expect(
      filterTasks(items, { ...NO_FILTER, type: 'ijro_report' }).every(
        (task) => task.type?.code === 'ijro_report',
      ),
    ).toBe(true);
    expect(
      filterTasks(items, { ...NO_FILTER, attention: true }).every((task) => task.step !== null),
    ).toBe(true);
  });
});

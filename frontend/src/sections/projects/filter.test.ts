import { describe, expect, it } from 'vitest';

import { DemoProjects } from './demo';
import { filterProjects, isFiltered, NO_FILTER } from './filter';

const items = new DemoProjects(() => new Date('2026-09-25T07:00:00Z')).view().items;

describe('фильтры проектов', () => {
  it('без фильтра — все проекты в серверном порядке', () => {
    expect(filterProjects(items, NO_FILTER)).toEqual(items);
    expect(isFiltered(NO_FILTER)).toBe(false);
  });

  it('поиск — по названию и по номеру, без учёта регистра', () => {
    const [first] = items;
    expect(filterProjects(items, { ...NO_FILTER, search: first!.code.toLowerCase() })).toEqual([
      first,
    ]);
    expect(
      filterProjects(items, { ...NO_FILTER, search: 'ГЕОДАНН' }).every((card) =>
        card.title.toLowerCase().includes('геоданн'),
      ),
    ).toBe(true);
  });

  it('«что держит Центр» — только проекты с ролью Центра', () => {
    const center = filterProjects(items, { ...NO_FILTER, center: true });
    expect(center.length).toBeGreaterThan(0);
    expect(center.every((card) => card.center_role !== null)).toBe(true);
  });

  it('«требует внимания» — только проекты на ступени лестницы', () => {
    const attention = filterProjects(items, { ...NO_FILTER, attention: true });
    expect(attention.length).toBeGreaterThan(0);
    expect(attention.every((card) => card.step !== null)).toBe(true);
  });
});

import { describe, expect, it } from 'vitest';

import { filterProjects, isFiltered, NO_FILTER } from './filter';
import { ITEMS } from './test-data';

describe('фильтры проектов', () => {
  it('без фильтра — все проекты в серверном порядке', () => {
    expect(filterProjects(ITEMS, NO_FILTER)).toEqual(ITEMS);
    expect(isFiltered(NO_FILTER)).toBe(false);
  });

  it('поиск — по названию и по номеру, без учёта регистра', () => {
    const [first] = ITEMS;
    expect(filterProjects(ITEMS, { ...NO_FILTER, search: first!.code.toLowerCase() })).toEqual([
      first,
    ]);
    expect(
      filterProjects(ITEMS, { ...NO_FILTER, search: 'ГЕОДАНН' }).map((card) => card.id),
    ).toEqual(['pr-geodata']);
  });

  it('«что держит Центр» — только проекты с ролью Центра', () => {
    expect(filterProjects(ITEMS, { ...NO_FILTER, center: true }).map((card) => card.id)).toEqual([
      'pr-drought',
    ]);
  });

  it('«требует внимания» — только проекты на ступени лестницы', () => {
    expect(filterProjects(ITEMS, { ...NO_FILTER, attention: true }).map((card) => card.id)).toEqual(
      ['pr-geodata'],
    );
  });

  it('тип и ответственный', () => {
    expect(filterProjects(ITEMS, { ...NO_FILTER, type: 'standard' })).toEqual([]);
    expect(filterProjects(ITEMS, { ...NO_FILTER, responsible: 'p-yusupova' })).toHaveLength(
      ITEMS.length,
    );
    expect(filterProjects(ITEMS, { ...NO_FILTER, responsible: 'p-karimov' })).toEqual([]);
  });
});

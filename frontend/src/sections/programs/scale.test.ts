/**
 * Шкала горизонта: даты за краями прижаты, вехи раскладываются по годам.
 */

import { describe, expect, it } from 'vitest';

import { byYear, scaleOf } from './scale';

describe('шкала горизонта', () => {
  const horizon = { from: 2026, to: 2030 };

  it('прижимает даты за краями и ставит годы по дням', () => {
    const scale = scaleOf(horizon);
    expect(scale.at(scale.from - 100)).toBe(0);
    expect(scale.at(scale.to + 100)).toBe(100);
    expect(scale.inside(scale.to)).toBe(false);
  });

  it('раскладывает вехи по годам, края — только непустые', () => {
    const groups = byYear(
      [{ due_on: '2035-12-01' }, { due_on: '2027-02-15' }, { due_on: '2027-01-10' }],
      horizon,
    );
    expect(groups.map((group) => group.bucket)).toEqual([2026, 2027, 2028, 2029, 2030, 'after']);
    expect(groups[1]!.items.map((item) => item.due_on)).toEqual(['2027-01-10', '2027-02-15']);
  });

  it('прошлый год — корзина «раньше»', () => {
    const groups = byYear([{ due_on: '2025-12-21' }], horizon);
    expect(groups[0]!.bucket).toBe('before');
  });
});

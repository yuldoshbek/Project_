/**
 * Сетка месяца и слова раздела: неделя с понедельника, правило цикла, горячий день.
 *
 * Сами даты циклов, горячие дни и ступени считает сервер и проверяет
 * `backend/tests/test_calendar.py` и `test_cycles_domain.py`.
 */

import i18next from 'i18next';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';

import { monthRange, weekday, weeksOf } from './grid';
import type { CycleRuleFields } from './model';
import { dayOfYear, hotText, isShown, itemTitle, kindText, ruleText } from './text';

const t = i18next.t.bind(i18next);

function cycle(overrides: Partial<CycleRuleFields>): CycleRuleFields {
  return { rule: 'annual', month: 2, day: 15, every_years: 1, anchor_year: 2026, ...overrides };
}

describe('сетка', () => {
  it('месяц — целыми неделями с понедельника', () => {
    const range = monthRange('2026-10');
    expect(range).toEqual({ from: '2026-09-28', to: '2026-11-01' });
    expect(weekday(range.from)).toBe(0);
    expect(weeksOf(range)).toHaveLength(5);
  });
});

describe('слова', () => {
  it('правило цикла; 29 и 30 февраля — как есть, а не 1 марта', () => {
    expect(ruleText(t, cycle({}))).toBe('ежегодно, 15 февраля');
    expect(ruleText(t, cycle({ rule: 'quarterly', day: 5 }))).toBe('ежеквартально, 5-го числа');
    expect(
      ruleText(
        t,
        cycle({ rule: 'every_n_years', month: 3, day: 1, every_years: 3, anchor_year: 2027 }),
      ),
    ).toBe('раз в 3 года, 1 марта, с 2027 года');
    expect(dayOfYear(2, 29)).toBe('29 февраля');
    expect(dayOfYear(2, 30)).toBe('30 февраля');
    expect(dayOfYear(4, 31)).toBe('31 апреля');
  });

  it('горячий день словами: «4 срока: 2 вехи, задача и годовой цикл»', () => {
    expect(hotText(t, { count: 4, kinds: { milestone: 2, task: 1, cycle: 1 } })).toBe(
      '4 срока: 2 вехи, задача и годовой цикл',
    );
    expect(hotText(t, { count: 5, kinds: { task: 5 } })).toBe('5 сроков: 5 задач');
    expect(hotText(t, { count: 3, kinds: { milestone: 1, project: 1, decision: 1 } })).toBe(
      '3 срока: веха, срок проекта и решение',
    );
  });

  it('веха «и срок проекта» видна и тому, кто оставил одни сроки проектов', () => {
    const merged = { kind: 'milestone' as const, is_done: false, ends_project: true };
    expect(kindText(t, merged)).toBe('Веха · и срок проекта');
    expect(isShown(merged, new Set(['project']))).toBe(true);
    expect(isShown({ ...merged, ends_project: false }, new Set(['project']))).toBe(false);
  });

  it('решение без текста называется видом решения, как на Пульте', () => {
    expect(itemTitle(t, { kind: 'decision', title: null, decision_kind: 'hurry' })).toBe(
      t('pult.decisions.hurry'),
    );
    expect(itemTitle(t, { kind: 'task', title: 'Сводка', decision_kind: null })).toBe('Сводка');
  });
});

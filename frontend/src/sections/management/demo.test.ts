/**
 * Вымышленный сервер Управления — по тем правилам, что обещает экран. Когда появится API,
 * правила проверит тест сервера, а демо уйдёт.
 */

import { describe, expect, it } from 'vitest';

import { DemoManagement } from './demo';

const NOW = new Date('2026-09-29T04:00:00Z'); // вторник, 09:00 по Ташкенту

function server() {
  return new DemoManagement(() => NOW);
}

describe('вымышленное Управление', () => {
  it('неделя обхода — с понедельника по воскресенье по Ташкенту', () => {
    const { round } = server().view();
    expect([round.week_from, round.week_to]).toEqual(['2026-09-28', '2026-10-04']);
  });

  it('пороги ТЗ дают числа Пульта вымышленной базы: горит 11, молчит 9', () => {
    const { thresholds } = server().view();
    const affected = Object.fromEntries(thresholds.map((each) => [each.key, each.affected]));
    expect(affected).toMatchObject({ burn_days: 11, quiet_days: 9, summary_at: null });
  });

  it('действие обхода убирает пункт и засчитывается неделе', () => {
    const demo = server();
    demo.act('r-acceptance', 'milestone_passed');
    const { round } = demo.view();
    expect(round.items.map((item) => item.id)).not.toContain('r-acceptance');
    expect(round.done).toBe(4);
  });

  it('чужое действие, пустая строка и чужой человек — отказ', () => {
    const demo = server();
    expect(() => demo.act('r-acceptance', 'task_done')).toThrow();
    expect(() => demo.act('r-lab', 'note', '   ')).toThrow();
    expect(() => demo.act('r-letter', 'assign', 'p-nobody')).toThrow();
    expect(demo.view().round.items).toHaveLength(12);
  });

  it('порог — целое в границах и по версии, которую видел человек', () => {
    const demo = server();
    expect(() => demo.setThreshold('burn_days', 61, 1)).toThrow();
    expect(() => demo.setThreshold('burn_days', 7.5, 1)).toThrow();
    expect(() => demo.setThreshold('summary_at', '8:3', 1)).toThrow();
    const saved = demo.setThreshold('burn_days', 10, 1);
    expect(saved).toMatchObject({ value: 10, affected: 15, version: 2 });
    expect(() => demo.setThreshold('burn_days', 9, 1)).toThrow();
  });

  it('справочники: без дублей, статус не выключается, регион не добавляется', () => {
    const demo = server();
    expect(() => demo.rename('task_types', 'other', 'Согласование', 1)).toThrow();
    expect(() => demo.toggle('task_statuses', 'new', 1)).toThrow();
    expect(() => demo.add('regions', 'Новая область')).toThrow();
    const created = demo.add('organizations', 'Министерство цифровых технологий', 'ministry');
    expect(created).toMatchObject({ used: 0, org_kind: 'ministry', is_center: false });
  });

  it('правка по устаревшей версии — отказ', () => {
    const demo = server();
    demo.rename('task_types', 'other', 'Прочее и разное', 1);
    expect(() => demo.rename('task_types', 'other', 'Иное', 1)).toThrow(/уже изменили/);
    expect(() => demo.removeStep('regulation', 'regulation-0', 5)).toThrow(/уже изменили/);
  });

  it('оба порога горячих дней — одно число: горячие дни в окне', () => {
    const demo = server();
    const hot = () =>
      demo
        .view()
        .thresholds.filter((each) => each.key.startsWith('hot_'))
        .map((each) => each.affected);
    expect(hot()).toEqual([3, 3]);
    demo.setThreshold('hot_day_threshold', 2, 1);
    expect(hot()).toEqual([6, 6]);
  });

  it('пороги управляют обходом — строгое сравнение, как на сервере', () => {
    const demo = server();
    const ids = () => demo.view().round.items.map((item) => item.id);
    expect(ids()).not.toContain('r-drought-note');
    demo.setThreshold('quiet_days', 21, 1);
    expect(ids()).not.toContain('r-aerial');
    expect(ids()).toContain('r-lab');
    demo.setThreshold('impediment_stale_days', 10, 1);
    expect(ids()).toContain('r-drought-note');
    expect(ids()).not.toContain('r-portal-note');
    const stale = demo.view().thresholds.find((each) => each.key === 'impediment_stale_days');
    expect(stale?.affected).toBe(4);
  });

  it('шаблон вех — по порядку сроков, новый тип начинается без вех', () => {
    const demo = server();
    demo.saveStep('regulation', { name: 'Экспертиза', offset_days: 45 });
    expect(demo.view().templates.regulation?.map((step) => step.offset_days)).toEqual([
      30, 45, 60, 90, 120,
    ]);
    const type = demo.add('project_types', 'Научное исследование');
    expect(demo.view().templates[type.id]).toEqual([]);
  });
});

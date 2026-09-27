/**
 * Вымышленный сервер раздела — по тем правилам, что обещаны экраном и будут у API:
 * отсчёт, ступени вех, «до конца года», «успеваем?», порядок раздела, горизонт.
 *
 * Когда появится API, эти же правила проверит тест сервера, а этот файл уйдёт вместе с
 * `demo.ts`.
 */

import { describe, expect, it } from 'vitest';

import { LADDER } from '@/sections/pult/model';

import { DemoPrograms } from './demo';
import { TERMINAL } from './model';
import { byYear, scaleOf } from './scale';

const NOW = new Date('2026-09-27T07:00:00Z'); // воскресенье, Ташкент
const TODAY = '2026-09-27';

function view() {
  return new DemoPrograms(() => NOW).view();
}

describe('вымышленные программы', () => {
  it('горизонт — пять лет от текущего: 2026–2030 (PLAN, блок 1)', () => {
    expect(view().horizon).toEqual({ from: 2026, to: 2030 });
  });

  it('отсчёт — календарные дни до даты программы', () => {
    for (const card of view().items) {
      const days = Math.round(
        (Date.parse(`${card.due_on}T00:00:00Z`) - Date.parse(`${TODAY}T00:00:00Z`)) / 86_400_000,
      );
      expect(card.days_left).toBe(days);
    }
  });

  it('есть программа с переносом даты и вехи с исходным сроком (ТЗ 11)', () => {
    const items = view().items;
    expect(items.some((card) => card.original_due_on !== card.due_on)).toBe(true);
    expect(
      items.flatMap((card) => card.milestones).some((mark) => mark.original_due_on !== mark.due_on),
    ).toBe(true);
  });

  it('ступень вехи сходится со сроком', () => {
    const marks = view().items.flatMap((card) => [
      ...card.milestones,
      ...card.subprojects.flatMap((sub) => sub.milestones),
    ]);
    for (const mark of marks) {
      if (mark.is_passed) expect(mark.step).toBeNull();
      if (mark.step === 'overdue') expect(mark.days_left).toBeLessThan(0);
      if (mark.step === 'burning') expect(mark.days_left).toBeLessThanOrEqual(7);
    }
    expect(marks.some((mark) => mark.step === 'awaiting_decision')).toBe(true);
  });

  it('порядок раздела — лестница, затем по дате; закрытые в конце', () => {
    const items = view().items;
    const rank = (index: number) => {
      const card = items[index]!;
      if (TERMINAL.has(card.status)) return LADDER.length + 1;
      return card.step ? LADDER.indexOf(card.step) : LADDER.length;
    };
    for (let index = 1; index < items.length; index += 1) {
      expect(rank(index)).toBeGreaterThanOrEqual(rank(index - 1));
      if (rank(index) === rank(index - 1)) {
        expect(items[index]!.due_on >= items[index - 1]!.due_on).toBe(true);
      }
    }
    expect(TERMINAL.has(items.at(-1)!.status)).toBe(true);
  });

  it('«до конца года» — непройденные вехи до 31.12, свои и подпроектов, по сроку', () => {
    const { year_end: rows } = view();
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.milestone.is_passed).toBe(false);
      expect(row.milestone.due_on <= '2026-12-31').toBe(true);
    }
    const dates = rows.map((row) => row.milestone.due_on);
    expect(dates).toEqual([...dates].sort());
    // Просроченная — первой: она всё ещё должна случиться в этом году.
    expect(rows[0]!.milestone.step).toBe('overdue');
    expect(rows.some((row) => row.subproject !== null)).toBe(true);
  });

  it('«успеваем?»: прогноз по темпу, мало данных — меньше 10 закрытых задач', () => {
    const items = view().items.filter((card) => card.pace);
    const verdicts = new Set(items.map((card) => card.pace!.verdict));
    expect(verdicts).toEqual(new Set(['on_track', 'behind', 'little_data']));

    for (const { pace, due_on } of items.map((card) => ({ ...card, pace: card.pace! }))) {
      if (pace.verdict === 'little_data') {
        expect(pace.closed_tasks).toBeLessThan(pace.min_closed_tasks);
        expect(pace.forecast_on).toBeNull();
        continue;
      }
      const need = Math.ceil((pace.remaining * pace.window_days) / pace.closed);
      const forecast = new Date(Date.parse(`${TODAY}T00:00:00Z`) + need * 86_400_000)
        .toISOString()
        .slice(0, 10);
      expect(pace.forecast_on).toBe(forecast);
      expect(pace.verdict).toBe(forecast > due_on ? 'behind' : 'on_track');
    }
  });

  it('остаток «успеваем?» — из тех же вех, что на экране, и не меньше непройденных', () => {
    for (const card of view().items.filter((each) => each.pace)) {
      const open = [card, ...card.subprojects]
        .flatMap((work) => work.milestones)
        .filter((mark) => !mark.is_passed).length;
      expect(card.pace!.remaining).toBeGreaterThanOrEqual(open);
      expect(card.pace!.closed).toBeGreaterThanOrEqual(card.pace!.closed_tasks);
    }
  });

  it('у закрытой программы «успеваем?» не спрашивают', () => {
    for (const card of view().items.filter((each) => TERMINAL.has(each.status))) {
      expect(card.pace).toBeNull();
      expect(card.lag_days).toBe(0);
    }
  });
});

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
});

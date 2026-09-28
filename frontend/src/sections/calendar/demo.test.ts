/**
 * Вымышленный сервер раздела — по тем правилам, что обещаны экраном и будут у API: даты
 * циклов на год вперёд и ближайшая за горизонтом (`domain/cycles`), горячие дни, ступени,
 * «срок прошёл», отмена цикла по версии. Плюс сетка месяца и слова: горячий день, правило.
 *
 * Когда появится API, правила проверит тест сервера, а демо уйдёт вместе с `demo.ts`.
 */

import i18next from 'i18next';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';

import { DemoCalendar, nextDate, occurrences } from './demo';
import { monthRange, weekday, weeksOf } from './grid';
import type { CycleRuleFields } from './model';
import { dayOfYear, hotText, ruleText } from './text';

const NOW = new Date('2026-09-28T07:00:00Z'); // понедельник, Ташкент
const TODAY = '2026-09-28';
const t = i18next.t.bind(i18next);

function server() {
  return new DemoCalendar(() => NOW);
}

function cycle(overrides: Partial<CycleRuleFields>): CycleRuleFields {
  return { rule: 'annual', month: 2, day: 15, every_years: 1, anchor_year: 2026, ...overrides };
}

describe('годовые циклы', () => {
  it('разворачиваются на год вперёд и не дальше', () => {
    expect(occurrences(cycle({}), TODAY)).toEqual(['2027-02-15']);
    expect(occurrences(cycle({ rule: 'quarterly', day: 5 }), TODAY)).toEqual([
      '2026-10-05',
      '2027-01-05',
      '2027-04-05',
      '2027-07-05',
    ]);
  });

  it('«раз в N лет» считается от года начала, годы до него не в счёт', () => {
    const every = cycle({ rule: 'every_n_years', month: 3, day: 1, every_years: 3 });
    expect(occurrences({ ...every, anchor_year: 2027 }, TODAY)).toEqual(['2027-03-01']);
    expect(occurrences({ ...every, anchor_year: 2026 }, TODAY)).toEqual([]);
    // 2027 = 2030 − 3: остаток ноль, но цикл начинается только в 2030-м.
    expect(occurrences({ ...every, anchor_year: 2030 }, TODAY)).toEqual([]);
  });

  it('несуществующий день пропускается, а не угадывается', () => {
    expect(occurrences(cycle({ month: 2, day: 31 }), TODAY)).toEqual([]);
    expect(occurrences(cycle({ rule: 'quarterly', day: -3 }), TODAY)).toEqual([]);
    expect(occurrences(cycle({ rule: 'quarterly', day: 1.5 }), TODAY)).toEqual([]);
  });

  it('ближайшая дата — и за горизонтом; 30 февраля — никогда', () => {
    const every = cycle({ rule: 'every_n_years', month: 1, day: 20, every_years: 3 });
    expect(nextDate(every, TODAY)).toBe('2029-01-20');
    expect(nextDate({ ...every, month: 3, day: 1, anchor_year: 2030 }, TODAY)).toBe('2030-03-01');
    expect(nextDate(cycle({ month: 2, day: 29 }), TODAY)).toBe('2028-02-29');
    expect(nextDate({ ...every, month: 2, day: 29 }, TODAY)).toBe('2032-02-29');
    expect(nextDate(cycle({ month: 2, day: 30 }), TODAY)).toBeNull();
    // Шаги — от года начала: начало через десять лет не делает день несуществующим.
    expect(nextDate({ ...every, every_years: 2, anchor_year: 2036 }, TODAY)).toBe('2036-01-20');
    expect(nextDate({ ...every, month: 2, day: 29, anchor_year: 2035 }, TODAY)).toBe('2044-02-29');
  });

  it('правило словами; 29 и 30 февраля — как есть, а не 1 марта', () => {
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
});

describe('вымышленный календарь', () => {
  const range = monthRange('2026-09');

  it('горячие дни на четыре недели — сегодня, через 10 и через 20 дней', () => {
    const view = server().view(range);
    expect(view.hot_threshold).toBe(3);
    expect(view.hot_window_days).toBe(28);
    expect(view.hot_ahead.map((day) => day.date)).toEqual([TODAY, '2026-10-08', '2026-10-18']);
    expect(view.hot_ahead[0]).toMatchObject({ count: 3, kinds: { milestone: 1, task: 2 } });
  });

  it('ответ карточки не зависит от месяца, который смотрят', () => {
    for (const month of ['2026-08', '2026-11', '2026-12', '2027-06']) {
      expect(server().view(monthRange(month)).hot_ahead).toEqual(server().view(range).hot_ahead);
    }
  });

  it('горячие дни сетки — в её днях, прошедших нет', () => {
    const november = server().view(monthRange('2026-11'));
    expect(november.hot_days.map((day) => day.date)).toContain('2026-11-12');
    for (const hot of november.hot_days) {
      expect(hot.date >= november.range.from && hot.date <= november.range.to).toBe(true);
    }
    expect(server().view(monthRange('2026-08')).hot_days).toEqual([]);
  });

  it('срок проекта в день его же вехи — одна строка и один срок', () => {
    // Через 6 дней: итоговая веха стажировок в день срока проекта и задача по геоданным.
    const { items, hot_ahead } = server().view(monthRange('2026-10'));
    const day = items.filter((item) => item.date === '2026-10-04' && !item.is_done);
    expect(day.map((item) => [item.kind, item.ends_project]).sort()).toEqual([
      ['milestone', true],
      ['task', false],
    ]);
    // Ступень — старшая из двух: у стажировок горит и веха, и срок.
    expect(day.find((item) => item.ends_project)).toMatchObject({
      title: 'Итоги и отчёт',
      step: 'burning',
      deviation: 6,
    });
    expect(hot_ahead.map((hot) => hot.date)).not.toContain('2026-10-04');
  });

  it('у горячего дня строк ровно столько, сколько сроков в его подписи', () => {
    const view = server().view({ from: TODAY, to: '2027-09-28' });
    for (const hot of view.hot_days) {
      const open = view.items.filter((item) => item.date === hot.date && !item.is_done);
      expect(open, hot.date).toHaveLength(hot.count);
    }
  });

  it('годовой отчёт Стратегии — 15 февраля, годы в названиях программ — из сроков', () => {
    const later = new DemoCalendar(() => new Date('2026-11-20T07:00:00Z'));
    for (const demo of [server(), later]) {
      const { items } = demo.view(monthRange('2027-02'));
      const report = items.find((item) => item.title === 'Отчёт об исполнении за 2026 год')!;
      expect(report.date).toBe('2027-02-15');
    }
    const title = (demo: DemoCalendar) =>
      demo.view(monthRange('2026-11')).projects.find((each) => each.id === 'pr-catalogue')!.title;
    expect(title(server())).toBe('Национальный каталог космических снимков 2025–2026');
    // Срок каталога — через 45 дней от загрузки: с 17 ноября он уже в следующем году.
    expect(title(later)).toBe('Национальный каталог космических снимков 2025–2027');
  });

  it('ступени — те же, что на Пульте из вымышленной базы', () => {
    const { items } = server().view({ from: '2026-09-01', to: '2027-01-31' });
    // Срок проекта в день его вехи — в строке вехи (`ends_project`).
    const step = (title: string) => {
      const found = items.find(
        (item) => item.title === title || (item.ends_project && item.owner?.title === title),
      )!;
      return [found.date, found.step, found.deviation];
    };
    expect(step('Выгрузка данных в субплатформу')).toEqual(['2026-10-03', 'burning', 5]);
    expect(step('Сводка по паводкам за сентябрь')).toEqual(['2026-10-10', null, 0]);
    expect(step('Внесение проекта постановления в Кабинет министров')).toEqual([
      '2026-10-04',
      'awaiting_decision',
      2,
    ]);
    expect(step('Заказ услуги: аэрофотосъёмка Ферганской долины')).toEqual([
      '2026-12-06',
      'silent',
      21,
    ]);
    expect(step('Совместная программа наблюдения за качеством воздуха')).toEqual([
      '2027-01-06',
      'blocked_by_others',
      25,
    ]);
  });

  it('«срок прошёл» — незакрытое со сроком до сегодня, без дат циклов', () => {
    const { overdue } = server().view(range);
    expect(overdue).toHaveLength(5);
    for (const item of overdue) {
      expect(item.date < TODAY).toBe(true);
      expect(item.is_done).toBe(false);
      expect(item.kind).not.toBe('cycle');
      expect(['overdue', 'awaiting_decision']).toContain(item.step);
    }
  });

  it('у дат цикла нет ступени, и прошедшие даты месяца видны', () => {
    const { items } = server().view(monthRange('2026-10'));
    const cycles = items.filter((item) => item.kind === 'cycle');
    expect(cycles.length).toBeGreaterThan(0);
    expect(cycles.every((item) => item.step === null && item.cycle !== null)).toBe(true);
    const july = server().view(monthRange('2026-07')).items;
    expect(july.map((item) => item.id)).toContain('cy-cabinet:2026-07-05');
  });

  it('список циклов — по ближайшей дате, и цикл без дат на год вперёд в нём есть', () => {
    const list = server().list();
    expect(list.map((each) => each.next_date)).toEqual(
      [...list.map((each) => each.next_date)].sort(),
    );
    const operators = list.find((each) => each.id === 'cy-operators')!;
    expect(operators.next_date).toBe('2027-11-15');
    expect(server().cycle('cy-operators').dates).toEqual([]);
  });

  it('новый цикл — в календаре, отменённый — уходит; отмена по устаревшей версии — отказ', () => {
    const demo = server();
    const created = demo.create({
      title: 'Сведения по ПФ-155 за полугодие',
      rule: 'annual',
      month: 12,
      day: 25,
      every_years: 1,
      anchor_year: 2026,
      project_id: null,
      responsible_id: 'p-rakhimov',
    });
    expect(created.dates).toEqual(['2026-12-25']);
    const december = () => demo.view(monthRange('2026-12')).items.map((item) => item.title);
    expect(december()).toContain('Сведения по ПФ-155 за полугодие');

    expect(() => demo.cancel(created.id, created.version + 1)).toThrow();
    demo.cancel(created.id, created.version);
    expect(december()).not.toContain('Сведения по ПФ-155 за полугодие');
  });

  it('цикл на день, которого нет ни в одном году, не заводится', () => {
    expect(() =>
      server().create({
        title: 'Опечатка',
        rule: 'annual',
        month: 2,
        day: 30,
        every_years: 1,
        anchor_year: 2026,
        project_id: null,
        responsible_id: null,
      }),
    ).toThrow(/ни в одном году/);
  });
});

describe('сетка и слова', () => {
  it('месяц — целыми неделями с понедельника', () => {
    const range = monthRange('2026-10');
    expect(range).toEqual({ from: '2026-09-28', to: '2026-11-01' });
    expect(weekday(range.from)).toBe(0);
    expect(weeksOf(range)).toHaveLength(5);
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
});

/**
 * Правила вымышленного сервера «Ижро» — те же, что посчитает настоящий (`services/metrics`):
 * лестница, двенадцать ответов и их списки, стена, предпросмотр и применение таблицы.
 *
 * Главное обещание — одно вычисление на число и его список (ТЗ 5, инвариант 2).
 */

import { describe, expect, it } from 'vitest';

import { DemoIjro } from './demo';
import { OPEN_STAGES, QUESTIONS, type ApplyChoices, type QuestionAnswer } from './model';

// 10:00 по Ташкенту.
const NOW = new Date('2026-09-30T05:00:00Z');
const FILE = { file: { name: 'АП топшириқлари 4-чорак.docx', size: 48_000 } };
const NO_CHOICES: ApplyChoices = { due_moves: {}, aliases: {}, removed: [] };

function server(now: Date = NOW) {
  return new DemoIjro(() => now);
}

function answer<K extends QuestionAnswer['key']>(
  ijro: DemoIjro,
  key: K,
): Extract<QuestionAnswer, { key: K }> {
  const found = ijro.view().questions.find((each) => each.key === key);
  if (!found) throw new Error(`нет ответа ${key}`);
  return found as Extract<QuestionAnswer, { key: K }>;
}

function steps(ijro: DemoIjro) {
  const counts: Record<string, number> = {};
  for (const row of ijro.view().items) {
    if (row.step) counts[row.step] = (counts[row.step] ?? 0) + 1;
  }
  return counts;
}

describe('лестница', () => {
  it('ступени — по порядку проверок сервера, в любой день года', () => {
    const expected = {
      awaiting_decision: 2,
      overdue: 3,
      burning: 4,
      blocked_by_others: 3,
      silent: 5,
    };
    expect(steps(server())).toEqual(expected);
    // Под конец года срок «до конца года» близко, но по дням не горит (V33).
    expect(steps(server(new Date('2026-12-20T05:00:00Z')))).toEqual(expected);
  });

  it('сданное и снятое с контроля в лестницу не входит', () => {
    for (const row of server().view().items) {
      if (!OPEN_STAGES.has(row.stage)) expect(row.step).toBeNull();
    }
  });

  it('строки идут по лестнице: сначала ждёт решения, в конце — по плану', () => {
    const order = server()
      .view()
      .items.map((row) => row.step);
    expect(order[0]).toBe('awaiting_decision');
    expect(order.at(-1)).toBeNull();
    const firstCalm = order.indexOf(null);
    expect(order.slice(firstCalm).every((step) => step === null)).toBe(true);
  });

  it('контрольная отметка — признак жизни: молчавшее перестаёт молчать', () => {
    const ijro = server();
    expect(ijro.card('a13').step).toBe('silent');

    ijro.mark('a13', { kind: 'contacted' }, 'leader');

    const card = ijro.card('a13');
    expect(card.step).toBeNull();
    expect(card.sign_of_life?.source).toBe('control_mark');
    expect(card.marks[0]).toMatchObject({ kind: 'contacted', author: 'leader' });
  });

  it('решение закрывает вопрос, «Отменить» возвращает его', () => {
    const ijro = server();
    expect(ijro.card('a09').step).toBe('awaiting_decision');

    const decision = ijro.decide('a09', 'approve');
    expect(ijro.card('a09').step).not.toBe('awaiting_decision');
    expect(ijro.card('a09').last_decision?.kind).toBe('approve');

    ijro.undoDecision(decision);
    expect(ijro.card('a09').step).toBe('awaiting_decision');
    expect(ijro.card('a09').last_decision).toBeNull();
  });
});

describe('двенадцать вопросов', () => {
  it('все двенадцать, в порядке телефона, и каждый список — строки реестра', () => {
    const view = server().view();
    expect(view.questions.map((each) => each.key)).toEqual([...QUESTIONS]);
    const known = new Set(view.items.map((row) => row.id));
    for (const each of view.questions) {
      expect(each.rows.every((id) => known.has(id))).toBe(true);
    }
  });

  it('«горит и просрочено» — те же строки, что на лестнице', () => {
    const ijro = server();
    const burning = answer(ijro, 'burning');
    expect([burning.burning, burning.overdue]).toEqual([4, 3]);
    expect(burning.rows).toHaveLength(7);
    expect(burning.oldest).toEqual({ id: 'a01', days: 12 });
    const people = burning.by_person.reduce((sum, each) => sum + each.overdue + each.burning, 0);
    expect(people).toBe(7);
  });

  it('«работает ли ответственный» — молчат при близком сроке, дольше всех первым', () => {
    const silent = answer(server(), 'silent');
    expect(silent.count).toBe(silent.rows.length);
    expect(silent.worst).toMatchObject({ id: 'a02', days: 33 });
    expect(silent.rows[0]).toBe('a02');
    // Срок «месяцем» дальше порога близости — в ответ не входит.
    expect(silent.rows).not.toContain('a12');
  });

  it('«из-за чужого ведомства» — по ведомствам, сумма равна числу', () => {
    const foreign = answer(server(), 'foreign');
    expect(foreign.organizations.reduce((sum, each) => sum + each.count, 0)).toBe(foreign.count);
    expect(foreign.organizations[0]?.organization.short_name).toBe('Минэкологии');
  });

  it('«без задач» — открытые с точным сроком без единой задачи; задача убирает строку', () => {
    const ijro = server();
    const before = answer(ijro, 'without_tasks');
    expect(before.rows).toContain('a05');
    expect(before.count).toBeLessThanOrEqual(before.total);

    ijro.createTask('a05');

    const after = answer(ijro, 'without_tasks');
    expect(after.rows).not.toContain('a05');
    expect(after.count).toBe(before.count - 1);
  });

  it('«разложить на задачу» — первая фраза, тот же ответственный, три рабочих дня до срока', () => {
    const ijro = server();
    // Срок a05 — воскресенье 04.10: три рабочих дня назад — среда 30.09.
    expect(ijro.card('a05').due_on).toBe('2026-10-04');
    expect(ijro.taskPrefill('a05')).toMatchObject({
      type_code: 'ijro_report',
      assignee_id: 'p-yusupova',
      due_on: '2026-09-30',
    });
    // У срока «до конца года» дня нет — и у задачи срока нет.
    expect(ijro.taskPrefill('a17').due_on).toBeNull();
  });

  it('остальные ответы — длины своих списков', () => {
    const ijro = server();
    expect(answer(ijro, 'awaiting')).toMatchObject({ count: 2, oldest: { id: 'a08', days: 6 } });
    expect(answer(ijro, 'returned').rows).toEqual(expect.arrayContaining(['a06', 'a29']));
    expect(answer(ijro, 'extension_requested').count).toBe(2);
    expect(answer(ijro, 'report_up').count).toBe(4);
    expect(answer(ijro, 'chronic').rows.sort()).toEqual(['a15', 'a20']);
    expect(answer(ijro, 'last_batch')).toMatchObject({
      created: 2,
      changed: 3,
      pending_extensions: 1,
    });
    expect(ijro.spravka()).toHaveLength(4);
  });

  it('«хватит ли сил на декабрь» — при шести закрытых судим, и наступает больше', () => {
    const pace = answer(server(), 'year_end');
    expect(pace.closed).toBe(6);
    expect(pace.upcoming).toBeGreaterThan(pace.closed);
    expect(pace.verdict).toBe('behind');
  });
});

describe('стена документов', () => {
  it('клеток столько, сколько пунктов; сдано — сданные и снятые с контроля', () => {
    const view = server().view();
    expect(view.documents.reduce((sum, each) => sum + each.total, 0)).toBe(view.items.length);
    for (const wall of view.documents) {
      expect(wall.cells).toHaveLength(wall.total);
      expect(wall.done).toBe(wall.cells.filter((cell) => !OPEN_STAGES.has(cell.stage)).length);
    }
  });
});

describe('сопоставление ФИО', () => {
  it('система только предлагает; подтверждает человек', () => {
    const ijro = server();
    const before = ijro.card('a07');
    expect(before.responsible).toBeNull();
    expect(before.responsible_raw).toBe('Н.Абдуллаев');
    expect(before.suggestions.map((each) => each.name)).toEqual(['Абдуллаев Н.']);

    ijro.matchPerson('a07', 'p-abdullaev');

    const after = ijro.card('a07');
    expect(after.responsible?.name).toBe('Абдуллаев Н.');
    // Написание из таблицы остаётся (инвариант 6).
    expect(after.responsible_raw).toBe('Н.Абдуллаев');
  });
});

describe('загрузка таблицы', () => {
  it('предпросмотр — семь классов ТЗ 7', () => {
    const preview = server().preview(FILE);
    expect(preview.already_applied_on).toBeNull();
    expect(preview.counts).toMatchObject({
      new: 2,
      text_changed: 1,
      responsible_changed: 1,
      due_moved: 3,
      vanished: 1,
      unrecognized: 1,
    });
    expect(Object.values(preview.counts).reduce((sum, each) => sum + each, 0)).toBe(
      preview.rows.length,
    );
  });

  it('перенос срока записывается только подтверждённый; остальные ждут', () => {
    const ijro = server();
    const before = ijro.card('a02');

    const result = ijro.apply(FILE, { ...NO_CHOICES, due_moves: { 'pv-due-1': 'extension' } });

    expect(result).toMatchObject({
      outcome: 'applied',
      created: 2,
      extensions: 1,
      pending_extensions: 2,
    });
    const after = ijro.card('a02');
    expect(after.extension_history).toHaveLength(before.extension_history.length + 1);
    expect(after.due_on).not.toBe(before.due_on);
    // Неподтверждённый перенос срок не трогает.
    expect(ijro.card('a16').due_on).toBe(server().card('a16').due_on);
    expect(answer(ijro, 'last_batch').pending_extensions).toBe(2);
  });

  it('привоз меняет только поля источника: этап, проблема и отметки — наши', () => {
    const ijro = server();
    ijro.setProblem('a13', 'Маблағ ажратилмади', 'Масала киритилсин');
    ijro.mark('a13', { kind: 'doing' }, 'assistant');
    const before = ijro.card('a13');

    ijro.apply(FILE, NO_CHOICES);

    const after = ijro.card('a13');
    expect(after.content).not.toBe(before.content);
    expect(after).toMatchObject({
      stage: before.stage,
      problem: before.problem,
      proposal: before.proposal,
    });
    expect(after.marks).toEqual(before.marks);
  });

  it('повторная загрузка той же таблицы ничего не меняет', () => {
    const ijro = server();
    ijro.apply(FILE, NO_CHOICES);
    const items = ijro.view().items;

    expect(ijro.preview(FILE).already_applied_on).toBe('2026-09-30');
    expect(ijro.apply(FILE, NO_CHOICES)).toEqual({
      outcome: 'already_applied',
      applied_on: '2026-09-30',
    });
    expect(ijro.view().items).toEqual(items);
  });

  it('следующая таблица без отличий — «изменений нет»', () => {
    const ijro = server();
    ijro.apply(FILE, NO_CHOICES);
    const other = { file: { name: 'другая.docx', size: 1 } };

    const preview = ijro.preview(other);
    expect(preview.counts.unchanged).toBe(preview.rows.length);
    expect(ijro.apply(other, NO_CHOICES)).toEqual({ outcome: 'no_changes' });
  });
});

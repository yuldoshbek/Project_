/**
 * Вымышленный сервер раздела — по тем правилам, что обещаны экраном и будут у API:
 * порядок строк, шаблон вех, «что если» без записи, перенос считается переносом.
 *
 * Когда появится API, эти же правила проверит `backend/tests/test_projects.py`, а этот
 * файл уйдёт вместе с `demo.ts`.
 */

import { describe, expect, it } from 'vitest';

import { DemoProjects, TYPES } from './demo';

const NOW = new Date('2026-09-25T07:00:00Z');

function server() {
  return new DemoProjects(() => NOW);
}

describe('вымышленные проекты', () => {
  it('сначала то, что требует внимания, в конце завершённое и отменённое', () => {
    const items = server().view().items;
    const firstCalm = items.findIndex((card) => card.step === null);
    expect(items.slice(firstCalm).every((card) => card.step === null)).toBe(true);

    const firstClosed = items.findIndex(
      (card) => card.status === 'done' || card.status === 'cancelled',
    );
    expect(
      items
        .slice(firstClosed)
        .every((card) => card.status === 'done' || card.status === 'cancelled'),
    ).toBe(true);
  });

  it('новый проект получает вехи из шаблона типа и срок по последней вехе', () => {
    const demo = server();
    const type = TYPES.find((each) => each.code === 'regulation')!;
    const created = demo.create({
      title: '  Положение о спутниковых данных  ',
      type_code: type.code,
      started_on: '2026-10-01',
      due_on: null,
      responsible_id: null,
      parent_id: null,
      is_multiyear: false,
    });

    expect(created.title).toBe('Положение о спутниковых данных');
    expect(created.code).toMatch(/^PRJ-2026-\d{3}$/);
    expect(created.milestone_list.map((mark) => mark.title)).toEqual(
      type.template.map((step) => step.title),
    );
    const last = Math.max(...type.template.map((step) => step.offset_days));
    const due = new Date(Date.parse('2026-10-01T00:00:00Z') + last * 86_400_000);
    expect(created.due_on).toBe(due.toISOString().slice(0, 10));
    expect(created.original_due_on).toBe(created.due_on);
  });

  it('«что если» ничего не записывает', () => {
    const demo = server();
    const [card] = demo.view().items;
    const before = demo.view();

    const result = demo.whatIf(card!.id, [{ kind: 'project', id: card!.id, due_on: '2027-06-01' }]);

    expect(result.project.after.due_on).toBe('2027-06-01');
    expect(demo.view()).toEqual(before);
  });

  it('«применить» со сдвигом позже — это перенос: исходный срок остаётся', () => {
    const demo = server();
    const card = demo
      .view()
      .items.find((each) => each.moves === 0 && each.status === 'in_progress')!;

    demo.apply(card.id, [{ kind: 'project', id: card.id, due_on: '2027-12-31' }]);

    const after = demo.detail(card.id);
    expect(after.due_on).toBe('2027-12-31');
    expect(after.original_due_on).toBe(card.original_due_on);
    expect(after.moves).toBe(1);
  });

  it('причина хранится у паузы и снимается при возврате в работу', () => {
    const demo = server();
    const card = demo.view().items.find((each) => each.status === 'in_progress')!;

    demo.setStatus(card.id, 'on_hold', 'Ждём финансирование');
    expect(demo.detail(card.id).status_reason).toBe('Ждём финансирование');

    demo.setStatus(card.id, 'in_progress', null);
    expect(demo.detail(card.id).status_reason).toBeNull();
  });
});

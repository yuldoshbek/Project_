/**
 * Вымышленный сервер раздела — по тем правилам, что обещаны экраном и будут у API: группы
 * по сроку, ступени, «кто перегружен», граф статусов, перенос срока.
 *
 * Когда появится API, эти же правила проверит `backend/tests/test_tasks.py`, а этот файл
 * уйдёт вместе с `demo.ts`.
 */

import { describe, expect, it } from 'vitest';

import { DemoTasks } from './demo';
import { HORIZONS } from './model';

const NOW = new Date('2026-09-25T07:00:00Z'); // пятница, Ташкент

function server() {
  return new DemoTasks(() => NOW);
}

describe('вымышленные задачи', () => {
  it('идут группами по сроку в порядке срочности', () => {
    const horizons = server()
      .view()
      .items.map((task) => HORIZONS.indexOf(task.horizon));
    expect(horizons).toEqual([...horizons].sort((left, right) => left - right));
  });

  it('группа и ступень сходятся со сроком', () => {
    for (const task of server().view().items) {
      if (task.horizon === 'overdue') expect(task.due_on! < '2026-09-25').toBe(true);
      if (task.horizon === 'today') expect(task.due_on).toBe('2026-09-25');
      if (task.horizon === 'none') expect(task.due_on).toBeNull();
      if (task.horizon === 'closed') expect(['done', 'cancelled']).toContain(task.status);
      if (task.step === 'overdue') expect(task.horizon).toBe('overdue');
    }
  });

  it('есть задачи без проекта — обычное дело (ТЗ 3.2)', () => {
    expect(
      server()
        .view()
        .items.some((task) => task.project === null),
    ).toBe(true);
  });

  it('«кто перегружен» считает те же ступени, что стоят в строках', () => {
    const view = server().view();
    for (const row of view.load) {
      const own = view.items.filter(
        (task) => task.assignee?.id === row.person.id && task.horizon !== 'closed',
      );
      expect(row.open).toBe(own.length);
      expect(row.overdue).toBe(own.filter((task) => task.step === 'overdue').length);
      expect(row.burning).toBe(own.filter((task) => task.step === 'burning').length);
    }
    const overdue = view.load.map((row) => row.overdue);
    expect(overdue).toEqual([...overdue].sort((left, right) => right - left));
  });

  it('статус — только по разрешённым переходам', () => {
    const demo = server();
    const task = demo.view().items.find((each) => each.status === 'new')!;
    const detail = demo.detail(task.id);
    expect(detail.transitions).toEqual(['in_progress', 'cancelled']);
    expect(() => demo.setStatus(task.id, 'done', detail.version)).toThrow();

    demo.setStatus(task.id, 'in_progress', detail.version);
    expect(demo.detail(task.id).status).toBe('in_progress');
  });

  it('правка по устаревшей версии — отказ', () => {
    const demo = server();
    const task = demo.view().items[0]!;
    demo.setStatus(task.id, 'in_review', task.version);
    expect(() => demo.setStatus(task.id, 'in_progress', task.version)).toThrow(/изменили/);
  });

  it('срок позже — перенос, исходный остаётся', () => {
    const demo = server();
    const task = demo.view().items.find((each) => each.due_on && each.moves === 0)!;
    const detail = demo.detail(task.id);
    demo.edit(task.id, {
      title: detail.title,
      type_code: detail.type?.code ?? null,
      due_on: '2026-12-31',
      assignee_id: detail.assignee?.id ?? null,
      project_id: detail.project?.id ?? null,
      description: null,
      version: detail.version,
    });
    const after = demo.detail(task.id);
    expect(after.due_on).toBe('2026-12-31');
    expect(after.original_due_on).toBe(task.original_due_on);
    expect(after.moves).toBe(1);
  });

  it('новая задача — из разобранной строки', () => {
    const demo = server();
    const parsed = demo.parse('к пятнице рассмотрение проекта постановления Минэкологии, Каримов');
    const created = demo.create({
      title: parsed.title,
      type_code: parsed.type_code,
      due_on: parsed.due_on,
      assignee_id: parsed.assignee_id,
      project_id: null,
    });
    expect(created).toMatchObject({
      title: 'Рассмотрение проекта постановления Минэкологии',
      status: 'new',
      due_on: '2026-10-02',
      horizon: 'week',
      assignee: { id: 'p-karimov' },
      type: { code: 'review_and_endorse' },
      project: null,
    });
    expect(created.code).toMatch(/^TSK-2026-\d{4}$/);
  });

  it('отметка пункта чек-листа — движение: счёт в строке меняется', () => {
    const demo = server();
    const task = demo.view().items.find((each) => each.checklist.total > each.checklist.done)!;
    const item = demo.detail(task.id).checklist_items.find((each) => !each.is_done)!;
    demo.toggleItem(task.id, item.id, true);
    expect(demo.detail(task.id).checklist.done).toBe(task.checklist.done + 1);
  });
});

/**
 * Вымышленный сервер Захвата — по тому правилу, что обещано экраном (допущение V17):
 * просьба руководителя — в «Задачи», идея, письмо и мероприятие — во входящие; недавние —
 * сначала новые. Когда появится API, правило проверит тест сервера, а демо уйдёт.
 */

import { describe, expect, it } from 'vitest';

import { DemoCaptures } from './demo';

const NOW = new Date('2026-09-28T07:00:00Z');

function server() {
  return new DemoCaptures(() => NOW);
}

describe('вымышленные записи захвата', () => {
  it('недавние — сначала новые, у каждой записано, куда ушла', () => {
    const { recent } = server().view();
    expect(recent.map((each) => each.created_at)).toEqual(
      [...recent.map((each) => each.created_at)].sort().reverse(),
    );
    for (const capture of recent) {
      const toTasks = capture.kind === 'task' || capture.kind === 'request';
      expect(capture.destination).toBe(toTasks ? 'tasks' : 'inbox');
    }
    // Срок письма — в днях от сегодня, как у вымышленной базы.
    expect(recent.find((each) => each.kind === 'letter')?.due_on).toBe('2026-10-10');
  });

  it('просьба руководителя — в «Задачи», идея, письмо, мероприятие — во входящие', () => {
    const demo = server();
    const request = demo.save(
      { kind: 'request', text: 'Справка по засухе', due_on: '2026-10-02', assignee_id: null },
      'leader',
    );
    const idea = demo.save(
      { kind: 'idea', text: '  Мониторинг пастбищ  ', due_on: null, assignee_id: null },
      'leader',
    );
    expect(request.destination).toBe('tasks');
    expect(idea).toMatchObject({ destination: 'inbox', text: 'Мониторинг пастбищ' });
    expect(
      demo
        .view()
        .recent.slice(0, 2)
        .map((each) => each.id),
    ).toEqual([idea.id, request.id]);
  });

  it('пустой текст не записывается', () => {
    expect(() =>
      server().save({ kind: 'idea', text: '   ', due_on: null, assignee_id: null }, 'leader'),
    ).toThrow();
  });
});

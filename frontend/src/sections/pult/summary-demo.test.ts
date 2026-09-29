/**
 * Вымышленный сервер сводки: строки — из ответа Пульта (числа на соседних вкладках одни),
 * «срок сегодня» — по дате на любой ступени (V26), время — из порога Управления (V24).
 */

import { describe, expect, it } from 'vitest';

import type { Threshold } from '@/sections/management/model';

import type { PultRow, PultView } from './model';
import { DEFAULT_SEND_AT, sendAtOf, summaryFrom } from './summary-demo';

function row(
  entity_id: string,
  step: PultRow['step'],
  deviation: number,
  due_on: string | null = null,
): PultRow {
  return {
    section: 'tasks',
    entity_id,
    title: entity_id,
    decision_kind: null,
    target_type: 'task',
    target_id: entity_id,
    context: null,
    step,
    deviation,
    due_on,
    original_due_on: due_on,
    responsible: null,
    question: null,
    last_decision: null,
  };
}

// 08:10 по Ташкенту, 29.09.
const PULT = {
  as_of: '2026-09-29T03:10:00Z',
  rows: [
    row('asked', 'awaiting_decision', 6, '2026-10-02'),
    row('asked-today', 'awaiting_decision', 2, '2026-09-29'),
    row('late', 'overdue', 2, '2026-09-27'),
    row('today', 'burning', 0, '2026-09-29'),
    row('soon', 'burning', 3, '2026-10-02'),
  ],
  is_demo: true,
} as PultView;

describe('summaryFrom', () => {
  it('ждут решения — ступень Пульта, срок сегодня — по дате, и у ждущего решения тоже', () => {
    const summary = summaryFrom(PULT, '08:30', new Date('2026-09-29T03:10:00Z'));

    expect(summary.awaiting.map((each) => each.entity_id)).toEqual(['asked', 'asked-today']);
    // Вопрос по работе не переносит её срок: «сроков сегодня нет» было бы неправдой.
    expect(summary.due_today.map((each) => each.entity_id)).toEqual(['asked-today', 'today']);
    expect(summary.as_of).toBe(PULT.as_of);
    expect(summary.is_demo).toBe(true);
  });

  it('до времени сводки она ещё не ушла, после — ушла сегодня', () => {
    // 08:10 и 08:40 по Ташкенту.
    expect(summaryFrom(PULT, '08:30', new Date('2026-09-29T03:10:00Z')).sent_at).toBeNull();
    expect(summaryFrom(PULT, '08:30', new Date('2026-09-29T03:40:00Z')).sent_at).toBe(
      '2026-09-29T08:30:04+05:00',
    );
    // Порог передвинули на 09:00 — в 08:40 ещё не время.
    const later = summaryFrom(PULT, '09:00', new Date('2026-09-29T03:40:00Z'));
    expect(later.send_at).toBe('09:00');
    expect(later.sent_at).toBeNull();
  });
});

describe('sendAtOf', () => {
  it('время — из порога «Утренняя сводка», без него — по ТЗ', () => {
    const threshold = { key: 'summary_at', value: '09:15' } as Threshold;
    expect(sendAtOf({ thresholds: [threshold] })).toBe('09:15');
    expect(sendAtOf({ thresholds: [] })).toBe(DEFAULT_SEND_AT);
  });
});

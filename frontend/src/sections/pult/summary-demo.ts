/**
 * Вымышленный сервер вкладки «Сводка» — до API (CLAUDE.md, цикл блока «экран → API»).
 *
 * Строки берутся из ответа Пульта, а не выдумываются отдельно: вкладка стоит рядом с
 * «Сейчас», и две разные «ждут решения» на соседних вкладках одного экрана — ровно та потеря
 * доверия, от которой защищает инвариант 2. Время — из порога «Утренняя сводка» в ответе
 * Управления, где его и меняют (V24). Сервер считает то же своим кодом (`metrics`).
 *
 * Вымышлены доставка и устройство руководителя: уведомлений пока нет, и экран говорит это
 * сам (`pult.summary.demo`). Устройство, на котором открыт экран, помнит «включено» только в
 * памяти вкладки — настоящая подписка появится с API.
 */

import type { ManagementView } from '@/sections/management/model';
import { AGENCY_TIMEZONE } from '@/shared/time';

import type { PultView, SummaryView } from './model';

const DAY_MS = 86_400_000;

/** Время сводки по ТЗ 8 — пока порог не прочитан или его нет в ответе. */
export const DEFAULT_SEND_AT = '08:30';

function dayIn(now: Date, days: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: AGENCY_TIMEZONE }).format(
    new Date(now.getTime() + days * DAY_MS),
  );
}

/** «ЧЧ:ММ» сейчас по Ташкенту: сравнивается со временем сводки строкой. */
function clock(now: Date): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: AGENCY_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(now);
}

/** Время из порога «Утренняя сводка» (V24) — то же значение, что на вкладке «Пороги». */
export function sendAtOf(management: Pick<ManagementView, 'thresholds'>): string {
  const value = management.thresholds.find((each) => each.key === 'summary_at')?.value;
  return typeof value === 'string' ? value : DEFAULT_SEND_AT;
}

export function summaryFrom(pult: PultView, sendAt: string, now: Date = new Date()): SummaryView {
  // «Сегодня» — день, на который посчитан Пульт, а не часы браузера: строки и их ступени
  // сервер считал на этот день.
  const today = dayIn(new Date(pult.as_of), 0);
  return {
    as_of: pult.as_of,
    send_at: sendAt,
    sent_at: clock(now) >= sendAt ? `${dayIn(now, 0)}T${sendAt}:04+05:00` : null,
    awaiting: pult.rows.filter((row) => row.step === 'awaiting_decision'),
    // По дате, а не по ступени (V26): работа с открытым вопросом стоит на ступени «ждёт
    // решения», но срок у неё от этого не сдвигается, и «сроков сегодня нет» было бы неправдой.
    due_today: pult.rows.filter((row) => row.due_on === today),
    leader_device: { name: 'iPhone', since: dayIn(now, -8) },
    is_demo: true,
  };
}

/** Уведомления на этом устройстве в вымышленном мире: включаются касанием, живут до перезагрузки. */
class DemoDevice {
  private enabledOn: string | null = null;

  enabled(): string | null {
    return this.enabledOn;
  }

  enable(now: Date = new Date()): string {
    this.enabledOn = dayIn(now, 0);
    return this.enabledOn;
  }

  reset(): void {
    this.enabledOn = null;
  }
}

export const demoDevice = new DemoDevice();

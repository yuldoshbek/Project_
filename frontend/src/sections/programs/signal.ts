/**
 * Цвет ступени в разделе — классами целиком, чтобы Tailwind их нашёл: собранное из частей
 * имя класса (`text-${…}-ink`) сборка не видит, и цвет молча пропадает.
 */

import { STEP_SIGNAL, type Step } from '@/sections/pult/model';

const INK = { call: 'text-call-ink', burn: 'text-burn-ink', wait: 'text-wait-ink' } as const;
const BAR = { call: 'bg-call', burn: 'bg-burn', wait: 'bg-wait' } as const;
const MARK = {
  call: 'border-call bg-call-soft',
  burn: 'border-burn bg-burn-soft',
  wait: 'border-wait bg-wait-soft',
} as const;

export function stepInk(step: Step | null): string {
  return step ? INK[STEP_SIGNAL[step]] : 'text-ink-muted';
}

export function stepBar(step: Step | null): string {
  return step ? BAR[STEP_SIGNAL[step]] : 'bg-accent/70';
}

/** Ромб вехи: пройденная закрашена, впереди — контур; у срочной — контур и заливка ступени. */
export function markShape(mark: { is_passed: boolean; step: Step | null }): string {
  if (mark.is_passed) return 'border-ink-strong bg-ink-strong';
  return mark.step ? MARK[STEP_SIGNAL[mark.step]] : 'border-ink-strong bg-card';
}

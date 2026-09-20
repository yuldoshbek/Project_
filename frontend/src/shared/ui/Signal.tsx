/**
 * Сигнал — состояние, показанное цветом **и словом**.
 *
 * Цветом одним нельзя: дальтонизм, чёрно-белая печать отчёта, солнце на экране телефона.
 * Поэтому подпись обязательна, а цвет её усиливает. Четыре состояния и ни одного больше:
 * горит, ждёт, спокойно, требует решения (tokens.css).
 */

import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/shared/lib/cn';

const signal = cva(
  'inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] px-2.5 py-1 ' +
    'text-xs font-medium whitespace-nowrap',
  {
    variants: {
      state: {
        burn: 'bg-burn-soft text-burn-ink',
        wait: 'bg-wait-soft text-wait-ink',
        calm: 'bg-calm-soft text-calm-ink',
        call: 'bg-call-soft text-call-ink',
        plain: 'bg-sunken text-ink-muted',
      },
    },
    defaultVariants: { state: 'plain' },
  },
);

const dot = {
  burn: 'bg-burn',
  wait: 'bg-wait',
  calm: 'bg-calm',
  call: 'bg-call',
  plain: 'bg-ink-muted',
} as const;

export interface SignalProps extends VariantProps<typeof signal> {
  children: string;
  className?: string;
}

export function Signal({ state = 'plain', children, className }: SignalProps) {
  return (
    <span className={cn(signal({ state }), className)}>
      <span className={cn('size-1.5 rounded-full', dot[state ?? 'plain'])} aria-hidden="true" />
      {children}
    </span>
  );
}

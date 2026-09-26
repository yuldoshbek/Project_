/**
 * Кнопка.
 *
 * Три вида и ни одного больше: основное действие, обычное, тихое. В прежнем интерфейсе
 * кнопок было пять стилей — не по замыслу, а потому что каждый экран заводил свою; ради
 * этого компонентный слой и появился (ADR-0030).
 *
 * Высота на телефоне — не меньше 44 px (токен `--touch-target`): это критерий приёмки, а
 * не вкус. Промах по кнопке на телефоне стоит дороже любой экономии места.
 */

import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@/shared/lib/cn';

const button = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius)] font-medium ' +
    'transition-colors duration-[var(--motion-fast)] select-none ' +
    'disabled:opacity-55 disabled:pointer-events-none',
  {
    variants: {
      look: {
        primary: 'bg-accent text-ink-inverse hover:bg-accent-hover',
        plain: 'bg-card text-ink border border-line hover:bg-hover',
        quiet: 'bg-transparent text-ink-muted hover:bg-hover hover:text-ink',
      },
      size: {
        // Телефон: минимальная цель нажатия. Уменьшать нельзя.
        base: 'min-h-touch px-4 text-[15px]',
        // Малая — только на ноутбуке и мониторе. На телефоне та же цель нажатия, что у
        // обычной: 36 px под пальцем промахиваются, а критерий приёмки — 44 px.
        small: 'min-h-touch px-3 text-sm md:min-h-9',
        icon: 'min-h-touch min-w-touch',
      },
    },
    defaultVariants: { look: 'plain', size: 'base' },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  /** Отдать оформление дочернему элементу — например ссылке маршрутизатора. */
  asChild?: boolean;
}

export function Button({ className, look, size, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot : 'button';
  return <Component className={cn(button({ look, size }), className)} {...props} />;
}

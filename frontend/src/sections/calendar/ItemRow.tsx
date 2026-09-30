/**
 * Строка даты: что наступает, чьё, кто отвечает, какая ступень. Одна на список дня, список
 * на телефоне и «просрочено».
 *
 * Вид даты назван словом и значком, а не только цветом. Сделанное зачёркнуто: календарь
 * показывает и историю, но она не должна спорить с тем, что впереди.
 */

import { useTranslation } from 'react-i18next';

import { StepMark } from '@/sections/programs/StepMark';
import { cn } from '@/shared/lib/cn';

import { KIND_ICON } from './kinds';
import type { CalendarItem } from './model';
import { itemTitle, kindText, ruleText } from './text';

interface ItemRowProps {
  item: CalendarItem;
  onOpen: (item: CalendarItem) => void;
  /** Показать дату — в «просрочено», где строки разных дней вместе. */
  withDate?: string | undefined;
}

export function ItemRow({ item, onOpen, withDate }: ItemRowProps) {
  const { t } = useTranslation();
  const Icon = KIND_ICON[item.kind];
  const meta = [
    withDate,
    item.owner?.title ?? null,
    item.responsible?.name ?? null,
    item.cycle ? ruleText(t, item.cycle) : null,
  ].filter(Boolean);

  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className={cn(
        'flex min-h-touch w-full min-w-0 items-start gap-2.5 rounded-[var(--radius)] px-2 py-2 text-left',
        'hover:bg-hover',
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-4 shrink-0',
          item.is_done ? 'text-ink-muted' : 'text-accent-ink',
        )}
        aria-hidden="true"
      />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-xs text-ink-muted">{kindText(t, item)}</span>
        <span
          className={cn(
            'text-sm',
            item.is_done ? 'text-ink-muted line-through' : 'text-ink-strong',
          )}
        >
          {itemTitle(t, item)}
        </span>
        {meta.length > 0 ? (
          <span className="numeric line-clamp-2 text-xs text-ink-muted">{meta.join(' · ')}</span>
        ) : null}
        {item.step ? (
          <span className="mt-0.5">
            <StepMark step={item.step} deviation={item.deviation} />
          </span>
        ) : null}
      </span>
    </button>
  );
}

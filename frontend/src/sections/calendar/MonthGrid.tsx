/**
 * Месяц сеткой — ноутбук и монитор (ТЗ 5: «календарь» — знакомая форма).
 *
 * В клетке — даты словами и «ещё N»: название важнее цветной точки, а двадцать точек в
 * клетке не читаются. На ноутбуке клетка шириной около ста пикселей, и название в одну
 * строку обрезалось до «Отбор учас…» — поэтому с сегодняшнего дня название в две строки, с
 * переносом по слогам. Прошедшие дни — в одну: это история, и две строки на каждой дате
 * выталкивали текущую неделю за нижний край экрана 1440×900. Горячий день — заливкой и
 * словом «тесно»; сегодня — кружком. Касание клетки открывает день справа: там всё, что в
 * него сходится.
 */

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { stepInk } from '@/sections/programs/signal';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';

import { weeksOf } from './grid';
import { KIND_ICON } from './kinds';
import type { CalendarItem, HotDay } from './model';
import { cellLabel, itemTitle, monthTitle, weekdayNames } from './text';

/** Сколько дат словами в клетке: на мониторе места вдвое больше. */
const SHOWN = { laptop: 2, monitor: 4 } as const;

interface MonthGridProps {
  month: string;
  range: { from: string; to: string };
  items: CalendarItem[];
  /** Сколько дат спрятал фильтр — по дню. */
  hidden: ReadonlyMap<string, number>;
  hot: HotDay[];
  today: string;
  selected: string;
  canBack: boolean;
  canForward: boolean;
  onMonth: (step: -1 | 1) => void;
  onToday: () => void;
  onSelect: (date: string) => void;
  /** Монитор: клетки шире и выше — дат словами больше. */
  tall: boolean;
  /** Новый месяц ещё грузится, а видны даты прежнего — сетка приглушена, а не врёт. */
  stale: boolean;
}

export function MonthGrid({
  month,
  range,
  items,
  hidden,
  hot,
  today,
  selected,
  canBack,
  canForward,
  onMonth,
  onToday,
  onSelect,
  tall,
  stale,
}: MonthGridProps) {
  const { t } = useTranslation();
  const shown = tall ? SHOWN.monitor : SHOWN.laptop;
  const hotDates = new Map(hot.map((day) => [day.date, day]));
  const byDay = new Map<string, CalendarItem[]>();
  for (const item of items) {
    const list = byDay.get(item.date) ?? [];
    list.push(item);
    byDay.set(item.date, list);
  }

  return (
    <section
      aria-label={monthTitle(month)}
      aria-busy={stale}
      className={cn(
        'min-w-0 rounded-[var(--radius-lg)] border border-line bg-card p-4 shadow-card sm:p-5',
        'transition-opacity duration-[var(--motion-fast)]',
        stale && 'opacity-60',
      )}
    >
      <header className="mb-3 flex items-center gap-2">
        <h2 className="min-w-0 flex-1 text-base font-semibold text-ink-strong">
          {monthTitle(month)}
        </h2>
        <Button
          size="small"
          look="quiet"
          onClick={() => onMonth(-1)}
          disabled={!canBack}
          aria-label={t('calendar.month.previous')}
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
        </Button>
        <Button size="small" onClick={onToday}>
          {t('calendar.month.today')}
        </Button>
        <Button
          size="small"
          look="quiet"
          onClick={() => onMonth(1)}
          disabled={!canForward}
          aria-label={t('calendar.month.next')}
        >
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </header>

      <div className="grid grid-cols-7 border-b border-line pb-1 text-xs text-ink-muted">
        {weekdayNames().map((name) => (
          <span key={name} className="px-1.5">
            {name}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 border-r border-line">
        {weeksOf(range).flatMap((week) =>
          week.map((date) => {
            const list = byDay.get(date) ?? [];
            const open = list.filter((item) => !item.is_done);
            const skipped = hidden.get(date) ?? 0;
            const heat = hotDates.get(date);
            const outside = date.slice(0, 7) !== month;
            const past = date < today;
            return (
              <button
                key={date}
                type="button"
                onClick={() => onSelect(date)}
                aria-pressed={selected === date}
                aria-label={cellLabel(t, date, open.length, skipped, heat !== undefined)}
                className={cn(
                  'relative flex min-w-0 flex-col items-stretch gap-0.5 border-b border-l border-line p-1.5 text-left',
                  'transition-colors duration-[var(--motion-fast)] hover:bg-hover',
                  tall ? 'min-h-32' : 'min-h-20',
                  past && 'bg-sunken/50',
                  heat && 'bg-burn-soft/60',
                  selected === date && 'z-10 ring-2 ring-accent ring-inset',
                )}
              >
                <span className="flex items-center gap-1">
                  <span
                    className={cn(
                      'numeric grid size-6 place-items-center rounded-full text-xs',
                      date === today
                        ? 'bg-accent font-semibold text-ink-inverse'
                        : outside
                          ? 'text-ink-muted'
                          : 'text-ink-strong',
                    )}
                  >
                    {Number(date.slice(8))}
                  </span>
                  {heat ? (
                    <span className="ml-auto rounded-[var(--radius-pill)] bg-burn px-1.5 text-[11px] font-medium text-ink-inverse">
                      {t('calendar.hot.tag')}
                    </span>
                  ) : null}
                </span>
                {list.slice(0, shown).map((item) => {
                  const Icon = KIND_ICON[item.kind];
                  return (
                    <span
                      key={item.id}
                      className={cn(
                        'flex min-w-0 items-start gap-1 leading-tight',
                        tall ? 'text-sm' : 'text-xs',
                        item.is_done ? 'text-ink-muted line-through' : stepInk(item.step),
                      )}
                    >
                      <Icon className="mt-px size-3 shrink-0" aria-hidden="true" />
                      <span
                        className={cn(
                          'min-w-0 break-words hyphens-auto',
                          past ? 'truncate' : 'line-clamp-2',
                          !item.is_done && !item.step && 'text-ink',
                        )}
                      >
                        {itemTitle(t, item)}
                      </span>
                    </span>
                  );
                })}
                {list.length > shown ? (
                  <span className="text-xs text-ink-muted">
                    {t('calendar.day.more', { count: list.length - shown })}
                  </span>
                ) : null}
                {skipped > 0 ? (
                  <span className="text-xs text-ink-muted">
                    {t('calendar.day.hidden', { count: skipped })}
                  </span>
                ) : null}
              </button>
            );
          }),
        )}
      </div>
    </section>
  );
}

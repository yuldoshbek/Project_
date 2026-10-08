/**
 * Ближайшие дни списком — телефон, где сетки месяца нет (ТЗ 6: без тяжёлой графики).
 *
 * Дни без сроков пропущены: список отвечает, что наступит, а не рисует пустые клетки. День,
 * все даты которого спрятал фильтр, остаётся — со строкой «скрыто фильтром»: иначе касание
 * горячего дня в «где неделя перегружена?» вело бы в никуда. Горячий день помечен словами.
 */

import { Flame } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';

import { Hidden, Overdue } from './DayAgenda';
import { ItemRow } from './ItemRow';
import { dayAnchor } from './kinds';
import type { CalendarItem, HotDay } from './model';
import { dayTitle, hotText, relativeDay } from './text';

interface UpcomingProps {
  items: CalendarItem[];
  /** Сколько дат спрятал фильтр — по дню. */
  hidden: ReadonlyMap<string, number>;
  overdue: CalendarItem[];
  hot: HotDay[];
  today: string;
  onOpen: (item: CalendarItem) => void;
  onShowAll: () => void;
  onMore: (() => void) | null;
}

export function Upcoming({
  items,
  hidden,
  overdue,
  hot,
  today,
  onOpen,
  onShowAll,
  onMore,
}: UpcomingProps) {
  const { t } = useTranslation();
  const hotDates = new Map(hot.map((day) => [day.date, day]));
  const byDay = new Map<string, CalendarItem[]>();
  for (const item of items) byDay.set(item.date, [...(byDay.get(item.date) ?? []), item]);
  const days = [...new Set([...byDay.keys(), ...hidden.keys()])].sort();

  return (
    <section
      aria-label={t('calendar.upcoming.title')}
      className="rounded-[var(--radius-lg)] border border-line bg-card p-4 shadow-card"
    >
      <h2 className="mb-2 text-base font-semibold text-ink-strong">
        {t('calendar.upcoming.title')}
      </h2>
      {overdue.length > 0 ? <Overdue items={overdue} onOpen={onOpen} /> : null}
      {days.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('calendar.upcoming.empty')}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {days.map((date) => {
            const heat = hotDates.get(date);
            const skipped = hidden.get(date) ?? 0;
            return (
              <section
                key={date}
                id={dayAnchor(date)}
                aria-label={dayTitle(date)}
                className="scroll-mt-[calc(var(--topbar-height)+1rem)]"
              >
                <h3
                  className={cn(
                    'flex flex-wrap items-baseline gap-x-2 border-b pb-1 text-sm font-semibold',
                    heat ? 'border-burn text-burn-ink' : 'border-line text-ink-strong',
                  )}
                >
                  <span>{dayTitle(date)}</span>
                  <span className="text-xs font-normal text-ink-muted">
                    {relativeDay(t, date, today)}
                  </span>
                </h3>
                {heat ? (
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-burn-ink">
                    <Flame className="size-3.5" aria-hidden="true" />
                    {hotText(t, heat)}
                  </p>
                ) : null}
                <ul className="flex flex-col">
                  {(byDay.get(date) ?? []).map((item) => (
                    <li key={item.id}>
                      <ItemRow item={item} onOpen={onOpen} />
                    </li>
                  ))}
                </ul>
                {skipped > 0 ? <Hidden count={skipped} onShowAll={onShowAll} /> : null}
              </section>
            );
          })}
        </div>
      )}
      {onMore ? (
        <Button look="plain" className="mt-3 w-full" onClick={onMore}>
          {t('calendar.upcoming.more')}
        </Button>
      ) : null}
    </section>
  );
}

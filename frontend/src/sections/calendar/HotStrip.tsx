/**
 * «Где неделя перегружена?» полосой на четыре недели (ТЗ 5, блок 4, пакет C).
 *
 * Список горячих дней отвечает словами («24.09 — 3 срока и мероприятие»), а полоса — тем, что
 * видно с двух метров на мониторе: где тесно подряд, где неделя свободна. Форма — календарь,
 * из разрешённых ТЗ 5: недели с понедельника, как в сетке месяца. Горячий день — цветом и
 * числом сроков, не одним цветом (дальтонизм, печать). Касание дня открывает его в Календаре.
 */

import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';

import { addDays, weekday } from './grid';
import type { HotDay } from './model';
import { cellLabel, dayTitle, weekdayNames } from './text';

/** Четыре недели — горизонт горячих дней сервера (`hot_window_days`, 28 дней). */
const WEEKS = 4;

export function HotStrip({
  today,
  hot,
  onPick,
}: {
  today: string;
  hot: Pick<HotDay, 'date' | 'count'>[];
  onPick: (date: string) => void;
}) {
  const { t } = useTranslation();
  const counts = new Map(hot.map((day) => [day.date, day.count]));
  const start = addDays(today, -weekday(today));
  const days = Array.from({ length: WEEKS * 7 }, (_, index) => addDays(start, index));

  return (
    <div className="mt-3">
      <div className="grid grid-cols-7 gap-1" aria-hidden="true">
        {weekdayNames().map((name) => (
          <span key={name} className="text-center text-[11px] text-ink-muted">
            {name}
          </span>
        ))}
      </div>
      <ul className="mt-1 grid grid-cols-7 gap-1">
        {days.map((date) => {
          const count = counts.get(date) ?? 0;
          const past = date < today;
          return (
            <li key={date}>
              <button
                type="button"
                disabled={past}
                onClick={() => onPick(date)}
                // Полоса знает только горячие дни: у остальных сроки могут быть, но меньше
                // порога, — «сроков 0» было бы неправдой, поэтому у них только дата.
                aria-label={count > 0 ? cellLabel(t, date, count, 0, true) : dayTitle(date)}
                className={cn(
                  'numeric flex h-10 w-full flex-col items-center justify-center rounded-[var(--radius-sm)] text-xs',
                  'transition-colors duration-[var(--motion-fast)]',
                  past
                    ? 'text-ink-muted/50'
                    : count > 0
                      ? 'bg-burn-soft font-semibold text-burn-ink hover:bg-burn-soft/70'
                      : 'bg-sunken text-ink hover:bg-hover',
                  date === today && 'ring-2 ring-accent',
                )}
              >
                <span>{Number(date.slice(8))}</span>
                {count > 0 ? <span className="text-[10px] leading-none">{count}</span> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

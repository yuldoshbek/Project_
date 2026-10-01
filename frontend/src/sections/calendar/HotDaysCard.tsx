/**
 * «Где неделя перегружена?» — вопрос раздела (ТЗ 5): «24.09 — 3 срока и мероприятие».
 *
 * Ответ — горячие дни на окно вперёд, которое прислал сервер вместе с ними: сколько
 * незакрытых сроков сходится в один день и каких. Действие — касание: календарь открывает
 * этот день, и видно, что именно там и что можно развести.
 */

import { Flame } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { formatDateTime } from '@/shared/time';
import { Card } from '@/shared/ui/Card';

import type { HotDay } from './model';
import { hotDayTitle, hotText, hotWindowText } from './text';

interface HotDaysCardProps {
  hot: HotDay[];
  windowDays: number;
  threshold: number;
  today: string;
  asOf: string;
  onPick: (date: string) => void;
}

export function HotDaysCard({ hot, windowDays, threshold, today, asOf, onPick }: HotDaysCardProps) {
  const { t } = useTranslation();

  return (
    <Card
      title={t('calendar.hot.title')}
      question={t('calendar.hot.question', {
        threshold,
        window: hotWindowText(t, windowDays),
      })}
      freshness={t('pult.asOf', { when: formatDateTime(asOf) })}
    >
      {hot.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('calendar.hot.none')}</p>
      ) : (
        <>
          <p className="mb-2 text-sm font-semibold text-burn-ink">
            {t('calendar.hot.answer', { count: hot.length })}
          </p>
          <ul className="flex flex-col">
            {hot.map((day) => (
              <li key={day.date}>
                <button
                  type="button"
                  onClick={() => onPick(day.date)}
                  className="flex min-h-touch w-full items-start gap-2 rounded-[var(--radius)] px-2 py-1.5 text-left hover:bg-hover md:min-h-9 md:py-1"
                >
                  <Flame className="mt-0.5 size-4 shrink-0 text-burn-ink" aria-hidden="true" />
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm font-medium text-ink-strong">
                      {hotDayTitle(t, day.date, today)}
                    </span>
                    <span className="text-xs text-ink">{hotText(t, day)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

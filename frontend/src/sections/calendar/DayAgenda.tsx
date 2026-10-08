/**
 * Выбранный день — всё, что в него сходится. Горячий день назван словами: сколько сроков и
 * каких. На сегодняшнем дне сверху — то, у чего срок прошёл, а работа не закрыта: оно тоже
 * «сегодня».
 *
 * Горячий день считается по всем источникам, а фильтр прячет часть из них: поэтому
 * скрытое названо числом с кнопкой «показать всё» — иначе «горячий день: 3 срока» стоял бы
 * над «сроков нет».
 */

import { Flame } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Card } from '@/shared/ui/Card';

import { ItemRow } from './ItemRow';
import type { CalendarItem, HotDay } from './model';
import { dayTitle, hotDayText, relativeDay } from './text';

interface DayAgendaProps {
  date: string;
  today: string;
  items: CalendarItem[];
  /** Сколько дат этого дня спрятал фильтр источников. */
  hidden: number;
  hot: HotDay | undefined;
  overdue: CalendarItem[];
  /** Месяц выбранного дня ещё грузится — день приглушён, а не объявлен пустым. */
  stale: boolean;
  onOpen: (item: CalendarItem) => void;
  onShowAll: () => void;
}

export function DayAgenda({
  date,
  today,
  items,
  hidden,
  hot,
  overdue,
  stale,
  onOpen,
  onShowAll,
}: DayAgendaProps) {
  const { t } = useTranslation();

  return (
    <Card
      title={dayTitle(date)}
      question={relativeDay(t, date, today)}
      className={cn('transition-opacity duration-[var(--motion-fast)]', stale && 'opacity-60')}
    >
      {hot ? (
        <p className="mb-2 flex items-start gap-2 rounded-[var(--radius)] bg-burn-soft px-3 py-2 text-sm text-burn-ink">
          <Flame className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{hotDayText(t, hot)}</span>
        </p>
      ) : null}

      {date === today && overdue.length > 0 ? <Overdue items={overdue} onOpen={onOpen} /> : null}

      {items.length === 0 && hidden === 0 ? (
        stale ? null : (
          <p className="text-sm text-ink-muted">{t('calendar.day.empty')}</p>
        )
      ) : (
        <ul className="flex flex-col">
          {items.map((item) => (
            <li key={item.id}>
              <ItemRow item={item} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}

      {hidden > 0 ? <Hidden count={hidden} onShowAll={onShowAll} /> : null}
    </Card>
  );
}

/** «Скрыто фильтром: 2 · Показать всё» — у дня, часть дат которого спрятал фильтр. */
export function Hidden({ count, onShowAll }: { count: number; onShowAll: () => void }) {
  const { t } = useTranslation();
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-ink-muted">
      <span>{t('calendar.filter.hidden', { count })}</span>
      <button
        type="button"
        onClick={onShowAll}
        className="inline-flex min-h-touch items-center rounded-[var(--radius)] px-1 font-medium text-accent-ink hover:bg-hover md:min-h-7"
      >
        {t('calendar.filter.showAll')}
      </button>
    </p>
  );
}

/**
 * Срок прошёл, работа не закрыта — свёрнуто: оно на Пульте, здесь — чтобы не забыть в
 * «сегодня». Счёт — не ступень Пульта «просрочено»: запись с вопросом руководителю здесь
 * тоже, со своей ступенью в строке.
 */
export function Overdue({
  items,
  onOpen,
}: {
  items: CalendarItem[];
  onOpen: (item: CalendarItem) => void;
}) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(false);
  return (
    <section aria-label={t('calendar.overdue.title', { count: items.length })} className="mb-3">
      <button
        type="button"
        aria-expanded={shown}
        onClick={() => setShown(!shown)}
        className="flex min-h-touch w-full items-center rounded-[var(--radius)] px-2 text-left text-sm font-medium text-burn-ink hover:bg-hover"
      >
        {t('calendar.overdue.title', { count: items.length })}
      </button>
      {shown ? (
        <ul className="flex flex-col border-b border-line pb-2">
          {items.map((item) => (
            <li key={item.id}>
              <ItemRow item={item} onOpen={onOpen} withDate={formatDate(item.date)} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

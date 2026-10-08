/**
 * Таймлайн — ноутбук и монитор: полоса от начала до срока, вехи ромбами, исходный срок
 * тонкой чертой, «сегодня» вертикалью (ТЗ 5, вид «таймлайн»).
 *
 * Окно задают обычные проекты, а не программы, и не шире полугода назад и года вперёд:
 * многолетняя программа растянула бы шкалу на годы, и полугодовые проекты сжались бы в
 * точки. У программ свой раздел со своей шкалой. Полоса, которая выходит за окно,
 * обрезается прямым краем — видно, что она продолжается.
 *
 * Ширина — в процентах, а не в пикселях: таймлайн заполняет экран и не даёт горизонтальной
 * прокрутки ни на ноутбуке, ни на мониторе.
 */

import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';

import { TERMINAL, type ProjectCard } from './model';
import { dueText } from './text';

const DAY_MS = 86_400_000;
const BACK_DAYS = 180;
const AHEAD_DAYS = 365;

/** Цвет полосы — ступень лестницы; классы целиком, чтобы Tailwind их нашёл. */
const BAR = { call: 'bg-call', burn: 'bg-burn', wait: 'bg-wait' } as const;

const monthFormat = new Intl.DateTimeFormat('ru-RU', { month: 'short', timeZone: 'UTC' });

function dayOf(date: string): number {
  return Math.round(Date.parse(`${date.slice(0, 10)}T00:00:00Z`) / DAY_MS);
}

function monthStart(day: number): number {
  const date = new Date(day * DAY_MS);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1) / DAY_MS;
}

function nextMonth(day: number): number {
  const date = new Date(day * DAY_MS);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1) / DAY_MS;
}

interface TimelineProps {
  items: ProjectCard[];
  /** Сегодня по Ташкенту, `YYYY-MM-DD`: от него окно и вертикаль. */
  today: string;
  onOpen: (id: string) => void;
}

export function Timeline({ items, today, onOpen }: TimelineProps) {
  const { t } = useTranslation();
  const now = dayOf(today);

  const scale = items.some((card) => !card.is_multiyear)
    ? items.filter((card) => !card.is_multiyear)
    : items;
  const earliest = Math.min(...scale.map((card) => dayOf(card.started_on)), now);
  const latest = Math.max(
    ...scale.flatMap((card) => [dayOf(card.due_on), dayOf(card.original_due_on)]),
    now,
  );
  const from = monthStart(Math.max(earliest, now - BACK_DAYS));
  const to = nextMonth(Math.min(latest, now + AHEAD_DAYS));
  const span = to - from;
  const at = (day: number) => ((Math.min(Math.max(day, from), to) - from) / span) * 100;

  // Год — отдельной строкой над месяцами: «март 2026» рядом с «апр» не помещается в
  // ширину месяца на ноутбуке, и подписи наезжают друг на друга.
  const months: { day: number; label: string; year: number | null }[] = [];
  for (let day = from; day < to; day = nextMonth(day)) {
    const date = new Date(day * DAY_MS);
    months.push({
      day,
      label: monthFormat.format(date).replace('.', ''),
      year: date.getUTCMonth() === 0 || day === from ? date.getUTCFullYear() : null,
    });
  }

  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4 shadow-card">
      <div className="grid grid-cols-[minmax(0,18rem)_minmax(0,1fr)] gap-x-4">
        {/* Шкала месяцев */}
        <div />
        <div className="relative h-10 border-b border-line text-xs text-ink-muted">
          {months.map((month) => (
            <span
              key={month.day}
              className="absolute top-0 flex h-full flex-col justify-between overflow-hidden border-l border-line pl-1"
              style={{
                left: `${at(month.day)}%`,
                width: `${at(nextMonth(month.day)) - at(month.day)}%`,
              }}
            >
              <span className="numeric font-medium whitespace-nowrap text-ink">
                {month.year ?? ''}
              </span>
              <span className="truncate">{month.label}</span>
            </span>
          ))}
        </div>

        {items.map((card) => {
          const start = dayOf(card.started_on);
          const due = dayOf(card.due_on);
          const original = dayOf(card.original_due_on);
          const terminal = TERMINAL.has(card.status);
          const left = at(start);
          const width = Math.max(at(due) - left, 0.6);
          return (
            <div key={card.id} className="contents">
              <button
                type="button"
                onClick={() => onOpen(card.id)}
                className="flex min-w-0 flex-col items-start border-b border-line py-2 text-left hover:text-accent-ink"
              >
                <span className="w-full truncate text-sm font-medium text-ink-strong">
                  {card.title}
                </span>
                <span className="numeric w-full truncate text-xs text-ink-muted">
                  {card.code} · {dueText(t, card)}
                </span>
              </button>

              <button
                type="button"
                onClick={() => onOpen(card.id)}
                aria-label={`${card.title}: ${dueText(t, card)}`}
                className="relative min-h-12 border-b border-line"
              >
                {months.map((month) => (
                  <span
                    key={month.day}
                    className="absolute inset-y-0 border-l border-line/60"
                    style={{ left: `${at(month.day)}%` }}
                    aria-hidden="true"
                  />
                ))}
                <span
                  className="absolute inset-y-0 w-0.5 bg-accent/60"
                  style={{ left: `${at(now)}%` }}
                  aria-hidden="true"
                />

                <span
                  className={cn(
                    'absolute top-1/2 h-3 -translate-y-1/2',
                    start >= from && 'rounded-l-[var(--radius-pill)]',
                    due <= to && 'rounded-r-[var(--radius-pill)]',
                    terminal
                      ? 'bg-ink-muted/40'
                      : card.step
                        ? BAR[STEP_SIGNAL[card.step]]
                        : 'bg-accent/70',
                  )}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  aria-hidden="true"
                />

                {original !== due && original >= from && original <= to ? (
                  <span
                    className="absolute top-2 bottom-2 w-0.5 bg-ink-muted"
                    style={{ left: `${at(original)}%` }}
                    title={`${t('projects.timeline.original')} ${formatDate(card.original_due_on)}`}
                    aria-hidden="true"
                  />
                ) : null}

                {card.marks
                  .filter((mark) => {
                    const day = dayOf(mark.due_on);
                    return day >= from && day <= to;
                  })
                  .map((mark, index) => (
                    <span
                      key={`${mark.title}-${index}`}
                      className={cn(
                        'absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-2',
                        mark.is_passed
                          ? 'border-ink-strong bg-ink-strong'
                          : 'border-ink-strong bg-card',
                      )}
                      style={{ left: `${at(dayOf(mark.due_on))}%` }}
                      title={`${mark.title} — ${formatDate(mark.due_on)}`}
                      aria-hidden="true"
                    />
                  ))}
              </button>
            </div>
          );
        })}

        {/* Подпись вертикали «сегодня» — под последней строкой */}
        <div />
        <div className="relative h-5">
          <span
            className="absolute -top-px text-xs font-medium whitespace-nowrap text-accent-ink"
            style={{ left: `${at(now)}%`, transform: 'translateX(-50%)' }}
          >
            {t('projects.timeline.today')}
          </span>
        </div>
      </div>

      <p className="mt-3 text-xs text-ink-muted">{t('projects.timeline.legend')}</p>
    </section>
  );
}

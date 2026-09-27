/**
 * Плитка программы — телефон, где горизонта лет нет (ТЗ 6: без диаграммы Ганта).
 *
 * Вместо полосы — отсчёт до даты крупно, следующая веха и строка лет: сколько вех в каждом
 * году горизонта и сколько пройдено. Это те же вехи по годам, что на горизонте ноутбука,
 * только списком, а не на шкале.
 *
 * «Не успеваем» стоит на самой плитке: на телефоне карточка «Успеваем к дате?» ниже пяти
 * плиток, и ответ на вопрос раздела не должен ждать прокрутки.
 */

import { useTranslation } from 'react-i18next';

import { lagText } from '@/sections/projects/text';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';

import type { ProgramCard, ProgramsView } from './model';
import { byYear } from './scale';
import { stepInk } from './signal';
import { StepMark } from './StepMark';
import { countdownText, markLeftText, paceShort, readinessText } from './text';

interface ProgramTileProps {
  card: ProgramCard;
  horizon: ProgramsView['horizon'];
  onOpen: (id: string) => void;
}

export function ProgramTile({ card, horizon, onOpen }: ProgramTileProps) {
  const { t } = useTranslation();
  const next = card.milestones.find((mark) => !mark.is_passed) ?? null;
  // Прошлые годы — только если там осталось непройденное: несделанная веха прошлого года
  // не должна пропасть из виду вместе со сменой года.
  const years = byYear(card.milestones, horizon).filter(
    (group) => group.bucket !== 'before' || group.items.some((mark) => !mark.is_passed),
  );
  const moved = card.original_due_on !== card.due_on;

  return (
    <article className="rounded-[var(--radius)] border border-line bg-card shadow-card">
      <button
        type="button"
        onClick={() => onOpen(card.id)}
        className="flex w-full min-w-0 flex-col gap-2 p-3 text-left"
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {card.step ? <StepMark step={card.step} deviation={card.deviation} /> : null}
          <span className="numeric ml-auto text-xs text-ink-muted">{card.code}</span>
        </span>

        <span className="line-clamp-2 text-[15px] leading-snug font-medium text-ink-strong">
          {card.title}
        </span>

        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="numeric text-lg font-semibold text-ink-strong">
            {countdownText(t, card.days_left)}
          </span>
          <span className="numeric text-xs text-ink-muted">
            {t('programs.countdown.until', { date: formatDate(card.due_on) })}
            {moved
              ? ` · ${t('programs.countdown.original', { date: formatDate(card.original_due_on) })}`
              : null}
          </span>
        </span>

        {card.pace?.verdict === 'behind' ? (
          <span className="text-sm font-medium text-burn-ink">{paceShort(t, card.pace)}</span>
        ) : null}

        {next ? (
          <span className="flex min-w-0 items-start gap-2 text-xs">
            <span className="line-clamp-2 min-w-0 flex-1 text-ink">
              {t('programs.mark.next', { title: next.title })}
            </span>
            <span className={cn('numeric shrink-0', stepInk(next.step))}>
              {markLeftText(t, next)}
            </span>
          </span>
        ) : null}

        {/* Вехи по годам: год, пройдено из всех. Текущий год выделен — к нему вопрос
            «что должно случиться до конца года». */}
        <span className="flex flex-col gap-1">
          <span className="sr-only">{t('programs.years.title')}</span>
          <span className="grid grid-flow-col gap-1">
            {years.map((group) => {
              const passed = group.items.filter((mark) => mark.is_passed).length;
              const late = group.items.some((mark) => !mark.is_passed && mark.days_left < 0);
              const label =
                group.bucket === 'after'
                  ? t('programs.years.afterShort')
                  : group.bucket === 'before'
                    ? t('programs.years.beforeShort')
                    : String(group.bucket);
              return (
                <span
                  key={String(group.bucket)}
                  className={cn(
                    'flex min-w-0 flex-col items-center rounded-[var(--radius-sm)] px-0.5 py-1',
                    group.bucket === horizon.from ? 'bg-accent-soft' : 'bg-sunken',
                  )}
                >
                  <span className="numeric text-[11px] text-ink-muted">{label}</span>
                  <span
                    className={cn(
                      'numeric text-xs font-medium',
                      late ? 'text-burn-ink' : 'text-ink-strong',
                    )}
                  >
                    {group.items.length === 0 ? '—' : `${passed}/${group.items.length}`}
                  </span>
                </span>
              );
            })}
          </span>
        </span>

        <span className="flex items-center gap-2">
          <span
            className="h-1.5 flex-1 overflow-hidden rounded-[var(--radius-pill)] bg-sunken"
            aria-hidden="true"
          >
            <span
              className="block h-full rounded-[var(--radius-pill)] bg-accent"
              style={{ width: `${card.readiness}%` }}
            />
          </span>
          <span className="numeric text-xs text-ink-muted">{readinessText(t, card)}</span>
        </span>

        <span className="flex flex-wrap items-center gap-x-3 text-xs">
          <span className={card.lag_days > 0 ? 'text-wait-ink' : 'text-ink-muted'}>
            {lagText(t, card.lag_days)}
          </span>
          {card.subprojects.length > 0 ? (
            <span className="text-ink-muted">
              {t('programs.horizon.subprojects', { count: card.subprojects.length })}
            </span>
          ) : null}
        </span>
      </button>
    </article>
  );
}

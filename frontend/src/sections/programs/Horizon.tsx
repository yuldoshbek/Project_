/**
 * Горизонт лет — ноутбук и монитор (ТЗ 11: «горизонт лет показывает программы с вехами и
 * исходными сроками; отсчёт до даты»).
 *
 * Пять лет шкалой; программа — полоса от начала до даты, вехи — ромбами, перенесённая веха
 * тянет пунктир от исходного срока к нынешнему, исходная дата программы — тонкая черта.
 * Работа за краями горизонта обрезана прямым краем с подписью года: видно, что она
 * продолжается, и шкала не растягивается под Стратегию‑2035.
 *
 * Подпроекты раскрываются под программой — у каждого своя строка со своими вехами.
 *
 * Название вехи на шкале — только в подсказке; всё, что важно, есть без наведения
 * (ТЗ 6): в карточке программы по касанию и в «до конца года».
 */

import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';

import {
  TERMINAL,
  type ProgramCard,
  type ProgramMilestone,
  type ProgramsView,
  type Subproject,
} from './model';
import { dayOf, scaleOf, yearsOf, type Scale } from './scale';
import { markShape, stepBar } from './signal';
import { StepMark } from './StepMark';
import { countdownText, markDateText, paceShort } from './text';

interface HorizonProps {
  items: ProgramCard[];
  horizon: ProgramsView['horizon'];
  today: string;
  /** Монитор: подпроекты раскрыты сразу — места хватает. */
  expanded: boolean;
  onOpen: (id: string) => void;
}

export function Horizon({ items, horizon, today, expanded, onOpen }: HorizonProps) {
  const { t } = useTranslation();
  const scale = scaleOf(horizon);
  const years = yearsOf(horizon);
  const now = dayOf(today);
  const [open, setOpen] = useState<ReadonlySet<string>>(
    () => new Set(expanded ? items.map((card) => card.id) : []),
  );

  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <section
      aria-label={t('programs.horizon.title', horizon)}
      className="min-w-0 rounded-[var(--radius-lg)] border border-line bg-card p-4 shadow-card sm:p-5"
    >
      <header className="mb-3">
        <h2 className="text-base font-semibold text-ink-strong">
          {t('programs.horizon.title', horizon)}
        </h2>
        <p className="mt-1 text-sm text-ink-muted">{t('programs.horizon.question')}</p>
      </header>

      <div className="grid grid-cols-[minmax(0,17rem)_minmax(0,1fr)] gap-x-4">
        {/* Шкала лет */}
        <div />
        <div className="relative h-8 border-b border-line text-xs">
          {years.map((year) => {
            const left = scale.at(dayOf(`${year}-01-01`));
            const right = scale.at(dayOf(`${year + 1}-01-01`));
            return (
              <span
                key={year}
                className={cn(
                  'numeric absolute inset-y-0 flex items-center border-l border-line pl-2',
                  year === horizon.from ? 'font-semibold text-accent-ink' : 'text-ink',
                )}
                style={{ left: `${left}%`, width: `${right - left}%` }}
              >
                {year}
              </span>
            );
          })}
        </div>

        {items.map((card) => {
          const shown = open.has(card.id);
          return (
            <div key={card.id} className="contents">
              <div className="flex min-w-0 flex-col items-start gap-0.5 border-b border-line py-2">
                <button
                  type="button"
                  onClick={() => onOpen(card.id)}
                  className="w-full min-w-0 text-left hover:text-accent-ink"
                >
                  <span className="line-clamp-2 text-sm font-medium text-ink-strong">
                    {card.title}
                  </span>
                  <span className="numeric block truncate text-xs text-ink-muted">
                    {card.code} · {t('programs.countdown.until', { date: formatDate(card.due_on) })}
                  </span>
                </button>
                {/* Отсчёт и подпроекты — одной строкой: строка программы не должна быть
                    выше, чем нужно полосе, иначе пять программ не помещаются в экран. */}
                <span className="flex w-full items-center gap-2">
                  <span className="numeric text-sm font-semibold text-ink-strong">
                    {countdownText(t, card.days_left)}
                  </span>
                  {card.subprojects.length > 0 ? (
                    <button
                      type="button"
                      aria-expanded={shown}
                      onClick={() => toggle(card.id)}
                      className="ml-auto inline-flex min-h-8 shrink-0 items-center gap-1 rounded-[var(--radius-sm)] px-1 text-xs text-accent-ink hover:bg-hover"
                    >
                      {shown ? (
                        <ChevronDown className="size-3.5" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="size-3.5" aria-hidden="true" />
                      )}
                      {t('programs.horizon.subprojects', { count: card.subprojects.length })}
                    </button>
                  ) : null}
                </span>
                {/* «Не успеваем» — в строке программы, а не только в карточке рядом:
                    иначе отстающая программа на шкале выглядит как идущие по плану. */}
                {card.pace?.verdict === 'behind' ? (
                  <span className="text-xs font-medium text-burn-ink">
                    {paceShort(t, card.pace)}
                  </span>
                ) : null}
                {card.step ? <StepMark step={card.step} deviation={card.deviation} /> : null}
              </div>

              <Track
                label={[
                  t('programs.horizon.label', {
                    title: card.title,
                    countdown: countdownText(t, card.days_left),
                    passed: card.milestones.filter((mark) => mark.is_passed).length,
                    total: card.milestones.length,
                  }),
                  card.pace?.verdict === 'behind' ? paceShort(t, card.pace) : null,
                ]
                  .filter(Boolean)
                  .join(', ')}
                work={card}
                milestones={card.milestones}
                scale={scale}
                years={years}
                now={now}
                onOpen={() => onOpen(card.id)}
              />

              {shown
                ? card.subprojects.map((sub) => (
                    <SubprojectRow
                      key={sub.id}
                      sub={sub}
                      roomy={expanded}
                      scale={scale}
                      years={years}
                      now={now}
                      onOpen={() => onOpen(card.id)}
                    />
                  ))
                : null}
            </div>
          );
        })}

        {/* Подпись вертикали «сегодня» — под последней строкой */}
        <div />
        <div className="relative h-5">
          <span
            className="absolute -top-px text-xs font-medium whitespace-nowrap text-accent-ink"
            style={{ left: `${scale.at(now)}%`, transform: 'translateX(-50%)' }}
          >
            {t('programs.horizon.today')}
          </span>
        </div>
      </div>

      <p className="mt-3 text-xs text-ink-muted">{t('programs.horizon.legend')}</p>
    </section>
  );
}

function SubprojectRow({
  sub,
  roomy,
  scale,
  years,
  now,
  onOpen,
}: {
  sub: Subproject;
  /** Монитор: подпись крупнее — его смотрят издалека, на совещании. */
  roomy: boolean;
  scale: Scale;
  years: number[];
  now: number;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="flex min-w-0 flex-col items-start gap-1 border-b border-line py-1.5 pl-5">
        <button
          type="button"
          onClick={onOpen}
          className="w-full min-w-0 text-left hover:text-accent-ink"
        >
          <span
            className={cn(
              'block w-full truncate font-medium text-ink',
              roomy ? 'text-sm' : 'text-xs',
            )}
          >
            {sub.title}
          </span>
          <span className="numeric block w-full truncate text-xs text-ink-muted">
            {sub.code} · {t('programs.countdown.until', { date: formatDate(sub.due_on) })}
          </span>
        </button>
        {sub.step ? <StepMark step={sub.step} deviation={sub.deviation} /> : null}
      </div>
      <Track
        label={t('programs.horizon.subLabel', {
          title: sub.title,
          date: formatDate(sub.due_on),
        })}
        work={sub}
        milestones={sub.milestones}
        scale={scale}
        years={years}
        now={now}
        thin
        onOpen={onOpen}
      />
    </>
  );
}

function Track({
  label,
  work,
  milestones,
  scale,
  years,
  now,
  thin = false,
  onOpen,
}: {
  label: string;
  work: Pick<ProgramCard, 'started_on' | 'due_on' | 'original_due_on' | 'step' | 'status'>;
  milestones: ProgramMilestone[];
  scale: Scale;
  years: number[];
  now: number;
  thin?: boolean;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const start = dayOf(work.started_on);
  const due = dayOf(work.due_on);
  const original = dayOf(work.original_due_on);
  const left = scale.at(start);
  const width = Math.max(scale.at(due) - left, 0.6);
  const closed = TERMINAL.has(work.status);

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={label}
      className={cn('relative border-b border-line', thin ? 'min-h-9' : 'min-h-14')}
    >
      {years.map((year) => (
        <span
          key={year}
          className="absolute inset-y-0 border-l border-line/60"
          style={{ left: `${scale.at(dayOf(`${year}-01-01`))}%` }}
          aria-hidden="true"
        />
      ))}
      <span
        className="absolute inset-y-0 w-0.5 bg-accent/60"
        style={{ left: `${scale.at(now)}%` }}
        aria-hidden="true"
      />

      <span
        className={cn(
          'absolute top-1/2 -translate-y-1/2',
          thin ? 'h-1.5' : 'h-3',
          start >= scale.from && 'rounded-l-[var(--radius-pill)]',
          due < scale.to && 'rounded-r-[var(--radius-pill)]',
          closed ? 'bg-ink-muted/40' : stepBar(work.step),
        )}
        style={{ left: `${left}%`, width: `${width}%` }}
        aria-hidden="true"
      />

      {due >= scale.to ? (
        <span
          className="numeric absolute top-0.5 right-1 text-[11px] text-ink-muted"
          aria-hidden="true"
        >
          {t('programs.horizon.beyond', { year: work.due_on.slice(0, 4) })}
        </span>
      ) : null}
      {start < scale.from ? (
        <span
          className="numeric absolute top-0.5 left-1 text-[11px] text-ink-muted"
          aria-hidden="true"
        >
          {t('programs.horizon.since', { year: work.started_on.slice(0, 4) })}
        </span>
      ) : null}

      {original !== due && scale.inside(original) ? (
        <span
          className={cn(
            'absolute top-1/2 w-0.5 -translate-y-1/2 bg-ink-muted',
            thin ? 'h-4' : 'h-6',
          )}
          style={{ left: `${scale.at(original)}%` }}
          title={t('programs.countdown.original', { date: formatDate(work.original_due_on) })}
          aria-hidden="true"
        />
      ) : null}

      {milestones.map((mark) => {
        const day = dayOf(mark.due_on);
        // Непройденная веха раньше горизонта не исчезает со сменой года: она прижата к
        // левому краю — несделанное прошлого года всё ещё надо сделать.
        const late = !mark.is_passed && day < scale.from;
        if (!scale.inside(day) && !late) return null;
        const was = dayOf(mark.original_due_on);
        // Срочная веха крупнее и в кольце цвета карточки: у «сегодня» она иначе сливается с
        // соседними ромбами, а один цвет контура — не различие (WCAG 1.4.1).
        const urgent = !mark.is_passed && mark.step !== null;
        return (
          <span key={mark.id} aria-hidden="true">
            {/* Перенос — над полосой: черта на исходном сроке и пунктир к нынешнему. На
                самой полосе пунктир тонет в её цвете. */}
            {was !== day && scale.inside(was) ? (
              <>
                <span
                  className={cn(
                    'absolute border-t border-dashed border-ink',
                    thin ? 'top-[calc(50%-7px)]' : 'top-[calc(50%-11px)]',
                  )}
                  style={{
                    left: `${scale.at(Math.min(was, day))}%`,
                    width: `${Math.abs(scale.at(day) - scale.at(was))}%`,
                  }}
                />
                <span
                  className={cn(
                    'absolute h-1.5 w-px bg-ink',
                    thin ? 'top-[calc(50%-10px)]' : 'top-[calc(50%-14px)]',
                  )}
                  style={{ left: `${scale.at(was)}%` }}
                />
              </>
            ) : null}
            <span
              className={cn(
                'absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rotate-45 border-2 ring-2 ring-card',
                urgent ? 'z-10' : null,
                urgent ? (thin ? 'size-3' : 'size-3.5') : thin ? 'size-2' : 'size-2.5',
                markShape(mark),
              )}
              style={{ left: `${scale.at(day)}%` }}
              title={`${mark.title} — ${markDateText(t, mark)}`}
            />
          </span>
        );
      })}
    </button>
  );
}

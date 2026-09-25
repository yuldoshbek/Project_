/**
 * Строка лестницы внимания и её раскрытие.
 *
 * Строка несёт ровно четыре вещи (PLAN-10X, «Пульт на iPhone»): сигнал словом и цветом →
 * что это и кто держит → на сколько отклонились → что нажать. Больше в строку не кладётся:
 * пять строк обязаны уместиться на экране телефона без прокрутки.
 *
 * Основное решение — одно касание, и оно самое частое на этой ступени (`STEP_DECISIONS`).
 * Остальные решения, вопрос целиком и сроки — в раскрытии: на телефоне под строкой, на
 * мониторе в средней панели.
 *
 * Решение принимает руководитель, вопрос ставит помощник (ТЗ 3.7, допущение V12). Кнопки
 * зависят от того, кто смотрит, а данные — нет: оба видят всё.
 */

import { ChevronDown } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Signal } from '@/shared/ui/Signal';

import { STEP_DECISIONS, STEP_SIGNAL, rowKey, type DecisionKind, type PultRow } from './model';
import { deviationText, dueText } from './text';

export type Viewer = 'leader' | 'assistant';

export interface RowActions {
  decide: (row: PultRow, kind: DecisionKind) => void;
  ask: (row: PultRow, text: string) => void;
}

interface LadderRowProps {
  row: PultRow;
  viewer: Viewer;
  actions: RowActions;
  busy: boolean;
  /** Раскрыта ли строка на месте (телефон и ноутбук). */
  expanded: boolean;
  /** Выбрана ли строка для средней панели (монитор). */
  selected: boolean;
  onToggle: () => void;
  /** На мониторе подробности живут в средней панели, а не под строкой. */
  detailsInline: boolean;
  /**
   * Телефон: название в одну строку и без стрелки раскрытия — раскрывает касание строки.
   * Иначе пять строк не помещаются на экран без прокрутки: кнопка решения сжимает
   * название до трёх строк, и каждая строка лестницы занимает треть экрана.
   */
  compact?: boolean;
}

export function LadderRow({
  row,
  viewer,
  actions,
  busy,
  expanded,
  selected,
  onToggle,
  detailsInline,
  compact = false,
}: LadderRowProps) {
  const { t } = useTranslation();
  const signal = STEP_SIGNAL[row.step];
  const primary = STEP_DECISIONS[row.step][0];
  const detailsId = `row-${rowKey(row)}`;

  const who = row.responsible?.name ?? t('pult.noHolder');
  const subtitle = [who, t(`pult.rowSections.${row.section}`), row.context]
    .filter(Boolean)
    .join(' · ');

  return (
    <li
      className={cn(
        'rounded-[var(--radius)] border bg-card transition-colors duration-[var(--motion-fast)]',
        selected ? 'border-line-accent bg-accent-soft/40' : 'border-line',
      )}
    >
      <div className={cn('flex items-center', compact ? 'gap-2 p-2.5' : 'gap-3 p-3')}>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={detailsInline ? expanded : undefined}
          aria-controls={detailsInline ? detailsId : undefined}
          className="min-w-0 flex-1 text-left"
        >
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Signal state={signal}>{t(`pult.steps.${row.step}`)}</Signal>
            <span className="numeric text-xs font-medium text-ink">{deviationText(t, row)}</span>
          </span>
          <span
            className={cn(
              'mt-1 block text-[15px] leading-snug font-medium text-ink-strong',
              // Раскрытая строка показывает название целиком: обрезанное — это вопрос,
              // на который ответа нет нигде, кроме этой строки.
              expanded ? '' : compact ? 'truncate' : 'line-clamp-2',
            )}
          >
            {row.title}
          </span>
          <span className="mt-0.5 block truncate text-xs text-ink-muted">{subtitle}</span>
        </button>

        <div className="flex shrink-0 items-center gap-1">
          {viewer === 'leader' ? (
            <Button
              look={row.step === 'awaiting_decision' ? 'primary' : 'plain'}
              disabled={busy}
              onClick={() => actions.decide(row, primary)}
            >
              {t(`pult.decisions.${primary}`)}
            </Button>
          ) : row.question ? null : (
            <Button look="plain" disabled={busy} onClick={onToggle}>
              {t('pult.ask.action')}
            </Button>
          )}
          {detailsInline && !compact ? (
            <Button
              look="quiet"
              size="icon"
              onClick={onToggle}
              aria-label={t(expanded ? 'pult.less' : 'pult.more')}
              aria-expanded={expanded}
              aria-controls={detailsId}
            >
              <ChevronDown
                className={cn(
                  'size-5 transition-transform duration-[var(--motion)]',
                  expanded && 'rotate-180',
                )}
                aria-hidden="true"
              />
            </Button>
          ) : null}
        </div>
      </div>

      {detailsInline && expanded ? (
        <div id={detailsId} className={cn('border-t border-line', compact ? 'p-2.5' : 'p-3')}>
          <RowDetails row={row} viewer={viewer} actions={actions} busy={busy} />
        </div>
      ) : null}
    </li>
  );
}

/** Всё о строке: вопрос, сроки, последнее решение и все решения, а не только основное. */
export function RowDetails({
  row,
  viewer,
  actions,
  busy,
}: {
  row: PultRow;
  viewer: Viewer;
  actions: RowActions;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const due = dueText(t, row);

  return (
    <div className="flex flex-col gap-3 text-sm">
      {row.question ? (
        <div className="rounded-[var(--radius)] bg-call-soft p-3 text-call-ink">
          <p className="text-xs font-medium">{t('pult.question')}</p>
          <p className="mt-1">{row.question.text}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-ink-muted">
        {due ? <p className="numeric">{due}</p> : null}
        {row.last_decision ? (
          <p>
            {t('pult.lastDecision', {
              what: t(`pult.decided.${row.last_decision.kind}`),
              when: formatDate(row.last_decision.decided_on),
            })}
          </p>
        ) : null}
      </div>

      {viewer === 'leader' ? (
        <div className="flex flex-wrap gap-2">
          {STEP_DECISIONS[row.step].map((kind, index) => (
            <Button
              key={kind}
              look={index === 0 ? 'primary' : 'plain'}
              disabled={busy}
              onClick={() => actions.decide(row, kind)}
            >
              {t(`pult.decisions.${kind}`)}
            </Button>
          ))}
        </div>
      ) : row.question ? (
        <p className="text-call-ink">{t('pult.ask.waiting')}</p>
      ) : (
        <AskForm row={row} actions={actions} busy={busy} />
      )}
    </div>
  );
}

/** Вопрос руководителю: помощник ставит его одной строкой, текст подсказан. */
function AskForm({ row, actions, busy }: { row: PultRow; actions: RowActions; busy: boolean }) {
  const { t } = useTranslation();
  const [text, setText] = useState(() => t('pult.ask.suggestion'));
  const inputId = `ask-${rowKey(row)}`;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (value) actions.ask(row, value);
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-xs font-medium text-ink-muted">
        {t('pult.ask.label')}
      </label>
      <textarea
        id={inputId}
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={2}
        className="w-full rounded-[var(--radius)] border border-line-strong bg-card p-2 text-[15px] text-ink"
      />
      <div>
        <Button type="submit" look="primary" disabled={busy || !text.trim()}>
          {t('pult.ask.send')}
        </Button>
      </div>
    </form>
  );
}

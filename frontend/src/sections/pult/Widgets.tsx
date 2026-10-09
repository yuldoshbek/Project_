/**
 * Карточки Пульта рядом с лестницей. У каждой — вопрос руководителя, ответ и действие
 * (инвариант 3): показатель без действия сюда не попадает.
 *
 * - «Что сорвётся за 14 дней?» — сроки всех разделов на две недели вперёд по датам;
 *   действие — решение по строке, пока срок ещё не сорвался;
 * - «С прошлого визита» — что изменилось, пока руководитель не смотрел;
 * - «Кто держит» — кому звонить первым; касание показывает строки этого человека;
 * - «Держим ли мы свои сроки?» — переносы и суммарный сдвиг; действие — переутвердить срок.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { dayTitle, relativeDay } from '@/sections/calendar/text';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime, formatTime, localDay } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import {
  LADDER,
  ON_TRACK_DECISIONS,
  STEP_DECISIONS,
  STEP_SIGNAL,
  rowKey,
  type DeadlineMoves,
  type DecisionKind,
  type Change,
  type Holder,
  type Person,
  type SoonRow,
} from './model';
import { rowTitle } from './text';

/** Сколько изменений видно до «показать все»: на телефоне карточка не должна съесть экран. */
const CHANGES_PREVIEW = 3;

/**
 * Сколько сроков горизонта видно до «показать все». На телефоне карточка стоит под
 * лестницей и не должна её вытеснить; на ноутбуке и мониторе она первая в правой колонке.
 */
const SOON_PREVIEW = { compact: 3, wide: 6 } as const;

function soonDecisions(row: SoonRow): readonly DecisionKind[] {
  return row.step === 'on_track' ? ON_TRACK_DECISIONS : STEP_DECISIONS[row.step];
}

export function SoonCard({
  soon,
  days,
  asOf,
  canDecide,
  busy,
  compact,
  onDecide,
}: {
  soon: SoonRow[];
  days: number;
  asOf: string;
  canDecide: boolean;
  busy: boolean;
  compact: boolean;
  onDecide: (row: SoonRow, kind: DecisionKind) => void;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const limit = compact ? SOON_PREVIEW.compact : SOON_PREVIEW.wide;
  const shown = all ? soon : soon.slice(0, limit);
  const today = localDay(asOf);

  // Строки уже идут по дате (так их отдаёт сервер) — группы собираются одним проходом.
  const groups: { day: string; rows: SoonRow[] }[] = [];
  for (const row of shown) {
    const day = row.due_on ?? today;
    const last = groups.at(-1);
    if (last?.day === day) last.rows.push(row);
    else groups.push({ day, rows: [row] });
  }

  const first = soon[0];

  return (
    <Card
      title={t('pult.soon.title', { days })}
      question={t('pult.soon.question')}
      freshness={t('pult.asOf', { when: formatDateTime(asOf) })}
    >
      {!first ? (
        <Empty label={t('pult.soon.none', { days })} />
      ) : (
        <>
          <p className="numeric text-[15px] font-semibold text-ink-strong">
            {t('pult.soon.answer', {
              count: soon.length,
              when: relativeDay(t, first.due_on ?? today, today),
            })}
          </p>
          <div className="mt-3 flex flex-col gap-3">
            {groups.map((group) => (
              <div key={group.day}>
                <p className="numeric text-xs font-semibold text-ink-muted">
                  {dayTitle(group.day)} · {relativeDay(t, group.day, today)}
                </p>
                <ul className="mt-1 flex flex-col divide-y divide-line">
                  {group.rows.map((row) => {
                    const key = rowKey(row);
                    const [primary, ...others] = soonDecisions(row);
                    const expanded = open === key;
                    const who = [
                      row.responsible?.name ?? t('pult.noHolder'),
                      t(`pult.rowSections.${row.section}`),
                    ].join(' · ');
                    return (
                      <li key={key} className="py-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            className="min-w-0 flex-1 text-left"
                            onClick={() => setOpen(expanded ? null : key)}
                            aria-expanded={canDecide ? expanded : undefined}
                          >
                            <span
                              className={cn(
                                'block text-sm leading-snug font-medium text-ink-strong',
                                !expanded && 'line-clamp-2',
                              )}
                            >
                              {rowTitle(t, row)}
                            </span>
                            <span className="mt-1 flex min-w-0 items-center gap-2">
                              <Signal
                                state={row.step === 'on_track' ? 'calm' : STEP_SIGNAL[row.step]}
                              >
                                {row.step === 'on_track'
                                  ? t('pult.counters.onTrack')
                                  : t(`pult.steps.${row.step}`)}
                              </Signal>
                              <span className="truncate text-xs text-ink-muted">{who}</span>
                            </span>
                          </button>
                          {canDecide && primary ? (
                            <Button
                              look="plain"
                              disabled={busy}
                              onClick={() => onDecide(row, primary)}
                            >
                              {t(`pult.decisions.${primary}`)}
                            </Button>
                          ) : null}
                        </div>
                        {canDecide && expanded ? (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {others.map((kind) => (
                              <Button
                                key={kind}
                                look="plain"
                                disabled={busy}
                                onClick={() => onDecide(row, kind)}
                              >
                                {t(`pult.decisions.${kind}`)}
                              </Button>
                            ))}
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
          {soon.length > limit ? (
            <Button className="mt-2" look="quiet" onClick={() => setAll(!all)}>
              {t(all ? 'pult.less' : 'pult.soon.all', { count: soon.length })}
            </Button>
          ) : null}
        </>
      )}
    </Card>
  );
}

export function SinceCard({
  changes,
  lastVisitAt,
}: {
  changes: Change[];
  lastVisitAt: string | null;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const shown = all ? changes : changes.slice(0, CHANGES_PREVIEW);

  return (
    <Card
      title={t('pult.since.title')}
      question={t('pult.since.question')}
      freshness={
        lastVisitAt ? t('pult.since.since', { when: formatDateTime(lastVisitAt) }) : undefined
      }
    >
      {changes.length === 0 ? (
        <Empty label={t('pult.since.none')} />
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {shown.map((change, index) => (
              // Порядковый номер в ключе нужен: две правки одной записи в одной транзакции
              // приходят с одинаковым временем — так перенос вехи дважды давал два
              // одинаковых ключа, и React терял одну из строк.
              <li
                key={`${change.kind}-${change.entity_id}-${index}`}
                className="flex gap-3 text-sm"
              >
                <time className="w-11 shrink-0 text-ink-muted" dateTime={change.at}>
                  {formatTime(change.at)}
                </time>
                <span className="min-w-0">
                  <span className="block text-xs font-medium text-ink-muted">
                    {t(`pult.since.kinds.${change.kind}`)}
                  </span>
                  <span className="block text-ink">{rowTitle(t, change)}</span>
                  {change.moved ? (
                    <span className="numeric block text-xs text-wait-ink">
                      {t('pult.dueMoved', {
                        from: formatDate(change.moved.from),
                        to: formatDate(change.moved.to),
                      })}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
          {changes.length > CHANGES_PREVIEW ? (
            <Button className="mt-2" look="quiet" onClick={() => setAll(!all)}>
              {t(all ? 'pult.less' : 'pult.ladder.showAll')}
            </Button>
          ) : null}
        </>
      )}
    </Card>
  );
}

export function HoldersCard({
  holders,
  active,
  onPick,
}: {
  holders: Holder[];
  active: string | null;
  onPick: (person: Person) => void;
}) {
  const { t } = useTranslation();

  return (
    <Card title={t('pult.holders.title')} question={t('pult.holders.question')}>
      {holders.length === 0 ? (
        <Empty label={t('pult.holders.none')} />
      ) : (
        <ul className="flex flex-col gap-1">
          {holders.map((holder) => {
            // Только ненулевые ступени: «просрочено 0» — это пустые данные, показанные
            // нулём, а ТЗ 5 запрещает именно это.
            const parts = LADDER.filter((step) => holder.counts[step] > 0).map(
              (step) => `${t(`pult.steps.${step}`).toLowerCase()} ${holder.counts[step]}`,
            );
            return (
              <li key={holder.person.id}>
                <button
                  type="button"
                  onClick={() => onPick(holder.person)}
                  aria-pressed={active === holder.person.id}
                  aria-label={t('pult.holders.show', { name: holder.person.name })}
                  className={cn(
                    'flex min-h-touch w-full items-center gap-3 rounded-[var(--radius)] px-2 py-2 text-left',
                    'transition-colors duration-[var(--motion-fast)] hover:bg-hover',
                    active === holder.person.id && 'bg-accent-soft',
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-ink-strong">
                      {holder.person.name}
                    </span>
                    <span className="block truncate text-xs text-ink-muted">
                      {parts.join(' · ')}
                    </span>
                  </span>
                  <Signal state={STEP_SIGNAL[holder.worst]}>
                    {t('pult.holders.rows', { count: holder.total })}
                  </Signal>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function MovesCard({
  moves,
  canDecide,
  busy,
  onReapprove,
}: {
  moves: DeadlineMoves;
  canDecide: boolean;
  busy: boolean;
  onReapprove: (item: DeadlineMoves['items'][number]) => void;
}) {
  const { t } = useTranslation();

  return (
    <Card title={t('pult.moves.title')} question={t('pult.moves.question')}>
      <p className="numeric text-sm font-medium text-ink-strong">
        {t('pult.moves.answer', {
          days: moves.period_days,
          moves: moves.moves,
          shift: moves.total_shift_days,
        })}
      </p>
      <ul className="mt-3 flex flex-col gap-3">
        {moves.items.map((item) => {
          const history = [
            t('pult.dueMoved', {
              from: formatDate(item.original_due_on),
              to: item.due_on ? formatDate(item.due_on) : '—',
            }),
            item.moves > 1 ? t('pult.moves.times', { count: item.moves }) : null,
          ]
            .filter(Boolean)
            .join(' · ');
          return (
            <li
              key={`${item.section}:${item.entity_id}`}
              className="flex items-center gap-3 text-sm"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-ink">{rowTitle(t, item)}</span>
                <span className="numeric block text-xs text-wait-ink">{history}</span>
              </span>
              {canDecide ? (
                <Button disabled={busy} onClick={() => onReapprove(item)}>
                  {t('pult.moves.reapprove')}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

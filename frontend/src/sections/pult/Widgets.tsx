/**
 * Карточки Пульта рядом с лестницей. У каждой — вопрос руководителя, ответ и действие
 * (инвариант 3): показатель без действия сюда не попадает.
 *
 * - «С прошлого визита» — что изменилось, пока руководитель не смотрел;
 * - «Кто держит» — кому звонить первым; касание показывает строки этого человека;
 * - «Держим ли мы свои сроки?» — переносы и суммарный сдвиг; действие — переутвердить срок.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime, formatTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import {
  LADDER,
  STEP_SIGNAL,
  type DeadlineMoves,
  type Change,
  type Holder,
  type Person,
} from './model';
import { rowTitle } from './text';

/** Сколько изменений видно до «показать все»: на телефоне карточка не должна съесть экран. */
const CHANGES_PREVIEW = 3;

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

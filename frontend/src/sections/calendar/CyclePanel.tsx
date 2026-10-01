/**
 * Годовой цикл — правило и даты на год вперёд (ТЗ 3.1).
 *
 * Хранится правило, а не даты: система разворачивает его сама, и перенос правила не
 * оставляет старых дат. Цикл отменяют, а не удаляют — запись о нём остаётся в журнале;
 * отменяет помощник, по версии, которую видел.
 *
 * Дат на год вперёд может не быть: цикл «раз в три года» два года из трёх ждёт. Тогда
 * названа ближайшая дата — чтобы «дат нет» не читалось как «цикл сломан».
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { formatDate } from '@/shared/time';
import { Block } from '@/shared/ui/Block';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';

import type { CycleDetail } from './model';
import { ruleText } from './text';
import { useCancelCycle, useCycle } from './useCalendar';

interface CyclePanelProps {
  id: string;
  canEdit: boolean;
  onCancelled: () => void;
}

export function CyclePanel({ id, canEdit, onCancelled }: CyclePanelProps) {
  const cycle = useCycle(id);
  if (cycle.isPending) return <Loading />;
  if (cycle.isError) {
    return <Failure detail={describeError(cycle.error)} onRetry={() => void cycle.refetch()} />;
  }
  return <Panel cycle={cycle.data} canEdit={canEdit} onCancelled={onCancelled} />;
}

function Panel({
  cycle,
  canEdit,
  onCancelled,
}: {
  cycle: CycleDetail;
  canEdit: boolean;
  onCancelled: () => void;
}) {
  const { t } = useTranslation();
  const cancel = useCancelCycle();
  const [asking, setAsking] = useState(false);
  // Версия — та, что видел человек, когда решил отменить (инвариант 15).
  const [version, setVersion] = useState(cycle.version);

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <p className="text-xs text-ink-muted">{t('calendar.kinds.cycle')}</p>
        <h2 className="text-lg leading-snug font-semibold text-ink-strong">{cycle.title}</h2>
        <p className="text-sm text-ink">{ruleText(t, cycle)}</p>
      </header>

      <Block title={t('calendar.cycle.dates')} question={t('calendar.cycle.datesQuestion')}>
        {cycle.dates.length === 0 ? (
          <p className="numeric text-sm text-ink-muted">
            {cycle.next_date
              ? t('calendar.cycle.later', { date: formatDate(cycle.next_date) })
              : t('calendar.cycle.never')}
          </p>
        ) : (
          <ul className="numeric flex flex-wrap gap-2">
            {cycle.dates.map((date) => (
              <li
                key={date}
                className="rounded-[var(--radius-pill)] bg-sunken px-2.5 py-1 text-sm text-ink"
              >
                {formatDate(date)}
              </li>
            ))}
          </ul>
        )}
      </Block>

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-muted">{t('calendar.cycle.owner')}</dt>
        <dd className="text-ink">{cycle.owner?.title ?? t('calendar.cycle.noOwner')}</dd>
        <dt className="text-ink-muted">{t('calendar.cycle.responsible')}</dt>
        <dd className="text-ink">{cycle.responsible?.name ?? t('calendar.cycle.nobody')}</dd>
      </dl>

      {canEdit ? (
        asking ? (
          <div className="flex flex-col gap-2 rounded-[var(--radius)] bg-wait-soft p-3">
            <p className="text-sm text-wait-ink">{t('calendar.cycle.cancelConfirm')}</p>
            <span className="flex flex-wrap gap-2">
              <Button
                look="primary"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate({ id: cycle.id, version }, { onSuccess: onCancelled })}
              >
                {t('calendar.cycle.cancelYes')}
              </Button>
              <Button onClick={() => setAsking(false)}>{t('calendar.cycle.cancelNo')}</Button>
            </span>
          </div>
        ) : (
          <Button
            className="self-start"
            onClick={() => {
              setVersion(cycle.version);
              setAsking(true);
            }}
          >
            {t('calendar.cycle.cancel')}
          </Button>
        )
      ) : null}

      {cancel.isError ? (
        <Failure detail={describeError(cancel.error)} onRetry={() => cancel.reset()} />
      ) : null}
    </div>
  );
}

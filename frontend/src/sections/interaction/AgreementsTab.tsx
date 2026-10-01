/**
 * Вкладка «Соглашения»: следующий шаг, его срок и «спящие» (ТЗ 3.4, 5).
 *
 * «Спит» — нет движения дольше 90 дней (ТЗ 5); движение — правка следующего шага или его
 * даты (V40). Действие вопроса «какие соглашения спят?» открывает вкладку с отбором
 * «только спящие»; помощник назначает следующий шаг прямо в строке.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { STEP_SIGNAL } from '@/sections/pult/model';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Empty } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import type { Agreement, InteractionView } from './model';
import { agreementStatus, orgName } from './text';
import { useNextStep } from './useInteraction';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

export function AgreementsTab({
  view,
  device,
  viewer,
  sleepingOnly,
  onSleepingOnly,
  onOrganization,
}: {
  view: InteractionView;
  device: Device;
  viewer: Role;
  sleepingOnly: boolean;
  onSleepingOnly: (value: boolean) => void;
  onOrganization: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<string | null>(null);
  const rows = view.agreements.filter((each) => !sleepingOnly || each.sleeping);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-pressed={sleepingOnly}
          onClick={() => onSleepingOnly(!sleepingOnly)}
          className={cn(
            'min-h-touch rounded-[var(--radius-pill)] border px-3 text-xs font-medium md:min-h-9',
            sleepingOnly
              ? 'border-accent bg-accent-soft text-accent-ink'
              : 'border-line bg-card text-ink',
          )}
        >
          {t('interaction.agreements.onlySleeping', { days: view.thresholds.sleeping_days })}
        </button>
        <span className="numeric text-xs text-ink-muted">
          {t('interaction.agreements.count', { count: rows.length })}
        </span>
      </div>
      {rows.length === 0 ? (
        <Empty label={t('interaction.agreements.empty')} />
      ) : (
        <ul
          className={cn(
            'grid gap-2',
            device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-3',
            device === 'monitor' && 'grid-cols-3 gap-4',
          )}
        >
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex min-w-0 flex-col gap-2 rounded-[var(--radius-lg)] border border-line bg-card p-4"
            >
              <span className="flex flex-wrap items-center gap-2">
                <AgreementBadge row={row} />
                <span className="numeric text-xs font-medium text-ink">
                  {agreementStatus(t, row)}
                </span>
              </span>
              <span className="font-semibold text-ink-strong">{row.title}</span>
              <span className="flex flex-wrap items-center gap-x-2 text-xs text-ink-muted">
                <button
                  type="button"
                  className="min-h-touch text-accent-ink underline-offset-2 hover:underline md:min-h-0"
                  onClick={() => onOrganization(row.organization.id)}
                >
                  {orgName(row.organization)}
                </button>
                <span>· {t(`interaction.agreementKinds.${row.kind}`)}</span>
                {row.valid_until ? (
                  <span className="numeric">
                    · {t('interaction.agreements.valid', { date: formatDate(row.valid_until) })}
                  </span>
                ) : null}
              </span>
              <p className="text-sm text-ink">
                <span className="text-ink-muted">{t('interaction.agreements.next')}: </span>
                {row.next_step ?? t('interaction.agreements.noNext')}
                {row.responsible ? (
                  <span className="text-ink-muted"> · {row.responsible.name}</span>
                ) : null}
              </p>
              {viewer === 'assistant' ? (
                editing === row.id ? (
                  <NextStepForm row={row} onDone={() => setEditing(null)} />
                ) : (
                  <div>
                    <Button size="small" onClick={() => setEditing(row.id)}>
                      {t('interaction.agreements.edit')}
                    </Button>
                  </div>
                )
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AgreementBadge({ row }: { row: Agreement }) {
  const { t } = useTranslation();
  if (row.sleeping) return <Signal state="wait">{t('interaction.agreements.sleeping')}</Signal>;
  if (row.step) {
    return <Signal state={STEP_SIGNAL[row.step]}>{t(`pult.steps.${row.step}`)}</Signal>;
  }
  return <Signal state="calm">{t('interaction.agreements.moving')}</Signal>;
}

function NextStepForm({ row, onDone }: { row: Agreement; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useNextStep();
  const [text, setText] = useState(row.next_step ?? '');
  const [on, setOn] = useState(row.next_step_on ?? '');
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(
          { id: row.id, next_step: text, next_step_on: on || null },
          { onSuccess: onDone },
        );
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        {t('interaction.agreements.next')}
        <input className={FIELD} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        {t('interaction.agreements.nextDate')}
        <input
          type="date"
          className={FIELD}
          value={on}
          onChange={(event) => setOn(event.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" look="primary" size="small" disabled={save.isPending}>
          {t('interaction.agreements.save')}
        </Button>
        <Button type="button" look="quiet" size="small" onClick={onDone}>
          {t('interaction.agreements.cancel')}
        </Button>
      </div>
    </form>
  );
}

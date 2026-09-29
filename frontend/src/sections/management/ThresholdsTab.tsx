/**
 * Пороги сигналов — «при скольких днях загорается сигнал?» (ТЗ 4, 3.9).
 *
 * Порог меняется в своих границах: «горит за 900 дней» выключило бы сигнал, ни о чём не
 * сказав. До записи видно, сколько строк порог сделает сигналом, — тот же расчёт, что у
 * Пульта, и без записи в базу (инвариант 2, как «что если»). К значению по умолчанию
 * возвращаются одним касанием; «по ТЗ» написано только там, где значение названо в ТЗ, у
 * остальных — «допущение». Руководитель видит пороги без правки: их ведёт помощник.
 *
 * Черновик живёт, пока его не записали или не отменили: если порог успели изменить с
 * другого устройства, запись отказывает, а набранное остаётся рядом с новым значением
 * (инвариант 15, ADR-0034).
 */

import { Minus, Plus } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Failure } from '@/shared/ui/States';

import type { Threshold } from './model';
import { useImpact, useSaveThreshold } from './useManagement';

function ThresholdRow({
  item,
  canEdit,
  onSaved,
}: {
  item: Threshold;
  canEdit: boolean;
  onSaved: (title: string) => void;
}) {
  const { t } = useTranslation();
  // `null` — не правили: показывается значение с сервера, каким бы оно ни стало.
  const [draft, setDraft] = useState<number | string | null>(null);
  const save = useSaveThreshold();
  const key = `management.thresholds.items.${item.key}` as const;
  const title = t(`${key}.title`);
  const isTime = item.kind === 'time';
  const value = draft ?? item.value;
  const numeric = typeof value === 'number' ? value : Number(value);
  const min = item.min ?? 0;
  const max = item.max ?? Infinity;
  const inBounds = isTime || (Number.isInteger(numeric) && numeric >= min && numeric <= max);
  const changed = draft !== null && draft !== item.value;
  const impact = useImpact(item.key, value, changed && inBounds && !isTime);

  const shown = (each: number | string) =>
    item.kind === 'days' ? t('management.thresholds.days', { count: Number(each) }) : String(each);

  const step = (delta: number) => {
    // Поле очистили — шаг идёт от сохранённого значения, а не в никуда.
    const base = Number.isFinite(numeric) ? numeric : Number(item.value);
    setDraft(Math.min(max, Math.max(min, base + delta)));
  };

  const cancel = () => {
    setDraft(null);
    save.reset();
  };

  return (
    <li className="flex flex-col gap-2 rounded-[var(--radius)] border border-line bg-card p-3">
      <div className="flex flex-col gap-0.5">
        <span className="text-[15px] font-medium text-ink-strong">{title}</span>
        <span className="text-sm text-ink-muted">{t(`${key}.question`)}</span>
      </div>

      {canEdit ? (
        <div className="flex flex-wrap items-center gap-2">
          {isTime ? (
            <input
              type="time"
              aria-label={t('management.thresholds.value', { title })}
              value={String(value)}
              onChange={(event) => setDraft(event.target.value)}
              className="numeric min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-3 text-base text-ink"
            />
          ) : (
            <>
              <Button
                size="icon"
                aria-label={t('management.thresholds.less', { title })}
                disabled={Number.isFinite(numeric) && numeric <= min}
                onClick={() => step(-1)}
              >
                <Minus className="size-4" aria-hidden="true" />
              </Button>
              <input
                type="number"
                inputMode="numeric"
                aria-label={t('management.thresholds.value', { title })}
                min={item.min ?? undefined}
                max={item.max ?? undefined}
                value={Number.isNaN(numeric) ? '' : numeric}
                onChange={(event) => setDraft(event.target.valueAsNumber)}
                className={cn(
                  'numeric min-h-touch w-20 rounded-[var(--radius)] border bg-card px-2 text-center text-base text-ink',
                  inBounds ? 'border-line-strong' : 'border-burn',
                )}
              />
              <Button
                size="icon"
                aria-label={t('management.thresholds.more', { title })}
                disabled={Number.isFinite(numeric) && numeric >= max}
                onClick={() => step(1)}
              >
                <Plus className="size-4" aria-hidden="true" />
              </Button>
            </>
          )}
          {item.min !== null && item.max !== null ? (
            <span
              className={cn('text-xs', inBounds ? 'text-ink-muted' : 'font-medium text-burn-ink')}
            >
              {t('management.thresholds.bounds', { min: item.min, max: item.max })}
            </span>
          ) : null}
        </div>
      ) : (
        <span className="numeric text-lg font-semibold text-ink-strong">{shown(item.value)}</span>
      )}

      <p className="numeric text-sm text-ink">
        {t(`${key}.now`, { count: item.affected ?? 0 })}
        {changed && impact.data !== undefined && impact.data !== null ? (
          <span className="ml-1.5 font-semibold text-accent-ink">
            {t('management.thresholds.then', { count: impact.data })}
          </span>
        ) : null}
      </p>

      <span className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
        <span>
          {item.origin === 'tz'
            ? t('management.thresholds.byTz', { value: shown(item.default) })
            : t('management.thresholds.byDefault', { value: shown(item.default) })}
        </span>
        {canEdit && value !== item.default ? (
          <Button look="quiet" size="small" onClick={() => setDraft(item.default)}>
            {t('management.thresholds.reset', { value: shown(item.default) })}
          </Button>
        ) : null}
      </span>

      {canEdit && changed ? (
        <span className="flex flex-wrap gap-2">
          <Button
            look="primary"
            size="small"
            disabled={!inBounds || save.isPending}
            onClick={() =>
              save.mutate(
                { key: item.key, value, version: item.version },
                {
                  onSuccess: () => {
                    setDraft(null);
                    onSaved(title);
                  },
                },
              )
            }
          >
            {t('management.thresholds.save')}
          </Button>
          <Button size="small" onClick={cancel}>
            {t('management.thresholds.cancel')}
          </Button>
        </span>
      ) : null}

      {save.isError ? <Failure detail={describeError(save.error)} /> : null}
    </li>
  );
}

export function ThresholdsTab({
  thresholds,
  canEdit,
  wide,
}: {
  thresholds: Threshold[];
  canEdit: boolean;
  wide: boolean;
}) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState<string | null>(null);

  return (
    <Card title={t('management.thresholds.title')} question={t('management.thresholds.question')}>
      <p className="text-xs text-ink-muted">{t('management.thresholds.note')}</p>
      {saved ? (
        <p
          role="status"
          className="mt-3 rounded-[var(--radius)] bg-calm-soft px-3 py-2 text-sm text-calm-ink"
        >
          {t('management.thresholds.saved', { title: saved })}
        </p>
      ) : null}
      <ul className={cn('mt-3 grid gap-3', wide ? 'grid-cols-2 2xl:grid-cols-3' : 'grid-cols-1')}>
        {thresholds.map((item) => (
          <ThresholdRow key={item.key} item={item} canEdit={canEdit} onSaved={setSaved} />
        ))}
      </ul>
    </Card>
  );
}

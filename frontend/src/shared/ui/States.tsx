/**
 * Три состояния любого экрана: загрузка, отказ, пусто.
 *
 * Вынесены в один файл нарочно. Пока их рисует каждый экран по-своему, два из трёх
 * выглядят как поломка: «пусто» неотличимо от «не загрузилось», а отказ показывает
 * технический текст вместо того, что делать дальше.
 */

import { AlertTriangle, Inbox, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-ink-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      {label ?? t('common.loading')}
    </div>
  );
}

interface FailureProps {
  detail: string;
  /** Что именно не получилось: по умолчанию — запрос. */
  kind?: 'request' | 'render';
  onRetry?: (() => void) | undefined;
}

export function Failure({ detail, kind = 'request', onRetry }: FailureProps) {
  const { t } = useTranslation();
  return (
    <div className="rounded-[var(--radius)] border border-line bg-burn-soft p-4" role="alert">
      <p className="flex items-center gap-2 font-medium text-burn-ink">
        <AlertTriangle className="size-4" aria-hidden="true" />
        {t('common.error')}
      </p>
      <p className="mt-1 text-sm text-burn-ink">
        {t(kind === 'render' ? 'common.brokenBody' : 'common.errorBody', { detail })}
      </p>
      {onRetry ? (
        <Button className="mt-3" size="small" onClick={onRetry}>
          {t('common.retry')}
        </Button>
      ) : null}
    </div>
  );
}

export function Empty({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <p className="flex items-center gap-2 py-4 text-sm text-ink-muted">
      <Inbox className="size-4" aria-hidden="true" />
      {label ?? t('common.empty')}
    </p>
  );
}

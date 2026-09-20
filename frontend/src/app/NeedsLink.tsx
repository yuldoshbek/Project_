/**
 * Экран «откройте по своей ссылке».
 *
 * Это не экран входа: вводить здесь нечего (ADR-0029). Сессия закончилась или её не было, и
 * единственное действие — открыть личную ссылку. Поэтому на экране одно предложение, одна
 * кнопка проверки и ни одного поля.
 */

import { Link2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';

export function NeedsLink({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();

  return (
    <div className="grid min-h-dvh place-items-center bg-app px-6">
      <div className="w-full max-w-md rounded-[var(--radius-lg)] border border-line bg-card p-6 shadow-card">
        <span className="grid size-11 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <Link2 className="size-5" />
        </span>
        <h1 className="mt-4 text-lg font-semibold text-ink-strong">{t('access.needed')}</h1>
        <p className="mt-2 text-sm text-ink-muted">{t('access.neededBody')}</p>
        <Button className="mt-5 w-full" look="primary" onClick={onRetry}>
          <RefreshCw className="size-4" />
          {t('access.retry')}
        </Button>
      </div>
    </div>
  );
}

/**
 * Экран «откройте по своей ссылке».
 *
 * Это не экран входа: вводить здесь нечего (ADR-0029). Сессия закончилась или её не было, и
 * единственное действие — открыть личную ссылку. Поэтому на экране одно предложение, одна
 * кнопка проверки и ни одного поля.
 *
 * Один случай со своей ссылкой: помощник только что перевыпустил её в «Управлении», и
 * перевыпуск погасил и эту сессию. Тогда новая ссылка — здесь: больше её показать негде, а
 * без неё помощник остался бы вне системы.
 */

import { Copy, Link2, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AccessLink } from '@/shared/api/orbita';
import { Button } from '@/shared/ui/Button';

function FreshLink({ link }: { link: AccessLink }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  return (
    <div className="mt-4 rounded-[var(--radius)] border border-line-accent bg-accent-soft p-3">
      <p className="mb-2 text-xs text-accent-ink">{t('management.links.warning')}</p>
      <code className="block truncate rounded-[var(--radius-sm)] bg-card px-2 py-1.5 text-xs">
        {link.url}
      </code>
      <span className="mt-3 flex flex-wrap gap-2">
        <Button asChild look="primary" size="small">
          <a href={link.url}>
            <Link2 className="size-4" aria-hidden="true" />
            {t('access.openFresh')}
          </a>
        </Button>
        <Button
          size="small"
          onClick={() => {
            void navigator.clipboard.writeText(link.url).then(() => setCopied(true));
          }}
        >
          <Copy className="size-4" aria-hidden="true" />
          {copied ? t('management.links.copied') : t('management.links.copy')}
        </Button>
      </span>
    </div>
  );
}

export function NeedsLink({
  fresh,
  onRetry,
}: {
  fresh?: AccessLink | undefined;
  onRetry: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="grid min-h-dvh place-items-center bg-app px-6">
      {/* min-w-0: иначе длинная ссылка в одну строку растягивает колонку сетки шире экрана. */}
      <div className="w-full max-w-md min-w-0 rounded-[var(--radius-lg)] border border-line bg-card p-6 shadow-card">
        <span className="grid size-11 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <Link2 className="size-5" />
        </span>
        <h1 className="mt-4 text-lg font-semibold text-ink-strong">
          {fresh ? t('access.reissued') : t('access.needed')}
        </h1>
        <p className="mt-2 text-sm text-ink-muted">
          {fresh ? t('access.reissuedBody') : t('access.neededBody')}
        </p>
        {fresh ? <FreshLink link={fresh} /> : null}
        <Button className="mt-5 w-full" look={fresh ? 'plain' : 'primary'} onClick={onRetry}>
          <RefreshCw className="size-4" />
          {t('access.retry')}
        </Button>
      </div>
    </div>
  );
}

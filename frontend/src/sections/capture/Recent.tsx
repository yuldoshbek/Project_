/**
 * Недавние записи — что записано и куда ушло. Ответ на вопрос, который задают сразу после
 * записи: «а оно сохранилось?», — и заодно видно, что лежит во входящих в ожидании раздела.
 * Записи обоих: пользователи видят всё, роль подписывает запись (инвариант 13).
 */

import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { Card } from '@/shared/ui/Card';
import { Failure, Loading } from '@/shared/ui/States';

import { KIND_ICON } from './kinds';
import { metaText } from './text';
import { useCaptures } from './useCapture';

export function Recent() {
  const { t } = useTranslation();
  const captures = useCaptures();

  if (captures.isPending) return <Loading />;
  if (captures.isError) {
    return (
      <Failure detail={describeError(captures.error)} onRetry={() => void captures.refetch()} />
    );
  }

  // Сколько записей — решает сервер (`services/captures.RECENT_LIMIT`).
  const { recent, as_of: asOf } = captures.data;
  return (
    <Card title={t('capture.recent.title')} question={t('capture.recent.question')}>
      {recent.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('capture.recent.empty')}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {recent.map((capture) => {
            const Icon = KIND_ICON[capture.kind];
            return (
              <li key={capture.id} className="flex min-w-0 items-start gap-2.5">
                <Icon className="mt-0.5 size-4 shrink-0 text-accent-ink" aria-hidden="true" />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-xs text-ink-muted">
                    {t(`capture.kinds.${capture.kind}`)}
                  </span>
                  <span className="text-sm text-ink-strong">{capture.text}</span>
                  <span className="numeric text-xs text-ink-muted">
                    {metaText(t, capture, asOf)}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

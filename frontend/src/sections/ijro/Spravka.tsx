/**
 * Справка по проблемным поручениям — «что докладывать наверх?» (ТЗ 5, 10).
 *
 * Открывается вместо вкладки и печатается браузером, как отчёт недели: оболочка на печати
 * скрыта. Оформленный PDF — блок 3 (PLAN); здесь — состав справки и её печать.
 */

import { ArrowLeft, Printer } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';

import type { IjroView } from './model';
import { dueLabel } from './text';
import { useSpravka } from './useIjro';

interface SpravkaProps {
  view: IjroView;
  freshness: string;
  onBack: () => void;
}

export function Spravka({ view, freshness, onBack }: SpravkaProps) {
  const { t } = useTranslation();
  const spravka = useSpravka();

  return (
    <article className="rounded-[var(--radius-lg)] border border-line bg-card p-4 sm:p-6 print:border-0 print:p-0">
      <div className="mb-4 flex flex-wrap items-center gap-2 print:hidden">
        <Button look="quiet" onClick={onBack}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t('ijro.spravka.back')}
        </Button>
        <Button className="ml-auto" look="primary" onClick={() => window.print()}>
          <Printer className="size-4" aria-hidden="true" />
          {t('ijro.spravka.print')}
        </Button>
      </div>
      <h2 className="text-lg font-semibold text-ink-strong">{t('ijro.spravka.title')}</h2>
      <p className="mt-1 text-xs text-ink-muted">
        {t('ijro.spravka.asOf', { date: formatDate(view.as_of) })}
        {' · '}
        {freshness}
      </p>

      {spravka.isPending ? (
        <Loading />
      ) : spravka.isError ? (
        <Failure detail={describeError(spravka.error)} />
      ) : spravka.data.length === 0 ? (
        <p className="mt-4 text-sm text-ink">{t('ijro.questions.report_up.empty')}</p>
      ) : (
        <ol className="mt-4 flex flex-col gap-4">
          {spravka.data.map((line, index) => (
            <li key={line.id} className="break-inside-avoid border-t border-line pt-3 text-sm">
              <p className="numeric text-xs text-ink-muted">
                {index + 1}
                {'. '}
                {[line.place, dueLabel(t, line), line.responsible].join(' · ')}
              </p>
              <p className="mt-1 text-ink-strong">{line.content}</p>
              <p className="mt-2 text-ink">
                <span className="text-xs font-medium text-ink-muted">
                  {t('ijro.card.problem.problem')}
                </span>
                <span className="block">{line.problem}</span>
              </p>
              {line.proposal ? (
                <p className="mt-2 text-ink">
                  <span className="text-xs font-medium text-ink-muted">
                    {t('ijro.card.problem.proposal')}
                  </span>
                  <span className="block">{line.proposal}</span>
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}

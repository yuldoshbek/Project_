/**
 * Отчёт недели и месяца — вкладка Пульта (ТЗ 2), печать в PDF (критерий 6 блока 1).
 *
 * Документ шириной листа A4, а не экран: его печатают и кладут в папку к совещанию.
 * Печать — средствами браузера («Сохранить как PDF»): отдельный отрисовщик на сервере
 * (порт `ReportRenderer`) понадобится для справки по Ижро в блоке 2, а для этого листа
 * он был бы вторым источником той же вёрстки.
 *
 * Итоги — за период по журналу изменений. Лестница и «кто держит» — на момент
 * формирования: снимков прошлых состояний нет, и отчёт пишет это прямо, а не выдаёт
 * сегодняшнее за конец прошлой недели.
 */

import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Printer } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import {
  LADDER,
  STEP_SIGNAL,
  type ReportPeriod,
  type ReportTotals,
  type ReportView,
} from './model';
import { deviationText, rowTitle } from './text';
import { reportQuery } from './usePult';

/** Порядок итогов: сначала сделанное, затем решения, затем то, что сдвинулось. */
const TOTALS: readonly (keyof ReportTotals)[] = [
  'closed_tasks',
  'closed_projects',
  'passed_milestones',
  'created_projects',
  'created_tasks',
  'decisions_made',
  'decisions_done',
  'moves',
  'shift_days',
];

export function ReportTab() {
  const { t } = useTranslation();
  const [period, setPeriod] = useState<ReportPeriod>('week');
  const [offset, setOffset] = useState(0);
  const report = useQuery(reportQuery(period, offset));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <div role="group" aria-label={t('pult.report.periodLabel')} className="flex gap-1">
          {(['week', 'month'] as const).map((each) => (
            <Button
              key={each}
              look={period === each ? 'primary' : 'plain'}
              aria-pressed={period === each}
              onClick={() => {
                setPeriod(each);
                setOffset(0);
              }}
            >
              {t(`pult.report.${each}`)}
            </Button>
          ))}
        </div>
        <Button
          look="plain"
          size="icon"
          aria-label={t('pult.report.previous')}
          onClick={() => setOffset(offset + 1)}
        >
          <ChevronLeft className="size-5" aria-hidden="true" />
        </Button>
        <Button
          look="plain"
          size="icon"
          aria-label={t('pult.report.next')}
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(offset - 1, 0))}
        >
          <ChevronRight className="size-5" aria-hidden="true" />
        </Button>
        <Button className="ml-auto" look="primary" onClick={() => window.print()}>
          <Printer className="size-4" aria-hidden="true" />
          {t('pult.report.print')}
        </Button>
      </div>

      {report.isPending ? <Loading /> : null}
      {report.isError ? (
        <Failure detail={describeError(report.error)} onRetry={() => void report.refetch()} />
      ) : null}
      {report.data ? <ReportDocument report={report.data} /> : null}
    </div>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    // Раздел не рвётся между страницами: половина списка на одном листе и половина на
    // другом читается как два разных списка.
    <section className="break-inside-avoid border-t border-line pt-4">
      <h3 className="text-base font-semibold text-ink-strong">{title}</h3>
      {note ? <p className="mt-0.5 text-xs text-ink-muted">{note}</p> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ReportDocument({ report }: { report: ReportView }) {
  const { t } = useTranslation();
  const range = { from: formatDate(report.start), to: formatDate(report.end) };

  return (
    <article
      className={cn(
        'mx-auto flex w-full max-w-[794px] flex-col gap-5 rounded-[var(--radius-lg)] border border-line bg-card p-6 shadow-card',
        'print:max-w-none print:rounded-none print:border-0 print:p-0 print:shadow-none',
      )}
    >
      <header className="flex flex-col gap-1">
        <p className="text-xs font-semibold tracking-wide text-accent-ink">{t('app.name')}</p>
        <h2 className="text-xl font-semibold text-ink-strong">
          {t(report.period === 'week' ? 'pult.report.titleWeek' : 'pult.report.titleMonth', range)}
        </h2>
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span>{t('pult.report.generated', { when: formatDateTime(report.generated_at) })}</span>
          {report.is_demo ? <Signal state="wait">{t('pult.demo')}</Signal> : null}
        </div>
        <p className="text-xs text-ink-muted">{t('pult.report.stateNote')}</p>
      </header>

      <Section title={t('pult.report.totals.title')} note={t('pult.report.totals.question')}>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
          {TOTALS.map((key) => (
            <div key={key} className="flex flex-col">
              <dt className="order-2 text-xs text-ink-muted">{t(`pult.report.totals.${key}`)}</dt>
              <dd className="numeric order-1 text-2xl font-semibold text-ink-strong">
                {report.totals[key]}
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title={t('pult.report.attention.title')} note={t('pult.report.attention.question')}>
        <p className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-sm text-ink">
          {LADDER.map((step) => (
            <span key={step} className="numeric">
              {t('pult.report.attention.count', {
                step: t(`pult.steps.${step}`),
                count: report.counts[step],
              })}
            </span>
          ))}
          <span className="numeric text-calm-ink">
            {t('pult.report.attention.onTrack', { count: report.on_track })}
          </span>
        </p>
        <ol className="flex flex-col divide-y divide-line">
          {report.rows.map((row) => (
            <li key={`${row.section}:${row.entity_id}`} className="flex items-start gap-3 py-2">
              <Signal state={STEP_SIGNAL[row.step]} className="shrink-0">
                {t(`pult.steps.${row.step}`)}
              </Signal>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-ink-strong">
                  {rowTitle(t, row)}
                </span>
                <span className="block text-xs text-ink-muted">
                  {[row.responsible?.name ?? t('pult.noHolder'), row.context]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              <span className="numeric shrink-0 text-xs font-medium text-ink">
                {deviationText(t, row)}
              </span>
            </li>
          ))}
        </ol>
        {report.more_rows > 0 ? (
          <p className="mt-2 text-xs text-ink-muted">
            {t('pult.report.attention.more', { count: report.more_rows })}
          </p>
        ) : null}
      </Section>

      <Section title={t('pult.holders.title')} note={t('pult.holders.question')}>
        <ul className="flex flex-col gap-1.5">
          {report.holders.map((holder) => (
            <li key={holder.person.id} className="flex items-baseline gap-3 text-sm">
              <span className="w-40 shrink-0 font-medium text-ink-strong">
                {holder.person.name}
              </span>
              <span className="text-xs text-ink-muted">
                {LADDER.filter((step) => holder.counts[step] > 0)
                  .map((step) => `${t(`pult.steps.${step}`).toLowerCase()} ${holder.counts[step]}`)
                  .join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={t('pult.report.decisions.title')}>
        {report.decisions.length === 0 ? (
          <p className="text-sm text-ink-muted">{t('pult.report.decisions.none')}</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {report.decisions.map((decision, index) => (
              <li
                key={`${decision.decided_on}-${index}`}
                className="flex items-baseline gap-3 text-sm"
              >
                <span className="numeric w-20 shrink-0 text-xs text-ink-muted">
                  {formatDate(decision.decided_on)}
                </span>
                <span className="min-w-0 flex-1 text-ink">
                  {[t(`pult.decisions.${decision.kind}`), decision.title]
                    .filter(Boolean)
                    .join(': ')}
                </span>
                <span className="shrink-0 text-xs text-ink-muted">
                  {decision.state === 'done' && decision.done_on
                    ? t('pult.report.decisions.done', { date: formatDate(decision.done_on) })
                    : t('pult.report.decisions.open')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={t('pult.report.moves.title')}>
        {report.deadline_moves.items.length === 0 ? (
          <p className="text-sm text-ink-muted">{t('pult.report.moves.none')}</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {report.deadline_moves.items.map((item) => (
              <li
                key={`${item.section}:${item.entity_id}`}
                className="flex items-baseline gap-3 text-sm"
              >
                <span className="min-w-0 flex-1 text-ink">{rowTitle(t, item)}</span>
                <span className="numeric shrink-0 text-xs text-wait-ink">
                  {[
                    t('pult.dueMoved', {
                      from: formatDate(item.original_due_on),
                      to: item.due_on ? formatDate(item.due_on) : '—',
                    }),
                    item.moves > 1 ? t('pult.moves.times', { count: item.moves }) : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </article>
  );
}

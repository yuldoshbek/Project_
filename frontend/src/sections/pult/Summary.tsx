/**
 * «Сводка» — вкладка Пульта: предпросмотр утренней сводки (PLAN, состав Пульта; ТЗ 8).
 *
 * Сводка — уведомление руководителю в 08:30 (CONTEXT): что ждёт его решения и что горит
 * сегодня. Вкладка отвечает на три вопроса: что придёт — так, как это выглядит на экране
 * блокировки; что за этими числами — те же строки лестницы, с решением в одно касание (сюда
 * ведёт касание уведомления, `/?view=summary`); дойдёт ли — устройство и доставка.
 *
 * На iPhone уведомления работают только после установки на экран «Домой»: вкладка показывает,
 * как это сделать (ТЗ 8), и только потом предлагает их включить.
 *
 * Пока нет API, доставка и устройство руководителя вымышлены — и вкладка говорит это сама:
 * общий значок шапки говорит о людях и проектах, а не об уведомлениях.
 */

import { BellRing, Share, SquarePlus } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { describeError } from '@/shared/api/client';
import { formatDate, formatTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { LadderRow, type RowActions, type Viewer } from './LadderRow';
import { rowKey, type PultRow, type PultView, type SummaryView } from './model';
import { deviationText, summaryLines } from './text';
import { useSummary, useThisDevice } from './usePult';

interface SummaryTabProps {
  pult: PultView;
  viewer: Viewer;
  actions: RowActions;
  busy: boolean;
  device: Device;
}

export function SummaryTab({ pult, viewer, actions, busy, device }: SummaryTabProps) {
  const summary = useSummary(pult);
  const view = summary.data;

  // «Загрузка» — только пока сводки нет вовсе: на месте открытой строки она свернула бы её и
  // стёрла черновик вопроса.
  if (!view) {
    return summary.isError ? (
      <Failure detail={describeError(summary.error)} onRetry={() => void summary.refetch()} />
    ) : (
      <Loading />
    );
  }

  const compact = device === 'phone';
  const rows = (kind: 'awaiting' | 'due', list: PultRow[]) => (
    <RowsCard
      kind={kind}
      rows={list}
      viewer={viewer}
      actions={actions}
      busy={busy}
      compact={compact}
    />
  );
  const notice = <NotificationCard summary={view} viewer={viewer} />;
  const recipient =
    viewer === 'leader' ? <ThisDeviceCard summary={view} /> : <LeaderCard summary={view} />;

  if (device === 'phone') {
    return (
      <div className="flex flex-col gap-3">
        {notice}
        {rows('awaiting', view.awaiting)}
        {rows('due', view.due_today)}
        {recipient}
      </div>
    );
  }

  const side = (
    <div className="flex flex-col gap-5">
      {notice}
      {recipient}
    </div>
  );

  if (device === 'monitor') {
    return (
      <div className="grid grid-cols-[minmax(0,4fr)_minmax(0,5fr)_minmax(0,5fr)] items-start gap-6">
        {side}
        {rows('awaiting', view.awaiting)}
        {rows('due', view.due_today)}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-start gap-5">
      {side}
      <div className="flex flex-col gap-5">
        {rows('awaiting', view.awaiting)}
        {rows('due', view.due_today)}
      </div>
    </div>
  );
}

/**
 * Что придёт: вид на экране блокировки. Помощнику — и доставка: дойдёт ли до руководителя.
 * Руководителю на это отвечает карточка его устройства, а «пришла на iPhone» над «включите
 * уведомления на этом iPhone» противоречило бы само себе.
 */
function NotificationCard({ summary, viewer }: { summary: SummaryView; viewer: Viewer }) {
  const { t } = useTranslation();

  return (
    <Card
      title={t('pult.summary.title')}
      question={t('pult.summary.question')}
      freshness={t('pult.summary.asOf', { time: formatTime(summary.as_of) })}
    >
      <figure className="flex flex-col gap-1 rounded-[var(--radius-lg)] border border-line bg-sunken p-3">
        <figcaption className="flex items-center gap-2 text-xs text-ink-muted">
          <img src="/icon-192.png" alt="" className="size-5 rounded-[var(--radius-sm)]" />
          <span className="font-medium tracking-wide">{t('pult.summary.app')}</span>
          <span className="numeric ml-auto">{summary.send_at}</span>
        </figcaption>
        <p className="text-sm font-semibold text-ink-strong">{t('pult.summary.push.title')}</p>
        {summaryLines(t, summary).map((line) => (
          <p key={line} className="text-sm leading-snug text-ink">
            {line}
          </p>
        ))}
      </figure>
      <p className="mt-1 text-xs text-ink-muted">{t('pult.summary.lockScreen')}</p>

      {viewer === 'assistant' ? (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink">
            <Delivery summary={summary} />
          </div>
          <p className="mt-2 text-xs text-ink-muted">{t('pult.summary.timeHint')}</p>
        </>
      ) : null}
      {summary.is_demo ? (
        <p className="mt-3 text-xs text-ink-muted">{t('pult.summary.demo')}</p>
      ) : null}
    </Card>
  );
}

/** Дойдёт ли: ушла ли сегодняшняя, а если нет — придёт ли вообще. */
function Delivery({ summary }: { summary: SummaryView }) {
  const { t } = useTranslation();
  if (!summary.leader_device) {
    return <Signal state="burn">{t('pult.summary.delivery.noDevice')}</Signal>;
  }
  if (summary.sent_at) {
    return (
      <>
        <Signal state="calm">{t('pult.summary.delivery.sent')}</Signal>
        <span className="numeric">
          {t('pult.summary.delivery.sentAt', {
            time: formatTime(summary.sent_at),
            device: summary.leader_device.name,
          })}
        </span>
      </>
    );
  }
  return (
    <>
      <Signal state="plain">{t('pult.summary.delivery.pending')}</Signal>
      <span className="numeric">
        {t('pult.summary.delivery.pendingAt', { time: summary.send_at })}
      </span>
    </>
  );
}

/**
 * Один пункт сводки — ответ числом и строки лестницы под ним. Пустой пункт — фразой, а не
 * нулём (ТЗ 5).
 */
function RowsCard({
  kind,
  rows,
  viewer,
  actions,
  busy,
  compact,
}: {
  kind: 'awaiting' | 'due';
  rows: PultRow[];
  viewer: Viewer;
  actions: RowActions;
  busy: boolean;
  compact: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<string | null>(null);
  const [first] = rows;

  return (
    <Card title={t(`pult.summary.${kind}.title`)} question={t(`pult.summary.${kind}.question`)}>
      {first ? (
        <>
          <p className="mb-3 flex flex-wrap items-baseline gap-x-2">
            <span className="numeric text-2xl leading-tight font-semibold text-ink-strong">
              {rows.length}
            </span>
            {kind === 'awaiting' ? (
              <span className="text-sm text-call-ink">
                {t('pult.summary.awaiting.oldest', { when: deviationText(t, first) })}
              </span>
            ) : null}
          </p>
          <ul className="flex flex-col gap-2">
            {rows.map((row) => {
              const key = rowKey(row);
              return (
                <LadderRow
                  key={key}
                  row={row}
                  viewer={viewer}
                  actions={actions}
                  busy={busy}
                  expanded={open === key}
                  selected={false}
                  onToggle={() => setOpen(open === key ? null : key)}
                  detailsInline
                  compact={compact}
                />
              );
            })}
          </ul>
        </>
      ) : (
        <p className="text-sm text-ink-muted">{t(`pult.summary.${kind}.empty`)}</p>
      )}
    </Card>
  );
}

/** Какие уведомления приходят — одна фраза и на телефоне, и у помощника. */
function Which({ summary }: { summary: SummaryView }) {
  const { t } = useTranslation();
  return (
    <p className="mt-3 text-xs text-ink-muted">
      {t('pult.summary.which', { time: summary.send_at })}
    </p>
  );
}

function Step({ icon, children }: { icon: ReactNode; children: string }) {
  return (
    <li className="flex items-start gap-2 text-sm text-ink">
      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-[var(--radius-sm)] bg-accent-soft text-accent-ink">
        {icon}
      </span>
      <span>{children}</span>
    </li>
  );
}

/** Руководитель: придёт ли сводка на устройство, с которого он смотрит. */
function ThisDeviceCard({ summary }: { summary: SummaryView }) {
  const { t } = useTranslation();
  const { state, enable } = useThisDevice();
  const setup = state.data?.setup;
  const enabledOn = state.data?.enabledOn ?? null;
  const denied = state.data?.apple ? 'deniedApple' : 'deniedBrowser';

  let body: ReactNode = null;
  if (setup === 'install') {
    body = (
      <>
        <p className="text-sm text-ink">{t('pult.summary.device.install')}</p>
        <ol className="mt-3 flex flex-col gap-2">
          <Step icon={<Share className="size-3.5" aria-hidden="true" />}>
            {t('pult.summary.device.stepShare')}
          </Step>
          <Step icon={<SquarePlus className="size-3.5" aria-hidden="true" />}>
            {t('pult.summary.device.stepHome')}
          </Step>
          <Step icon={<BellRing className="size-3.5" aria-hidden="true" />}>
            {t('pult.summary.device.stepOpen')}
          </Step>
        </ol>
      </>
    );
  } else if (setup === 'unsupported') {
    body = <p className="text-sm text-ink">{t('pult.summary.device.unsupported')}</p>;
  } else if (setup === 'denied') {
    body = <p className="text-sm text-ink">{t(`pult.summary.device.${denied}`)}</p>;
  } else if (setup === 'ready' && enabledOn) {
    body = (
      <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
        <Signal state="calm">{t('pult.summary.device.on')}</Signal>
        <span className="numeric">
          {/* В демо касание ничего не подписывает — и время не обещается. */}
          {t(summary.is_demo ? 'pult.summary.device.onDemo' : 'pult.summary.device.onSince', {
            date: formatDate(enabledOn),
            time: summary.send_at,
          })}
        </span>
      </p>
    );
  } else if (setup === 'ready') {
    body = (
      <Button
        look="primary"
        className="w-full sm:w-auto"
        disabled={enable.isPending}
        onClick={() => enable.mutate()}
      >
        <BellRing className="size-4" aria-hidden="true" />
        {t('pult.summary.device.enable')}
      </Button>
    );
  }

  return (
    <Card title={t('pult.summary.device.title')} question={t('pult.summary.device.question')}>
      {state.isPending ? <Loading /> : body}
      {enable.isError ? <Failure detail={describeError(enable.error)} /> : null}
      <Which summary={summary} />
    </Card>
  );
}

/** Помощник: дойдёт ли сводка до руководителя. */
function LeaderCard({ summary }: { summary: SummaryView }) {
  const { t } = useTranslation();
  return (
    <Card title={t('pult.summary.leader.title')} question={t('pult.summary.leader.question')}>
      {summary.leader_device ? (
        <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
          <Signal state="calm">{t('pult.summary.device.on')}</Signal>
          <span className="numeric">
            {t('pult.summary.leader.on', {
              device: summary.leader_device.name,
              date: formatDate(summary.leader_device.since),
            })}
          </span>
        </p>
      ) : (
        <p className="text-sm text-ink">{t('pult.summary.leader.off')}</p>
      )}
      <Which summary={summary} />
    </Card>
  );
}

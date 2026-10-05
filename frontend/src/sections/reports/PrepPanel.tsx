/**
 * Карточка подготовки (ТЗ 3.5): этап, кто задерживает и напоминание, запросы сведений,
 * чек-лист.
 *
 * Напоминание (V43) — готовый текст в буфер обмена: отправляет человек своим каналом,
 * система писем не шлёт. Правит подготовку помощник; руководитель видит то же без кнопок
 * правки (инвариант 13).
 */

import { Copy } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Role } from '@/shared/api/orbita';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import {
  PREP_STAGES,
  type Delay,
  type InfoRequest,
  type NewRequest,
  type PreparationCard,
  type ReportsView,
} from './model';
import { PrepBadge } from './ReportsSection';
import { delayText, missingText, reminderText } from './text';
import {
  useAddItem,
  useAddRequest,
  usePreparation,
  useReceive,
  useStage,
  useToggleItem,
} from './useReports';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

export function PrepPanel({ id, view, viewer }: { id: string; view: ReportsView; viewer: Role }) {
  const card = usePreparation(id);
  if (card.isPending) return <Loading />;
  if (card.isError) return <Failure detail={describeError(card.error)} />;
  return <Panel card={card.data} view={view} canEdit={viewer === 'assistant'} />;
}

function Block({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink-strong">{title}</h3>
        {aside ? <span className="numeric text-xs text-ink-muted">{aside}</span> : null}
      </header>
      {children}
    </section>
  );
}

function Panel({
  card,
  view,
  canEdit,
}: {
  card: PreparationCard;
  view: ReportsView;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const stage = useStage();

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <PrepBadge row={card} />
        <h2 className="text-lg leading-snug font-semibold text-ink-strong">{card.title}</h2>
        <p className="numeric text-sm text-ink-muted">
          {[
            t(`reports.kinds.${card.kind}`),
            card.addressee ? t(`reports.addressees.${card.addressee}`) : null,
            t('reports.card.show', { date: formatDate(card.show_on) }),
            card.start_on ? t('reports.card.start', { date: formatDate(card.start_on) }) : null,
            card.responsible?.name ?? null,
            card.link ? t('reports.card.project', { title: card.link.title }) : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
      </header>

      <Block title={t('reports.card.stage')}>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            {PREP_STAGES.map((each) => (
              <Button
                key={each}
                size="small"
                look={card.stage === each ? 'primary' : 'plain'}
                aria-pressed={card.stage === each}
                disabled={stage.isPending}
                onClick={() => stage.mutate({ id: card.id, stage: each, version: card.version })}
              >
                {t(`reports.stages.${each}`)}
              </Button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink">{t(`reports.stages.${card.stage}`)}</p>
        )}
      </Block>

      {card.delays.length > 0 ? (
        <Block title={t('reports.card.delays')}>
          <ul className="flex flex-col gap-2">
            {card.delays.map((delay) => (
              <DelayLine
                key={`${delay.source.kind}:${delay.source.id}`}
                card={card}
                delay={delay}
              />
            ))}
          </ul>
        </Block>
      ) : null}

      <Requests card={card} view={view} canEdit={canEdit} />
      <Checklist card={card} canEdit={canEdit} />
    </div>
  );
}

function DelayLine({ card, delay }: { card: PreparationCard; delay: Delay }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const requests = card.info_requests.filter((each) => delay.requests.includes(each.id));
  return (
    <li className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm text-burn-ink">{delayText(t, delay)}</span>
      <Button
        size="small"
        onClick={() => {
          void navigator.clipboard
            ?.writeText(reminderText(t, card, requests))
            .then(() => setCopied(true));
        }}
      >
        <Copy className="size-4" aria-hidden="true" />
        {t('reports.reminder.button')}
      </Button>
      {copied ? (
        <span role="status" className="w-full text-xs text-calm-ink">
          {t('reports.reminder.copied')}
        </span>
      ) : null}
    </li>
  );
}

function RequestState({ request }: { request: InfoRequest }) {
  const { t } = useTranslation();
  if (request.state === 'received') {
    return (
      <Signal state="calm">
        {t('reports.requestStates.received', {
          date: request.received_on ? formatDate(request.received_on) : '',
        })}
      </Signal>
    );
  }
  if (request.state === 'overdue') {
    return (
      <Signal state="burn">
        {t('reports.requestStates.overdue', { days: request.late_days })}
      </Signal>
    );
  }
  return (
    <Signal state="plain">
      {request.due_on
        ? t('reports.requestStates.requestedDue', { date: formatDate(request.due_on) })
        : t('reports.requestStates.requested')}
    </Signal>
  );
}

function Requests({
  card,
  view,
  canEdit,
}: {
  card: PreparationCard;
  view: ReportsView;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const receive = useReceive();
  const add = useAddRequest();
  const today = view.as_of.slice(0, 10);
  const [what, setWhat] = useState('');
  const [source, setSource] = useState('');
  const [due, setDue] = useState('');

  return (
    <Block title={t('reports.card.requests')} aside={missingText(t, card)}>
      {card.info_requests.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('reports.requests.none')}</p>
      ) : (
        <ul className="divide-y divide-line">
          {card.info_requests.map((request) => (
            <li key={request.id} className="flex flex-col gap-1 py-2 text-sm">
              <span className="text-ink-strong">{request.what}</span>
              <span className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                <span>{request.source.name}</span>
                <RequestState request={request} />
              </span>
              {canEdit ? (
                <span>
                  <Button
                    size="small"
                    look={request.state === 'received' ? 'quiet' : 'plain'}
                    disabled={receive.isPending}
                    onClick={() =>
                      receive.mutate({
                        id: card.id,
                        requestId: request.id,
                        received_on: request.state === 'received' ? null : today,
                        version: request.version,
                      })
                    }
                  >
                    {request.state === 'received'
                      ? t('reports.card.unreceive')
                      : t('reports.card.receive')}
                  </Button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <form
          className="mt-3 grid gap-2 sm:grid-cols-[1fr_12rem_10rem_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            const [kind, sourceId] = source.split(':');
            if (!what.trim() || !kind || !sourceId) return;
            const request: NewRequest = {
              what,
              source_kind: kind as NewRequest['source_kind'],
              source_id: sourceId,
              due_on: due || null,
            };
            add.mutate(
              { id: card.id, request },
              {
                onSuccess: () => {
                  setWhat('');
                  setDue('');
                },
              },
            );
          }}
        >
          <input
            aria-label={t('reports.card.what')}
            placeholder={t('reports.card.what')}
            className={FIELD}
            value={what}
            onChange={(event) => setWhat(event.target.value)}
          />
          <select
            aria-label={t('reports.card.source')}
            className={FIELD}
            value={source}
            onChange={(event) => setSource(event.target.value)}
          >
            <option value="">{t('reports.card.source')}</option>
            <optgroup label={t('reports.card.people')}>
              {view.people.map((each) => (
                <option key={each.id} value={`person:${each.id}`}>
                  {each.name}
                </option>
              ))}
            </optgroup>
            <optgroup label={t('reports.card.organizations')}>
              {view.organizations.map((each) => (
                <option key={each.id} value={`organization:${each.id}`}>
                  {each.short_name ?? each.name}
                </option>
              ))}
            </optgroup>
          </select>
          <input
            type="date"
            aria-label={t('reports.card.due')}
            className={FIELD}
            value={due}
            onChange={(event) => setDue(event.target.value)}
          />
          <Button type="submit" disabled={add.isPending || !what.trim() || !source}>
            {t('reports.card.request')}
          </Button>
        </form>
      ) : null}
    </Block>
  );
}

function Checklist({ card, canEdit }: { card: PreparationCard; canEdit: boolean }) {
  const { t } = useTranslation();
  const toggle = useToggleItem();
  const add = useAddItem();
  const [text, setText] = useState('');
  const done = card.items.filter((each) => each.is_done).length;

  return (
    <Block
      title={t('reports.card.checklist')}
      aside={t('reports.card.checklistCount', { done, total: card.items.length })}
    >
      {card.items.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('reports.card.noItems')}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {card.items.map((item) => (
            <li key={item.id}>
              <label className="inline-flex min-h-touch items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={item.is_done}
                  disabled={!canEdit || toggle.isPending}
                  onChange={(event) =>
                    toggle.mutate({
                      id: card.id,
                      itemId: item.id,
                      done: event.target.checked,
                      version: item.version,
                    })
                  }
                />
                <span className={cn(item.is_done ? 'text-ink-muted line-through' : 'text-ink')}>
                  {item.text}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <form
          className="mt-2 flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (!text.trim()) return;
            add.mutate({ id: card.id, text }, { onSuccess: () => setText('') });
          }}
        >
          <input
            aria-label={t('reports.card.newItem')}
            placeholder={t('reports.card.newItem')}
            className={cn(FIELD, 'flex-1')}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <Button type="submit" disabled={add.isPending || !text.trim()}>
            {t('reports.card.addItem')}
          </Button>
        </form>
      ) : null}
    </Block>
  );
}

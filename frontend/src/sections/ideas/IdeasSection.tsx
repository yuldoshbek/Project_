/**
 * Идеи и карты — «что предложено и как это связано?» (ТЗ 2, 3.6).
 *
 * Вкладка «Идеи»: вопрос «Что ждёт моего „да“?» с ответом и действием, запись новой идеи,
 * идеи по шагам пути. Руководитель решает: в проект, в задачу или отложить — решение сразу
 * заводит настоящую запись (критерий 1 блока 3). Вкладка «Карты» — интеллект-карты:
 * полотно на ноутбуке, контур на телефоне, без правки на мониторе (ТЗ 6).
 */

import { useNavigate, useSearch } from '@tanstack/react-router';
import { Lightbulb } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Sheet } from '@/shared/ui/Sheet';
import { Empty, Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { Maps } from './Maps';
import type { Idea, IdeasView, Outcome } from './model';
import { awaitingText, ideaMeta } from './text';
import { useCreateIdea, useDecide, useIdeas, useToReview } from './useIdeas';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

const TABS = ['ideas', 'maps'] as const;
type Tab = (typeof TABS)[number];

export function IdeasSection() {
  const ideas = useIdeas();
  if (ideas.isPending) return <Loading />;
  if (ideas.isError) {
    return <Failure detail={describeError(ideas.error)} onRetry={() => void ideas.refetch()} />;
  }
  return <Ideas view={ideas.data} />;
}

function Ideas({ view }: { view: IdeasView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const viewer: Role = user.data?.role === 'leader' ? 'leader' : 'assistant';
  const search: { view?: unknown; map?: unknown } = useSearch({ strict: false });
  const navigate = useNavigate();
  const tab: Tab = search.view === 'maps' ? 'maps' : 'ideas';
  const openMap = typeof search.map === 'string' ? search.map : null;
  const go = (next: { view?: Tab; map?: string | null }) =>
    void navigate({
      to: '/ideas',
      search: {
        ...((next.view ?? tab) === 'maps' ? { view: 'maps' } : {}),
        ...(next.map ? { map: next.map } : {}),
      },
      replace: true,
    });

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <header className="flex flex-wrap items-center gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {device === 'phone' ? null : (
            <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
              <Lightbulb className="size-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink-strong">{t('sections.ideas')}</h1>
            <p className="text-sm text-ink-muted">{t('sectionQuestions.ideas')}</p>
            {view.is_demo ? (
              <p className="mt-1 text-xs">
                <span title={t('pult.demoHint')}>
                  <Signal state="wait">{t('pult.demo')}</Signal>
                </span>
              </p>
            ) : null}
          </div>
        </div>
        <span role="tablist" aria-label={t('ideas.tabs.label')} className="inline-flex gap-1">
          {TABS.map((each) => (
            <button
              key={each}
              type="button"
              role="tab"
              aria-selected={tab === each}
              onClick={() => go({ view: each, map: null })}
              className={cn(
                'min-h-touch rounded-[var(--radius-pill)] border px-4 text-sm md:min-h-9',
                tab === each
                  ? 'border-line-accent bg-accent-soft text-accent-ink'
                  : 'border-line bg-card text-ink-muted hover:bg-hover',
              )}
            >
              {t(`ideas.tabs.${each}`)}
            </button>
          ))}
        </span>
      </header>

      <div role="tabpanel" aria-label={t(`ideas.tabs.${tab}`)}>
        {tab === 'ideas' ? (
          <IdeasTab view={view} viewer={viewer} />
        ) : (
          <Maps view={view} openId={openMap} onOpen={(id) => go({ view: 'maps', map: id })} />
        )}
      </div>
    </div>
  );
}

function IdeasTab({ view, viewer }: { view: IdeasView; viewer: Role }) {
  const { t } = useTranslation();
  const device = useDevice();
  const [deciding, setDeciding] = useState<string | null>(null);
  const [onlyWaiting, setOnlyWaiting] = useState(false);
  const answer = view.questions[0];
  const text = answer ? awaitingText(t, answer) : null;
  const freshness = t('ideas.freshness', { when: formatDateTime(view.as_of) });

  const byId = new Map(view.items.map((each) => [each.id, each]));
  const waiting = (answer?.rows ?? []).flatMap((id) => byId.get(id) ?? []);
  const groups: { key: string; items: Idea[] }[] = onlyWaiting
    ? [{ key: 'review', items: waiting }]
    : [
        { key: 'review', items: waiting },
        { key: 'draft', items: view.items.filter((each) => each.step === 'draft') },
        { key: 'decided', items: view.items.filter((each) => each.step === 'decided') },
      ];
  const target = deciding ? byId.get(deciding) : undefined;

  return (
    <div className="flex flex-col gap-4">
      <div className={cn('grid gap-3', device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-4')}>
        {answer && text ? (
          <Card title={t('ideas.awaiting.title')} freshness={freshness} className="flex flex-col">
            <p className="text-lg leading-snug font-semibold text-ink-strong">{text.main}</p>
            {text.detail ? <p className="mt-1 text-sm text-ink-muted">{text.detail}</p> : null}
            {answer.count > 0 ? (
              <div className="mt-auto pt-3">
                {viewer === 'leader' && answer.oldest_id ? (
                  <Button size="small" onClick={() => setDeciding(answer.oldest_id)}>
                    {t('ideas.awaiting.decide')}
                  </Button>
                ) : (
                  <Button size="small" onClick={() => setOnlyWaiting(true)}>
                    {t('ideas.awaiting.show')}
                  </Button>
                )}
              </div>
            ) : null}
          </Card>
        ) : null}
        <NewIdea />
      </div>

      {onlyWaiting ? (
        <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
          {t('ideas.list.filtered', { count: waiting.length })}
          <Button size="small" look="quiet" onClick={() => setOnlyWaiting(false)}>
            {t('ideas.list.clear')}
          </Button>
        </p>
      ) : null}

      {groups.map((group) => (
        <section
          key={group.key}
          aria-label={t(`ideas.groups.${group.key}`)}
          className="flex flex-col gap-2"
        >
          <h2 className="text-sm font-semibold text-ink-strong">
            {t(`ideas.groups.${group.key}`)}{' '}
            <span className="numeric font-normal text-ink-muted">{group.items.length}</span>
          </h2>
          {group.items.length === 0 ? (
            <Empty label={t(`ideas.empty.${group.key}`)} />
          ) : (
            <ul
              className={cn('grid gap-2', device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-3')}
            >
              {group.items.map((idea) => (
                <IdeaRow
                  key={idea.id}
                  idea={idea}
                  viewer={viewer}
                  onDecide={() => setDeciding(idea.id)}
                />
              ))}
            </ul>
          )}
        </section>
      ))}

      {target ? (
        <Sheet
          label={t('ideas.decision.label')}
          closeLabel={t('ideas.decision.close')}
          onClose={() => setDeciding(null)}
        >
          <Decision idea={target} view={view} onDone={() => setDeciding(null)} />
        </Sheet>
      ) : null}
    </div>
  );
}

function IdeaRow({ idea, viewer, onDecide }: { idea: Idea; viewer: Role; onDecide: () => void }) {
  const { t } = useTranslation();
  const review = useToReview();
  const open = idea.step !== 'decided' || idea.outcome === 'postponed';
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <span className="inline-flex flex-wrap items-center gap-2">
        <Signal
          state={
            idea.step === 'review'
              ? 'call'
              : idea.outcome === 'postponed'
                ? 'wait'
                : idea.step === 'decided'
                  ? 'calm'
                  : 'plain'
          }
        >
          {idea.step === 'decided' && idea.outcome
            ? t(`ideas.outcomes.${idea.outcome}`)
            : t(`ideas.steps.${idea.step}`)}
        </Signal>
        <span className="numeric text-xs text-ink-muted">
          {ideaMeta(t, idea, formatDate(idea.created_at.slice(0, 10)))}
        </span>
      </span>
      <span className="text-ink-strong">{idea.text}</span>
      {idea.link ? (
        <span className="text-sm text-ink">
          {t(`ideas.link.${idea.link.type}`, { code: idea.link.code, title: idea.link.title })}
        </span>
      ) : null}
      {open ? (
        <span className="flex flex-wrap gap-2">
          {viewer === 'leader' ? (
            <Button size="small" look="primary" onClick={onDecide}>
              {t('ideas.decision.open')}
            </Button>
          ) : null}
          {idea.step !== 'review' ? (
            <Button
              size="small"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: idea.id, version: idea.version })}
            >
              {t('ideas.toReview')}
            </Button>
          ) : null}
        </span>
      ) : null}
      {review.isError ? (
        <p role="alert" className="text-sm text-burn-ink">
          {describeError(review.error)}
        </p>
      ) : null}
    </li>
  );
}

function NewIdea() {
  const { t } = useTranslation();
  const create = useCreateIdea();
  const [text, setText] = useState('');
  return (
    <Card title={t('ideas.new.title')} question={t('ideas.new.hint')}>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!text.trim()) return;
          create.mutate(text, { onSuccess: () => setText('') });
        }}
      >
        <input
          aria-label={t('ideas.new.label')}
          placeholder={t('ideas.new.placeholder')}
          className={cn(FIELD, 'flex-1')}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Button type="submit" look="primary" disabled={create.isPending || !text.trim()}>
          {t('ideas.new.add')}
        </Button>
      </form>
      {create.isError ? (
        <p role="alert" className="mt-2 text-sm text-burn-ink">
          {describeError(create.error)}
        </p>
      ) : null}
    </Card>
  );
}

function Decision({ idea, view, onDone }: { idea: Idea; view: IdeasView; onDone: () => void }) {
  const { t } = useTranslation();
  const decide = useDecide();
  const [type, setType] = useState(view.project_types[0]?.code ?? '');
  const act = (outcome: Outcome) =>
    decide.mutate(
      {
        id: idea.id,
        outcome,
        type_code: outcome === 'project' ? type || null : null,
        version: idea.version,
      },
      { onSuccess: onDone },
    );
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-xs text-ink-muted">
          {ideaMeta(t, idea, formatDate(idea.created_at.slice(0, 10)))}
        </p>
        <p className="mt-1 text-lg leading-snug font-semibold text-ink-strong">{idea.text}</p>
      </div>
      <p className="text-sm text-ink-muted">{t('ideas.decision.hint')}</p>
      <div className="flex flex-col gap-2 rounded-[var(--radius-lg)] border border-line p-3">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          {t('ideas.decision.type')}
          <select className={FIELD} value={type} onChange={(event) => setType(event.target.value)}>
            {view.project_types.map((each) => (
              <option key={each.code} value={each.code}>
                {each.name}
              </option>
            ))}
          </select>
        </label>
        <Button look="primary" disabled={decide.isPending || !type} onClick={() => act('project')}>
          {t('ideas.decision.project')}
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={decide.isPending} onClick={() => act('task')}>
          {t('ideas.decision.task')}
        </Button>
        <Button look="quiet" disabled={decide.isPending} onClick={() => act('postponed')}>
          {t('ideas.decision.postpone')}
        </Button>
      </div>
      {decide.isError ? (
        <p role="alert" className="text-sm text-burn-ink">
          {describeError(decide.error)}
        </p>
      ) : null}
    </div>
  );
}

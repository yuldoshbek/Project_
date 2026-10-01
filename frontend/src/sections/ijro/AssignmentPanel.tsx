/**
 * Карточка поручения (ТЗ 3.3).
 *
 * Что пришло из таблицы и что внёс человек — видно отдельно (инвариант 6): содержание и
 * механизм — как в источнике, на узбекской кириллице; написание ответственного из таблицы
 * показано всегда, сопоставленный сотрудник — рядом. Кнопки — по роли (V35): отметку ставят
 * оба, решает руководитель, спрашивает и правит помощник.
 */

import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { STEP_DECISIONS } from '@/sections/pult/model';
import { describeError } from '@/shared/api/client';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime } from '@/shared/time';
import { Block } from '@/shared/ui/Block';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { StepBadge } from './AssignmentsTab';
import { MARK_KINDS, STAGES, type AssignmentCard, type MarkKind } from './model';
import { dueLabel, place } from './text';
import {
  useAsk,
  useAssignment,
  useComment,
  useCreateTask,
  useDecide,
  useExtensionRequested,
  useMark,
  useMatchPerson,
  useProblem,
  useStage,
  useTaskPrefill,
  useUndoDecision,
} from './useIjro';

const FIELD =
  'w-full rounded-[var(--radius)] border border-line-strong bg-card p-2 text-[15px] text-ink';

export function AssignmentPanel({ id, viewer }: { id: string; viewer: Role }) {
  const card = useAssignment(id);
  if (card.isPending) return <Loading />;
  if (card.isError) {
    return <Failure detail={describeError(card.error)} onRetry={() => void card.refetch()} />;
  }
  return <Panel card={card.data} viewer={viewer} />;
}

function Panel({ card, viewer }: { card: AssignmentCard; viewer: Role }) {
  const { t } = useTranslation();
  const canEdit = viewer === 'assistant';

  return (
    <div className="flex flex-col gap-3">
      <header className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-ink-strong">{place(card)}</h2>
        <p className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <StepBadge row={card} />
          <span>{t(`ijro.sources.${card.document.source}`)}</span>
        </p>
        <p className="text-sm text-ink-muted">{card.document.title}</p>
      </header>

      <Decision card={card} viewer={viewer} />

      <Block title={t('ijro.card.content')}>
        <p className="text-[15px] leading-relaxed text-ink-strong">{card.content}</p>
        <h4 className="mt-3 text-xs font-medium text-ink-muted">{t('ijro.card.mechanism')}</h4>
        <p className="text-sm text-ink">{card.mechanism ?? t('ijro.card.noMechanism')}</p>
      </Block>

      <Due card={card} canEdit={canEdit} />

      <Block title={t('ijro.card.responsible.title')}>
        <p className="text-sm text-ink">
          {card.responsible
            ? t('ijro.card.responsible.matched', { name: card.responsible.name })
            : t('ijro.card.responsible.unmatched')}
        </p>
        <p className="mt-1 text-xs text-ink-muted">
          {t('ijro.card.responsible.raw', { raw: card.responsible_raw })}
        </p>
        {canEdit ? <Suggestions card={card} /> : null}
        <h4 className="mt-3 text-xs font-medium text-ink-muted">{t('ijro.card.lead.title')}</h4>
        <p className="text-sm text-ink">
          {card.lead_organization
            ? t('ijro.lead.coExecutor', { name: card.lead_organization.name })
            : t('ijro.card.lead.agency')}
        </p>
      </Block>

      <Stage card={card} canEdit={canEdit} />
      <Problem key={`problem-${card.version}`} card={card} canEdit={canEdit} />
      <Marks card={card} />
      <Tasks card={card} canEdit={canEdit} />
      <Feed card={card} />

      <Block title={t('ijro.card.source.title')}>
        <p className="text-sm text-ink">
          {t('ijro.card.source.line', {
            source: t(`ijro.sources.${card.document.source}`),
            date: formatDate(card.import.table_on),
            file: card.import.file,
          })}
        </p>
      </Block>
    </div>
  );
}

/** Вопрос руководителю и решение: руководитель решает, помощник спрашивает — как на Пульте. */
function Decision({ card, viewer }: { card: AssignmentCard; viewer: Role }) {
  const { t } = useTranslation();
  const decide = useDecide();
  const undo = useUndoDecision();
  const ask = useAsk();
  const [text, setText] = useState('');
  // «Отменить» относится к решению, принятому этим касанием, а не к последнему вообще.
  const [made, setMade] = useState<string | null>(null);
  const decided = made !== null && card.last_decision?.id === made ? card.last_decision : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    ask.mutate({ id: card.id, text: value }, { onSuccess: () => setText('') });
  };

  return (
    <section className="rounded-[var(--radius-lg)] border border-line-accent bg-accent-soft/40 p-4">
      {card.question ? (
        <p className="text-sm text-ink-strong">
          <span className="text-xs font-medium text-call-ink">{t('ijro.card.question')}</span>
          <span className="mt-1 block">{card.question.text}</span>
        </p>
      ) : null}
      {decided ? (
        <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
          <span>{t('ijro.card.decided', { kind: t(`pult.decisions.${decided.kind}`) })}</span>
          <Button
            size="small"
            disabled={undo.isPending}
            onClick={() => undo.mutate(decided.id, { onSuccess: () => setMade(null) })}
          >
            {t('ijro.card.undo')}
          </Button>
        </p>
      ) : viewer === 'leader' && card.step ? (
        <div className={cn('flex flex-wrap gap-2', card.question && 'mt-3')}>
          {STEP_DECISIONS[card.step].slice(0, 3).map((kind, index) => (
            <Button
              key={kind}
              look={index === 0 ? 'primary' : 'plain'}
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { id: card.id, kind },
                  { onSuccess: (decisionId) => setMade(decisionId) },
                )
              }
            >
              {t(`pult.decisions.${kind}`)}
            </Button>
          ))}
        </div>
      ) : viewer === 'assistant' && !card.question ? (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label htmlFor={`ask-${card.id}`} className="text-xs font-medium text-ink-muted">
            {t('pult.ask.label')}
          </label>
          <textarea
            id={`ask-${card.id}`}
            rows={2}
            value={text}
            onChange={(event) => setText(event.target.value)}
            className={FIELD}
          />
          <div>
            <Button type="submit" disabled={ask.isPending || text.trim() === ''}>
              {t('pult.ask.send')}
            </Button>
          </div>
        </form>
      ) : !card.question ? (
        <p className="text-sm text-ink-muted">{t('ijro.card.calm')}</p>
      ) : null}
    </section>
  );
}

function Due({ card, canEdit }: { card: AssignmentCard; canEdit: boolean }) {
  const { t } = useTranslation();
  const requested = useExtensionRequested();
  return (
    <Block title={t('ijro.card.due.title')} aside={dueLabel(t, card)}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {card.original_due_on && card.original_due_on !== card.due_on ? (
          <>
            <dt className="text-ink-muted">{t('ijro.card.due.original')}</dt>
            <dd className="numeric text-ink">{formatDate(card.original_due_on)}</dd>
          </>
        ) : null}
        {card.interim_on ? (
          <>
            <dt className="text-ink-muted">{t('ijro.card.due.interim')}</dt>
            <dd className="numeric text-ink">{formatDate(card.interim_on)}</dd>
          </>
        ) : null}
      </dl>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {card.extension_requested ? (
          <Signal state="wait">{t('ijro.card.due.requested')}</Signal>
        ) : null}
        {canEdit ? (
          <Button
            size="small"
            disabled={requested.isPending}
            onClick={() =>
              requested.mutate({
                id: card.id,
                value: !card.extension_requested,
                version: card.version,
              })
            }
          >
            {t(card.extension_requested ? 'ijro.card.due.unrequest' : 'ijro.card.due.request')}
          </Button>
        ) : null}
      </div>
      {card.extension_history.length > 0 ? (
        <>
          <h4 className="mt-3 text-xs font-medium text-ink-muted">{t('ijro.card.due.history')}</h4>
          <ul className="mt-1 flex flex-col gap-1 text-sm text-ink">
            {card.extension_history.map((each) => (
              <li key={`${each.from}-${each.to}`} className="numeric">
                {t('ijro.card.due.historyLine', {
                  from: formatDate(each.from),
                  to: formatDate(each.to),
                  on: formatDate(each.on),
                  kind: t(`ijro.card.due.kinds.${each.kind}`),
                })}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </Block>
  );
}

/** Система предлагает, человек подтверждает; склейки ФИО алгоритмом нет (ТЗ 7). */
function Suggestions({ card }: { card: AssignmentCard }) {
  const { t } = useTranslation();
  const match = useMatchPerson();
  if (card.suggestions.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {card.suggestions.map((person) => (
        <Button
          key={person.id}
          size="small"
          disabled={match.isPending}
          onClick={() => match.mutate({ id: card.id, personId: person.id, version: card.version })}
        >
          {t('ijro.card.responsible.suggest', { name: person.name })}
        </Button>
      ))}
    </div>
  );
}

function Stage({ card, canEdit }: { card: AssignmentCard; canEdit: boolean }) {
  const { t } = useTranslation();
  const stage = useStage();
  return (
    <Block
      title={t('ijro.card.stage.title')}
      aside={t('ijro.card.stage.since', { date: formatDate(card.stage_changed_on) })}
    >
      {canEdit ? (
        <div className="flex flex-wrap gap-2">
          {STAGES.map((each) => (
            <Button
              key={each}
              size="small"
              look={card.stage === each ? 'primary' : 'plain'}
              aria-pressed={card.stage === each}
              disabled={stage.isPending}
              onClick={() => stage.mutate({ id: card.id, stage: each, version: card.version })}
            >
              {t(`ijro.stages.${each}`)}
            </Button>
          ))}
        </div>
      ) : (
        <Signal state={card.stage === 'returned' ? 'burn' : 'plain'}>
          {t(`ijro.stages.${card.stage}`)}
        </Signal>
      )}
    </Block>
  );
}

function Problem({ card, canEdit }: { card: AssignmentCard; canEdit: boolean }) {
  const { t } = useTranslation();
  const save = useProblem();
  const [problem, setProblem] = useState(card.problem ?? '');
  const [proposal, setProposal] = useState(card.proposal ?? '');

  return (
    <Block
      title={t('ijro.card.problem.title')}
      aside={
        card.problem_updated_on
          ? t('ijro.card.problem.updated', { date: formatDate(card.problem_updated_on) })
          : undefined
      }
    >
      {canEdit ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate({ id: card.id, problem, proposal, version: card.version });
          }}
        >
          <label className="text-xs font-medium text-ink-muted" htmlFor={`problem-${card.id}`}>
            {t('ijro.card.problem.problem')}
          </label>
          <textarea
            id={`problem-${card.id}`}
            rows={2}
            value={problem}
            onChange={(event) => setProblem(event.target.value)}
            className={FIELD}
          />
          <label className="text-xs font-medium text-ink-muted" htmlFor={`proposal-${card.id}`}>
            {t('ijro.card.problem.proposal')}
          </label>
          <textarea
            id={`proposal-${card.id}`}
            rows={2}
            value={proposal}
            onChange={(event) => setProposal(event.target.value)}
            className={FIELD}
          />
          <div>
            <Button type="submit" size="small" disabled={save.isPending}>
              {t('ijro.card.problem.save')}
            </Button>
          </div>
        </form>
      ) : card.problem ? (
        <>
          <p className="text-sm text-ink-strong">{card.problem}</p>
          {card.proposal ? (
            <p className="mt-2 text-sm text-ink">
              <span className="text-xs font-medium text-ink-muted">
                {t('ijro.card.problem.proposal')}
              </span>
              <span className="block">{card.proposal}</span>
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-ink-muted">{t('ijro.card.problem.none')}</p>
      )}
    </Block>
  );
}

function Marks({ card }: { card: AssignmentCard }) {
  const { t } = useTranslation();
  const mark = useMark();
  const [promised, setPromised] = useState('');
  const [comment, setComment] = useState('');

  const put = (kind: MarkKind) =>
    mark.mutate(
      {
        id: card.id,
        kind,
        promised_on: promised || null,
        comment: comment || null,
      },
      {
        onSuccess: () => {
          setPromised('');
          setComment('');
        },
      },
    );

  return (
    <Block
      title={t('ijro.card.marks.title')}
      question={t('ijro.card.marks.question')}
      aside={
        card.sign_of_life
          ? t(`ijro.life.${card.sign_of_life.source}`, { date: formatDate(card.sign_of_life.on) })
          : t('ijro.life.none')
      }
    >
      <div className="flex flex-wrap gap-2">
        {MARK_KINDS.map((kind) => (
          <Button key={kind} disabled={mark.isPending} onClick={() => put(kind)}>
            {t(`ijro.marks.${kind}`)}
          </Button>
        ))}
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-[10rem_1fr]">
        <div>
          <label className="text-xs text-ink-muted" htmlFor={`promised-${card.id}`}>
            {t('ijro.card.marks.promised')}
          </label>
          <input
            id={`promised-${card.id}`}
            type="date"
            value={promised}
            onChange={(event) => setPromised(event.target.value)}
            className={cn(FIELD, 'min-h-touch')}
          />
        </div>
        <div>
          <label className="text-xs text-ink-muted" htmlFor={`mark-comment-${card.id}`}>
            {t('ijro.card.marks.comment')}
          </label>
          <input
            id={`mark-comment-${card.id}`}
            type="text"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className={cn(FIELD, 'min-h-touch')}
          />
        </div>
      </div>
      {card.marks.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">{t('ijro.card.marks.none')}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2 text-sm">
          {card.marks.map((each) => (
            <li key={each.id} className="border-t border-line pt-2">
              <span className="font-medium text-ink-strong">{t(`ijro.marks.${each.kind}`)}</span>
              <span className="numeric text-ink-muted">
                {' · '}
                {formatDateTime(each.made_at)}
                {' · '}
                {t(`role.${each.author}`)}
              </span>
              {each.promised_on ? (
                <span className="block text-ink">
                  {t('ijro.card.marks.promisedLine', { date: formatDate(each.promised_on) })}
                </span>
              ) : null}
              {each.comment ? <span className="block text-ink">{each.comment}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}

function Tasks({ card, canEdit }: { card: AssignmentCard; canEdit: boolean }) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const prefill = useTaskPrefill(card.id, confirming);
  const create = useCreateTask();

  return (
    <Block title={t('ijro.card.tasks.title')} question={t('ijro.card.tasks.question')}>
      {card.linked_tasks.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('ijro.card.tasks.none')}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {card.linked_tasks.map((task) => (
            <li key={task.id}>
              <span className="text-ink-strong">{task.title}</span>
              <span className="numeric block text-xs text-ink-muted">
                {[
                  task.code,
                  t(`tasks.statuses.${task.status}`),
                  task.due_on ? t('ijro.due.day', { date: formatDate(task.due_on) }) : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      )}
      {canEdit && !confirming ? (
        <div className="mt-3">
          <Button size="small" onClick={() => setConfirming(true)}>
            {t('ijro.card.tasks.decompose')}
          </Button>
        </div>
      ) : null}
      {confirming && prefill.data ? (
        <div className="mt-3 rounded-[var(--radius)] border border-line bg-sunken p-3 text-sm">
          <p className="font-medium text-ink-strong">{prefill.data.title}</p>
          <p className="numeric mt-1 text-xs text-ink-muted">
            {prefill.data.due_on
              ? t('ijro.card.tasks.confirmDue', { date: formatDate(prefill.data.due_on) })
              : t('ijro.card.tasks.confirmNoDue')}
            {' · '}
            {card.responsible?.name ?? t('ijro.card.tasks.confirmNoAssignee')}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              look="primary"
              size="small"
              disabled={create.isPending}
              onClick={() => create.mutate(card.id, { onSuccess: () => setConfirming(false) })}
            >
              {t('ijro.card.tasks.create')}
            </Button>
            <Button size="small" look="quiet" onClick={() => setConfirming(false)}>
              {t('ijro.card.tasks.cancel')}
            </Button>
          </div>
        </div>
      ) : null}
    </Block>
  );
}

function Feed({ card }: { card: AssignmentCard }) {
  const { t } = useTranslation();
  const add = useComment();
  const [text, setText] = useState('');
  return (
    <Block title={t('ijro.card.feed.title')}>
      {card.comments.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('ijro.card.feed.none')}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {card.comments.map((each) => (
            <li key={each.id}>
              <span className="text-ink-strong">{each.text}</span>
              <span className="numeric block text-xs text-ink-muted">
                {formatDateTime(each.created_at)}
                {' · '}
                {t(`role.${each.author}`)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form
        className="mt-3 flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          const value = text.trim();
          if (!value) return;
          add.mutate({ id: card.id, text: value }, { onSuccess: () => setText('') });
        }}
      >
        <input
          type="text"
          aria-label={t('ijro.card.feed.label')}
          value={text}
          onChange={(event) => setText(event.target.value)}
          className={cn(FIELD, 'min-h-touch flex-1')}
        />
        <Button type="submit" disabled={add.isPending || text.trim() === ''}>
          {t('ijro.card.feed.add')}
        </Button>
      </form>
    </Block>
  );
}

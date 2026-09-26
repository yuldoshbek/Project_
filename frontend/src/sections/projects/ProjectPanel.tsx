/**
 * Карточка проекта — всё о проекте на одном листе.
 *
 * Порядок блоков — порядок вопросов руководителя (ТЗ 5): идёт ли проект и насколько
 * отстаёт; ждёт ли он решения; что мешает; где мы по вехам; что будет, если сдвинуть срок.
 * Справочные сведения — организации, подпроекты, задачи — ниже.
 *
 * Вносит и меняет данные помощник; руководитель смотрит и считает «что если» — расчёт
 * ничего не записывает, поэтому доступен обоим. Сервер проверяет то же самое сам.
 */

import { AlertTriangle, Building2, CircleHelp, Layers } from 'lucide-react';
import { useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { deviationText } from '@/sections/pult/text';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import {
  BOARD_COLUMNS,
  NEEDS_REASON,
  TERMINAL,
  type ProjectDetail,
  type ProjectStatus,
} from './model';
import { StatusReason } from './StatusReason';
import { dueText, lagText } from './text';
import { useImpediment, useProject, useProjectStatus } from './useProjects';
import { WhatIf } from './WhatIf';

interface ProjectPanelProps {
  id: string;
  canEdit: boolean;
  onOpen: (id: string) => void;
}

export function ProjectPanel({ id, canEdit, onOpen }: ProjectPanelProps) {
  const project = useProject(id);
  if (project.isPending) return <Loading />;
  if (project.isError) {
    return <Failure detail={describeError(project.error)} onRetry={() => void project.refetch()} />;
  }
  return <Panel project={project.data} canEdit={canEdit} onOpen={onOpen} />;
}

function Panel({
  project,
  canEdit,
  onOpen,
}: {
  project: ProjectDetail;
  canEdit: boolean;
  onOpen: (id: string) => void;
}) {
  const { t } = useTranslation();
  const terminal = TERMINAL.has(project.status);

  return (
    <>
      <header className="flex flex-col gap-2">
        <p className="numeric text-xs text-ink-muted">
          {project.code} · {project.type.name} · {t(`projects.statuses.${project.status}`)}
        </p>
        <h2 className="text-xl leading-snug font-semibold text-ink-strong">{project.title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          {project.step ? (
            <>
              <Signal state={STEP_SIGNAL[project.step]}>{t(`pult.steps.${project.step}`)}</Signal>
              <span className="numeric text-sm text-ink">
                {deviationText(t, { step: project.step, deviation: project.deviation })}
              </span>
            </>
          ) : !terminal ? (
            <Signal state="calm">{t('projects.whatIf.onPlan')}</Signal>
          ) : null}
          {project.is_multiyear ? (
            <Chip icon={<Layers className="size-3" aria-hidden="true" />}>
              {t('projects.card.program')}
            </Chip>
          ) : null}
          {project.center_role ? (
            <Chip icon={<Building2 className="size-3" aria-hidden="true" />}>
              {t('projects.card.center', { role: t(`projects.roles.${project.center_role}`) })}
            </Chip>
          ) : null}
        </div>
        {project.parent ? (
          <button
            type="button"
            onClick={() => onOpen(project.parent!.id)}
            className="self-start text-left text-sm text-accent-ink hover:underline"
          >
            {t('projects.card.parent', { title: project.parent.title })}
          </button>
        ) : null}
        {project.status_reason ? (
          <p className="text-sm text-ink">
            {t('projects.card.reason', { reason: project.status_reason })}
          </p>
        ) : null}
      </header>

      {project.question ? (
        <div className="flex gap-2 rounded-[var(--radius)] bg-call-soft p-3 text-call-ink">
          <CircleHelp className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div className="min-w-0 text-sm">
            <p className="font-medium">{t('projects.panel.question')}</p>
            <p>{project.question.text}</p>
            <p className="numeric text-xs">{formatDate(project.question.asked_on)}</p>
          </div>
        </div>
      ) : null}

      <Facts project={project} />

      <Impediment project={project} canEdit={canEdit && !terminal} />

      <Block
        title={t('projects.panel.milestones')}
        question={t('projects.panel.milestonesQuestion')}
      >
        <ol className="flex flex-col divide-y divide-line">
          {project.milestone_list.map((mark) => (
            <li key={mark.id} className="flex items-start gap-3 py-2">
              <span
                className={cn(
                  'mt-1.5 size-2.5 shrink-0 rotate-45 border-2 border-ink-strong',
                  mark.is_passed ? 'bg-ink-strong' : 'bg-card',
                )}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className={cn('text-sm', mark.is_passed ? 'text-ink-muted' : 'text-ink-strong')}>
                  {mark.title}
                </p>
                <p className="numeric text-xs text-ink-muted">
                  {mark.is_passed && mark.passed_on
                    ? t('projects.panel.passed', { date: formatDate(mark.passed_on) })
                    : dueText(t, mark)}
                </p>
              </div>
              {mark.step ? (
                <Signal state={STEP_SIGNAL[mark.step]}>
                  {deviationText(t, { step: mark.step, deviation: mark.deviation })}
                </Signal>
              ) : null}
            </li>
          ))}
        </ol>
      </Block>

      {!terminal ? <WhatIf project={project} canApply={canEdit} /> : null}

      {canEdit ? <StatusControl project={project} /> : null}

      <Block title={t('projects.panel.organizations')}>
        {project.organizations.length === 0 ? (
          <p className="text-sm text-ink-muted">{t('projects.panel.noOrganizations')}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {project.organizations.map((org) => (
              <li key={`${org.id}-${org.role}`} className="flex justify-between gap-3">
                <span className={cn('text-ink', org.is_center && 'font-medium text-ink-strong')}>
                  {org.name}
                </span>
                <span className="text-ink-muted">{t(`projects.roles.${org.role}`)}</span>
              </li>
            ))}
          </ul>
        )}
        {project.lead_outside ? (
          <p className="mt-2 text-xs text-wait-ink">{t('projects.card.outside')}</p>
        ) : null}
      </Block>

      {project.subproject_list.length > 0 ? (
        <Block title={t('projects.panel.subprojects')}>
          <ul className="flex flex-col divide-y divide-line">
            {project.subproject_list.map((sub) => (
              <li key={sub.id}>
                <button
                  type="button"
                  onClick={() => onOpen(sub.id)}
                  className="flex min-h-touch w-full items-center gap-3 py-2 text-left hover:text-accent-ink"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink-strong">
                      {sub.title}
                    </span>
                    <span className="numeric text-xs text-ink-muted">
                      {sub.code} · {dueText(t, sub)}
                    </span>
                  </span>
                  {sub.step ? (
                    <Signal state={STEP_SIGNAL[sub.step]}>{t(`pult.steps.${sub.step}`)}</Signal>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </Block>
      ) : null}

      <Block title={t('projects.panel.tasks')} aside={t('projects.card.tasks', project.tasks)}>
        {project.task_list.length === 0 ? (
          <p className="text-sm text-ink-muted">{t('projects.panel.noTasks')}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm text-ink">
            {project.task_list.map((task) => (
              <li key={task.id} className="flex justify-between gap-3">
                <span className="min-w-0">{task.title}</span>
                <span className="shrink-0 text-xs text-ink-muted">{task.assignee?.name ?? ''}</span>
              </li>
            ))}
          </ul>
        )}
      </Block>

      {project.direction || project.region ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {project.direction ? (
            <>
              <dt className="text-ink-muted">{t('projects.panel.direction')}</dt>
              <dd className="text-ink">{project.direction}</dd>
            </>
          ) : null}
          {project.region ? (
            <>
              <dt className="text-ink-muted">{t('projects.panel.region')}</dt>
              <dd className="text-ink">{project.region}</dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </>
  );
}

function Chip({ icon, children }: { icon: ReactNode; children: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-sunken px-2 py-0.5 text-xs text-ink">
      {icon}
      {children}
    </span>
  );
}

function Block({
  title,
  question,
  aside,
  children,
}: {
  title: string;
  question?: string;
  aside?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <header className="mb-2 flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink-strong">{title}</h3>
          {question ? <p className="text-xs text-ink-muted">{question}</p> : null}
        </div>
        {aside ? <span className="numeric shrink-0 text-xs text-ink-muted">{aside}</span> : null}
      </header>
      {children}
    </section>
  );
}

/** Главные числа проекта — все четыре считает сервер. */
function Facts({ project }: { project: ProjectDetail }) {
  const { t } = useTranslation();
  const terminal = TERMINAL.has(project.status);
  const facts: {
    label: string;
    value: string;
    hint?: string | undefined;
    tone?: string | undefined;
  }[] = [
    {
      label: t('projects.panel.dates'),
      value: dueText(t, project),
      hint: [
        t('projects.panel.started', { date: formatDate(project.started_on) }),
        project.moves > 0 ? t('projects.card.moves', { count: project.moves }) : null,
      ]
        .filter(Boolean)
        .join(' · '),
    },
    {
      label: t('projects.table.readiness'),
      value: t('projects.table.percent', { value: project.readiness }),
      hint: t('projects.card.milestones', project.milestones),
    },
  ];
  if (!terminal) {
    facts.push({
      label: t('projects.table.lag'),
      value: lagText(t, project.lag_days),
      tone: project.lag_days > 0 ? 'text-wait-ink' : undefined,
      hint: project.next_milestone
        ? t('projects.card.next', {
            title: project.next_milestone.title,
            date: formatDate(project.next_milestone.due_on),
          })
        : undefined,
    });
  }
  facts.push({
    label: t('projects.table.responsible'),
    value: project.responsible?.name ?? t('projects.card.noHolder'),
  });

  return (
    <dl className="grid grid-cols-2 gap-2">
      {facts.map((fact) => (
        <div key={fact.label} className="rounded-[var(--radius)] border border-line bg-card p-3">
          <dt className="text-xs text-ink-muted">{fact.label}</dt>
          <dd className={cn('numeric text-[15px] font-semibold text-ink-strong', fact.tone)}>
            {fact.value}
          </dd>
          {fact.hint ? <dd className="text-xs text-ink-muted">{fact.hint}</dd> : null}
        </div>
      ))}
    </dl>
  );
}

/** «Что мешает» — одна строка с датой. Устаревшая помечена: её пора подтвердить или снять. */
function Impediment({ project, canEdit }: { project: ProjectDetail; canEdit: boolean }) {
  const { t } = useTranslation();
  const save = useImpediment();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(project.impediment?.text ?? '');
  // Версия — та, с которой начали править: карточка перечитывается каждые 15 секунд, и
  // версия с экрана в момент «Сохранить» пропустила бы чужую правку (инвариант 15).
  const [basis, setBasis] = useState(project.version);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({ id: project.id, text, version: basis }, { onSuccess: () => setEditing(false) });
  };

  // Правка начинается с того, что на экране сейчас, а не с того, что было при первом
  // открытии карточки: строку могли поменять, пока лист был открыт.
  const edit = () => {
    save.reset();
    setText(project.impediment?.text ?? '');
    setBasis(project.version);
    setEditing(true);
  };

  const failure = save.isError ? <Failure detail={describeError(save.error)} /> : null;

  if (editing) {
    return (
      <form
        onSubmit={submit}
        className="flex flex-col gap-2 rounded-[var(--radius-lg)] border border-line bg-card p-4"
      >
        <label
          htmlFor={`impediment-${project.id}`}
          className="text-sm font-semibold text-ink-strong"
        >
          {t('projects.panel.impedimentLabel')}
        </label>
        <input
          id={`impediment-${project.id}`}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={t('projects.panel.impedimentPlaceholder')}
          autoFocus
          className="min-h-touch w-full rounded-[var(--radius)] border border-line-strong bg-card px-2 text-[15px] text-ink"
        />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" look="primary" disabled={save.isPending}>
            {t('projects.panel.save')}
          </Button>
          <Button type="button" look="quiet" onClick={() => setEditing(false)}>
            {t('projects.panel.cancel')}
          </Button>
        </div>
        {failure}
      </form>
    );
  }

  if (!project.impediment) {
    return canEdit ? (
      <Button look="plain" className="self-start" onClick={edit}>
        {t('projects.panel.impedimentAdd')}
      </Button>
    ) : null;
  }

  return (
    <section
      className={cn(
        'flex gap-2 rounded-[var(--radius-lg)] p-4',
        project.impediment.stale ? 'border border-line bg-card' : 'bg-wait-soft',
      )}
    >
      <AlertTriangle
        className={cn(
          'mt-0.5 size-4 shrink-0',
          project.impediment.stale ? 'text-ink-muted' : 'text-wait-ink',
        )}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <h3 className="text-sm font-semibold text-ink-strong">{t('projects.card.impediment')}</h3>
        <p className="text-sm text-ink">{project.impediment.text}</p>
        <p className="numeric text-xs text-ink-muted">
          {t('projects.card.impedimentAge', { date: formatDate(project.impediment.updated_on) })}
          {project.impediment.stale ? ` · ${t('projects.card.stale')}` : ''}
        </p>
        {canEdit ? (
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="small" onClick={edit}>
              {t('projects.panel.impedimentEdit')}
            </Button>
            <Button
              size="small"
              look="quiet"
              disabled={save.isPending}
              onClick={() => save.mutate({ id: project.id, text: '', version: project.version })}
            >
              {t('projects.panel.impedimentClear')}
            </Button>
          </div>
        ) : null}
        {failure ? <div className="mt-2">{failure}</div> : null}
      </div>
    </section>
  );
}

/** Статус — кнопками: доска перетаскиванием — ускорение, а это путь для всех. */
function StatusControl({ project }: { project: ProjectDetail }) {
  const { t } = useTranslation();
  const change = useProjectStatus();
  // Статус с причиной запоминает версию в момент выбора: пока помощник пишет причину,
  // карточка успеет перечитаться, и версия с экрана пропустила бы чужую правку.
  const [pending, setPending] = useState<{ status: ProjectStatus; version: number } | null>(null);

  const choose = (status: ProjectStatus) => {
    change.reset();
    if (NEEDS_REASON.has(status)) setPending({ status, version: project.version });
    else change.mutate({ id: project.id, status, reason: null, version: project.version });
  };

  return (
    <Block title={t('projects.panel.status')}>
      {pending ? (
        <StatusReason
          status={pending.status}
          busy={change.isPending}
          onCancel={() => setPending(null)}
          onSave={(reason) =>
            change.mutate(
              { id: project.id, status: pending.status, reason, version: pending.version },
              { onSuccess: () => setPending(null) },
            )
          }
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          {BOARD_COLUMNS.map((status) => (
            <Button
              key={status}
              size="small"
              look={status === project.status ? 'primary' : 'plain'}
              aria-pressed={status === project.status}
              disabled={change.isPending}
              onClick={() => (status === project.status ? undefined : choose(status))}
            >
              {t(`projects.statuses.${status}`)}
            </Button>
          ))}
        </div>
      )}
      {change.isError ? (
        <div className="mt-3">
          <Failure detail={describeError(change.error)} />
        </div>
      ) : null}
    </Block>
  );
}
